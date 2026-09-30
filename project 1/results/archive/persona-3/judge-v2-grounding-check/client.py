"""Small standard-library client for local Ollama or optional Groq."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMITS = {"factual_correctness": 2, "completeness": 2,
          "no_hallucination": 2, "relevance": 1, "professional_tone": 1}


class JudgeError(Exception):
    def __init__(self, kind, message, metadata=None):
        super().__init__(message)
        self.kind = kind
        self.metadata = metadata or {}


def validate_scores(value, reason=True):
    required = set(LIMITS) | {"total"} | ({"reason"} if reason else set())
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Incorrect score fields")
    for key, maximum in {**LIMITS, "total": 8}.items():
        if type(value[key]) is not int or not 0 <= value[key] <= maximum:
            raise ValueError(f"Invalid integer score: {key}")
    if value["total"] != sum(value[k] for k in LIMITS):
        raise ValueError("Total does not match criterion scores")
    if reason and (not isinstance(value["reason"], str) or not value["reason"].strip()):
        raise ValueError("Missing explanation")
    return value


def settings():
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, sep, value = line.partition("=")
                if not sep:
                    raise ValueError("Invalid .env line; expected NAME=value")
                values[key.strip()] = value.strip().strip("\"'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("JUDGE_")})
    return values


class Judge:
    def __init__(self, config=None):
        config = settings() if config is None else config
        self.provider = config.get("JUDGE_PROVIDER", "ollama").strip().lower()
        if self.provider not in ("ollama", "groq"):
            raise JudgeError("configuration", "JUDGE_PROVIDER must be ollama or groq.")
        self.key = config.get("JUDGE_API_KEY", "").strip()
        if self.provider == "groq" and not self.key:
            raise JudgeError("configuration", "Set JUDGE_API_KEY to use the optional Groq provider.")
        default_base = "http://localhost:11434" if self.provider == "ollama" else "https://api.groq.com/openai/v1"
        self.base = config.get("JUDGE_BASE_URL", default_base).rstrip("/")
        if self.provider == "ollama":
            if not self.base.startswith(("http://localhost", "http://127.0.0.1")):
                raise JudgeError("configuration", "Local Ollama must use localhost or 127.0.0.1.")
        elif not self.base.startswith("https://"):
            raise JudgeError("configuration", "Groq JUDGE_BASE_URL must use HTTPS.")
        self.model = config.get("JUDGE_MODEL", "qwen3:14b" if self.provider == "ollama" else "openai/gpt-oss-20b")
        self.timeout = float(config.get("JUDGE_TIMEOUT", "120"))
        self.max_tokens = int(config.get("JUDGE_MAX_TOKENS", "2048"))
        if self.timeout <= 0 or self.max_tokens < 1 or not self.model.strip():
            raise JudgeError("configuration", "Model, positive timeout and positive token limit are required.")
        self.prompt_version = config.get("JUDGE_PROMPT_VERSION", "judge_v2")
        if self.prompt_version not in ("judge_v1", "judge_v2"):
            raise JudgeError("configuration", "JUDGE_PROMPT_VERSION must be judge_v1 or judge_v2.")
        self.prompt = (ROOT / "prompts" / f"{self.prompt_version}.txt").read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.prompt.encode()).hexdigest()

    def _request(self, prompt, data):
        messages = [{"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]
        if self.provider == "ollama":
            body = {"model": self.model, "stream": False, "format": "json", "think": False, "messages": messages,
                    "options": {"temperature": 0, "num_predict": self.max_tokens}}
            endpoint = self.base + "/api/chat"
            headers = {"Content-Type": "application/json"}
        else:
            body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                    "response_format": {"type": "json_object"}, "messages": messages}
            endpoint = self.base + "/chat/completions"
            headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}
        request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.load(response)
        except urllib.error.HTTPError as exc:
            if self.provider == "ollama" and exc.code == 404:
                raise JudgeError("model_missing", f"Local model {self.model!r} is missing; install it with ollama pull {self.model}.") from None
            raise JudgeError("api", f"Provider returned HTTP {exc.code}; check access, limits, and settings.") from None
        except (TimeoutError, urllib.error.URLError) as exc:
            kind = "timeout" if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError) else "network"
            raise JudgeError(kind, "Request failed; no automatic retry was made.") from None
        except (ValueError, UnicodeError):
            raise JudgeError("invalid_output", "Provider returned invalid JSON.") from None
        metadata = {"latency_ms": (time.perf_counter() - started) * 1000,
                    "usage": raw.get("usage") if self.provider == "groq" and isinstance(raw, dict) else ({"prompt_tokens": raw.get("prompt_eval_count"), "completion_tokens": raw.get("eval_count")} if self.provider == "ollama" and isinstance(raw, dict) else None),
                    "response_model": raw.get("model") if isinstance(raw, dict) else None,
                    "raw_response": raw}
        try:
            if self.provider == "ollama":
                if not raw.get("done"):
                    raise JudgeError("incomplete", "Judge response did not finish normally.", metadata)
                content = raw["message"]["content"]
            else:
                choice = raw["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise JudgeError("incomplete", "Judge response did not finish normally.", metadata)
                if choice["message"].get("refusal"):
                    raise JudgeError("refusal", "Judge refused the evaluation.", metadata)
                content = choice["message"]["content"]
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise JudgeError("invalid_output", "Missing or invalid judge JSON.", metadata) from None
        return result, metadata

    def grade(self, customer_message, order_context, response_text):
        """Person 2 interface: returns scores, reason, and request metadata."""
        if not isinstance(customer_message, str) or not customer_message.strip() or not isinstance(order_context, dict) or not isinstance(response_text, str):
            raise JudgeError("input", "Expected a customer message, context object, and response string.")
        result, metadata = self._request(self.prompt, {
            "customer_message": customer_message, "order_context": order_context,
            "response_text": response_text})
        try:
            validate_scores(result)
        except ValueError as exc:
            raise JudgeError("invalid_output", str(exc), metadata) from None
        return {"scores": {k: result[k] for k in [*LIMITS, "total"]},
                "reason": result["reason"], "prompt_version": self.prompt_version,
                "prompt_sha256": self.prompt_hash, **metadata}

    def prefer(self, item, answer_a, answer_b):
        prompt = self.prompt.replace("Return ONLY a JSON object with exactly these keys: factual_correctness, completeness, no_hallucination, relevance, professional_tone, total, reason.", "PAIRWISE MODE: return only JSON with exactly winner and reason fields.") + '\nIn pairwise mode choose winner A, B, or tie. Prefer the reply with the higher rubric total; ties are allowed. Ignore answer order and length.'
        result, metadata = self._request(prompt, {
            "customer_message": item["customer_message"], "order_context": item["order_context"],
            "answer_A": answer_a, "answer_B": answer_b})
        if not isinstance(result, dict) or set(result) != {"winner", "reason"} or result["winner"] not in ("A", "B", "tie") or not isinstance(result["reason"], str) or not result["reason"].strip():
            raise JudgeError("invalid_output", "Invalid pairwise verdict", metadata)
        return {**result, **metadata}
