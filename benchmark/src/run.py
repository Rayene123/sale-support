"""Sequential sentiment benchmark for local and hosted model endpoints."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from prompt import build_messages

ROOT = Path(__file__).resolve().parents[1]
ITEMS_PATH = ROOT / "Data" / "items.jsonl"
RESULTS_DIR = ROOT / "results"
LABELS = {"positive", "negative", "neutral", "mixed"}
FIELDS = ["provider", "model", "item_id", "text", "reference_answer",
          "generated_answer", "latency_ms", "input_tokens", "output_tokens",
          "error", "error_type", "finish_reason", "response_model", "tokens_per_second"]
PRESETS = {
    "ollama": ("http://localhost:11434", "ollama", None, "qwen2.5:14b"),
    "openai": ("https://api.openai.com/v1", "responses", "OPENAI_API_KEY", None),
    "groq": ("https://api.groq.com/openai/v1", "chat", "GROQ_API_KEY", "openai/gpt-oss-20b"),
    "compatible": ("http://localhost:1234/v1", "chat", None, None),
}
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass  # OS environment and CLI work without optional .env loading.


def load_items(path=ITEMS_PATH):
    path = Path(path)
    with path.open(encoding="utf-8-sig") as file:
        if path.suffix.lower() == ".json":
            items = json.load(file)
        else:
            items = [json.loads(line) for line in file if line.strip()]
    if not isinstance(items, list) or not items:
        raise ValueError("Dataset must be a nonempty JSON array or JSONL records.")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or any(k not in item for k in ("id", "text", "label")):
            raise ValueError("Each item needs id, text, label.")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise ValueError("Item IDs must be unique nonempty strings.")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError("Each text must be a nonempty string.")
        if item["label"] not in LABELS:
            raise ValueError("Invalid reference label.")
        seen.add(item["id"])
    return items


def slugify_model_name(model):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-") or "model"


def resolve_config(args, provider):
    if provider not in PRESETS:
        raise ValueError(f"Unsupported preset: {provider}")
    base, api_format, key_env, default_model = PRESETS[provider]
    prefix = provider.upper()
    config = {
        "provider": provider,
        "model": args.model or os.getenv(prefix + "_MODEL", default_model),
        "base_url": (args.base_url or os.getenv(prefix + "_BASE_URL") or
                     (os.getenv("OLLAMA_URL") if provider == "ollama" else None) or base).rstrip("/"),
        "api_format": args.api_format or os.getenv(prefix + "_API_FORMAT", api_format),
        "api_key_env": args.api_key_env or key_env,
        "temperature": None if args.temperature == "omit" else float(args.temperature),
        "max_tokens": args.max_tokens, "timeout": args.timeout,
        "reasoning_effort": args.reasoning_effort, "token_parameter": args.token_parameter,
    }
    if not config["model"]:
        raise ValueError("Specify --model or " + prefix + "_MODEL.")
    if config["api_format"] not in ("ollama", "chat", "responses"):
        raise ValueError("Unknown API format.")
    if config["reasoning_effort"] and config["api_format"] == "ollama":
        raise ValueError("reasoning-effort is only supported for chat/responses adapters.")
    if config["api_key_env"] and not os.getenv(config["api_key_env"]):
        raise ValueError("Missing environment variable " + config["api_key_env"])
    from urllib.parse import urlsplit
    url = urlsplit(config["base_url"])
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError("Base URL must be HTTP(S), without credentials, query or fragment.")
    if not math.isfinite(config["timeout"]) or config["timeout"] <= 0 or config["max_tokens"] <= 0:
        raise ValueError("Timeout and token limit must be positive.")
    if config["temperature"] is not None and (not math.isfinite(config["temperature"]) or config["temperature"] < 0):
        raise ValueError("Temperature must be a finite nonnegative number or omit.")
    return config


def make_request(config, text):
    messages = build_messages(text)
    fmt = config["api_format"]
    payload = {"model": config["model"]}
    temp = config["temperature"]
    if fmt == "ollama":
        payload.update(messages=messages, stream=False, options={"num_predict": config["max_tokens"]})
        if temp is not None:
            payload["options"]["temperature"] = temp
        route = "/api/chat"
    elif fmt == "responses":
        payload.update(input=messages, max_output_tokens=config["max_tokens"], store=False)
        if temp is not None:
            payload["temperature"] = temp
        if config["reasoning_effort"]:
            payload["reasoning"] = {"effort": config["reasoning_effort"]}
        route = "/responses"
    else:
        payload.update(messages=messages, stream=False)
        payload[config["token_parameter"]] = config["max_tokens"]
        if temp is not None:
            payload["temperature"] = temp
        if config["reasoning_effort"]:
            payload["reasoning_effort"] = config["reasoning_effort"]
        route = "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config["api_key_env"]:
        headers["Authorization"] = "Bearer " + os.environ[config["api_key_env"]]
    return urllib.request.Request(config["base_url"] + route,
                                  data=json.dumps(payload).encode("utf-8"),
                                  headers=headers, method="POST")


def extract_response(data, fmt):
    result = dict(generated_answer="", input_tokens="", output_tokens="",
                  finish_reason="", response_model=data.get("model", ""),
                  error="", error_type="", tokens_per_second="")
    if data.get("error"):
        result.update(error="Provider returned an error object", error_type="api_error")
        return result
    if fmt == "ollama":
        result["generated_answer"] = data["message"].get("content") or ""
        result["input_tokens"] = data.get("prompt_eval_count", "")
        result["output_tokens"] = data.get("eval_count", "")
        result["finish_reason"] = data.get("done_reason", "")
        if data.get("eval_duration") and data.get("eval_count") is not None:
            result["tokens_per_second"] = data["eval_count"] / (data["eval_duration"] / 1e9)
        if result["finish_reason"] == "length":
            result.update(error="Output token limit reached", error_type="truncated")
    elif fmt == "responses":
        texts, refusals = [], []
        for output in data.get("output", []):
            for part in output.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                elif part.get("type") == "refusal":
                    refusals.append(part.get("refusal", ""))
        result["generated_answer"] = "".join(texts)
        result["finish_reason"] = data.get("status", "")
        usage = data.get("usage") or {}
        result["input_tokens"] = usage.get("input_tokens", "")
        result["output_tokens"] = usage.get("output_tokens", "")
        if refusals:
            result.update(error="Structured refusal", error_type="refusal")
        elif data.get("status") != "completed":
            result.update(error="Response did not complete", error_type="truncated" if data.get("status") == "incomplete" else "api_error")
    else:
        choice = data["choices"][0]
        message = choice["message"]
        result["generated_answer"] = message.get("content") or ""
        result["finish_reason"] = choice.get("finish_reason", "")
        usage = data.get("usage") or {}
        result["input_tokens"] = usage.get("prompt_tokens", "")
        result["output_tokens"] = usage.get("completion_tokens", "")
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            result.update(error="Structured refusal", error_type="refusal")
        elif choice.get("finish_reason") == "length":
            result.update(error="Output token limit reached", error_type="truncated")
    if not isinstance(result["generated_answer"], str):
        raise ValueError("Expected text content.")
    return result


def call_model(config, text):
    start = time.perf_counter()
    raw = None
    try:
        with urllib.request.urlopen(make_request(config, text), timeout=config["timeout"]) as response:
            raw = json.load(response)
        result = extract_response(raw, config["api_format"])
    except Exception as exc:
        timeout = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
        # Avoid persisting keys, authorization headers, or arbitrary server error bodies.
        error = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        result = dict(generated_answer="", input_tokens="", output_tokens="",
                      finish_reason="", response_model="", tokens_per_second="",
                      error=error, error_type="timeout" if timeout else "api_error")
    result["latency_ms"] = (time.perf_counter() - start) * 1000
    return result, raw


def run_provider(config, items, output_dir, dataset_path):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = "per_item_" + config["provider"] + "_" + slugify_model_name(config["model"])
    csv_path = output_dir / (stem + ".csv")
    raw_path = output_dir / (stem + ".raw.jsonl")
    meta_path = output_dir / (stem + ".meta.json")
    if any(p.exists() for p in (csv_path, raw_path, meta_path)):
        raise FileExistsError("Results already exist; select a new --results-dir.")
    metadata = dict(config, started_at=datetime.now(timezone.utc).isoformat(),
                    dataset_sha256=hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest(),
                    prompt_sha256=hashlib.sha256(json.dumps(build_messages(""), ensure_ascii=False).encode()).hexdigest(),
                    expected_items=len(items), completed_items=0, status="running")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    errors = 0
    with csv_path.open("x", encoding="utf-8", newline="") as f, raw_path.open("x", encoding="utf-8") as raw_file:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        f.flush()
        for index, item in enumerate(items, 1):
            result, raw = call_model(config, item["text"])
            writer.writerow(dict(provider=config["provider"], model=config["model"],
                                 item_id=item["id"], text=item["text"],
                                 reference_answer=item["label"], **result))
            f.flush()
            raw_file.write(json.dumps({"item_id": item["id"], "response": raw}) + "\n")
            raw_file.flush()
            errors += bool(result["error"])
            metadata["completed_items"] = index
            print(f"{index}/{len(items)} {item['id']}: {result['error_type'] or 'received'}", flush=True)
    metadata.update(status="complete", finished_at=datetime.now(timezone.utc).isoformat())
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(csv_path)
    return errors


def import_chat_answers(path, items, output_dir, model):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    answers = data["answers"]
    if set(answers) != {x["id"] for x in items} or not all(isinstance(x, str) for x in answers.values()):
        raise ValueError("Imported answers must be strings with exactly the dataset IDs.")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / ("per_item_chat_" + slugify_model_name(model) + ".csv")
    with target.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(dict(provider="chat_nonblind", model=model, item_id=item["id"],
                                 text=item["text"], reference_answer=item["label"],
                                 generated_answer=answers[item["id"]]))
    print(target)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", choices=PRESETS, action="append", help="Repeat for multiple presets; otherwise PROVIDERS or ollama.")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-format", choices=["ollama", "chat", "responses"])
    p.add_argument("--api-key-env", help="Name of the environment variable containing the key, never the key itself.")
    p.add_argument("--temperature", default="0", help="Number or omit for unsupported models.")
    p.add_argument("--max-tokens", type=int, default=256)
    p.add_argument("--token-parameter", choices=["max_tokens", "max_completion_tokens"], default="max_tokens")
    p.add_argument("--reasoning-effort")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--items", type=Path, default=ITEMS_PATH)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--import-chat", type=Path)
    return p


def main():
    args = parser().parse_args()
    items = load_items(args.items)
    if args.import_chat:
        if not args.model:
            raise ValueError("--import-chat requires --model for provenance.")
        import_chat_answers(args.import_chat, items, args.results_dir, args.model)
        return
    providers = args.provider or [x.strip() for x in os.getenv("PROVIDERS", "ollama").split(",") if x.strip()]
    if not providers or len(set(providers)) != len(providers):
        raise ValueError("Specify unique provider presets.")
    if len(providers) > 1 and any((args.model, args.base_url, args.api_key_env, args.api_format)):
        raise ValueError("Use per-provider environment settings or run explicit models separately.")
    configs = [resolve_config(args, provider) for provider in providers]
    errors = sum(run_provider(config, items, args.results_dir, args.items) for config in configs)
    if errors:
        raise SystemExit(f"{errors} failed responses recorded; run score.py to count them as wrong.")


if __name__ == "__main__":
    main()
