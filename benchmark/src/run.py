"""
Run the sentiment classification benchmark with multiple providers.

Currently supported:
    - Groq
    - Ollama

Required packages:

    pip install ollama openai python-dotenv

Run:

    python benchmark/src/run.py

Example .env:

    PROVIDERS=groq,ollama

    GROQ_API_KEY=your_groq_api_key
    GROQ_MODEL=openai/gpt-oss-20b

    OLLAMA_MODEL=tinyllama:1.1b
    OLLAMA_URL=http://localhost:11434
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

import ollama
from dotenv import load_dotenv
from openai import OpenAI

from prompt import build_messages


ROOT = Path(__file__).resolve().parents[1]

ITEMS_PATH = ROOT / "data" / "items.jsonl"
RESULTS_DIR = ROOT / "results"

load_dotenv(ROOT.parent / ".env")


def load_items() -> list[dict]:
    with ITEMS_PATH.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


def get_providers() -> list[str]:
    """
    Read providers from .env.

    Example:
        PROVIDERS=groq,ollama

    If PROVIDERS is not specified, default to Ollama.
    """
    value = os.getenv("PROVIDERS", "ollama")

    return [
        provider.strip().lower()
        for provider in value.split(",")
        if provider.strip()
    ]


def slugify_model_name(model: str) -> str:
    """
    Turn a model identifier into something safe to use in a filename.

    Example:
        "openai/gpt-oss-20b" -> "openai-gpt-oss-20b"
        "qwen2.5:14b"        -> "qwen2.5-14b"
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model)
    slug = slug.strip("-")

    return slug or "unknown-model"


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

def get_groq_model() -> str:
    return os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-20b",
    )


def create_groq_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing from .env"
        )

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )


def call_groq(
    client: OpenAI,
    model: str,
    text: str,
):
    start = time.perf_counter()

    response = client.chat.completions.create(
        model=model,
        messages=build_messages(text),
        temperature=0,
        max_tokens=256,
    )

    latency_ms = (
        time.perf_counter() - start
    ) * 1000

    output = (
        response.choices[0].message.content
        or ""
    )

    input_tokens = None
    output_tokens = None

    if response.usage:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return (
        output,
        latency_ms,
        input_tokens,
        output_tokens,
    )


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def get_ollama_model() -> str:
    return os.getenv(
        "OLLAMA_MODEL",
        "qwen2.5:14b",
    )


def get_ollama_url() -> str:
    return os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434",
    ).rstrip("/")


def create_ollama_client() -> ollama.Client:
    return ollama.Client(
        host=get_ollama_url(),
    )


def call_ollama(
    client: ollama.Client,
    model: str,
    text: str,
):
    start = time.perf_counter()

    response = client.chat(
        model=model,
        messages=build_messages(text),
        options={
            "temperature": 0,
            "num_predict": 256,
        },
    )

    latency_ms = (
        time.perf_counter() - start
    ) * 1000

    output = (
        response["message"]["content"]
        or ""
    )

    input_tokens = response.get(
        "prompt_eval_count",
    )

    output_tokens = response.get(
        "eval_count",
    )

    return (
        output,
        latency_ms,
        input_tokens,
        output_tokens,
    )


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_provider(
    provider: str,
    items: list[dict],
):
    if provider == "groq":

        model = get_groq_model()
        client = create_groq_client()

        call_model = call_groq

    elif provider == "ollama":

        model = get_ollama_model()
        client = create_ollama_client()

        call_model = call_ollama

    else:

        raise ValueError(
            f"Unsupported provider: {provider}"
        )

    output_path = (
        RESULTS_DIR
        / f"per_item_{provider}_{slugify_model_name(model)}.csv"
    )

    print()
    print("=" * 60)
    print(f"{provider.upper()} BENCHMARK")
    print(f"Model: {model}")
    print("=" * 60)

    rows = []

    for index, item in enumerate(
        items,
        start=1,
    ):

        print(
            f"{index}/{len(items)} "
            f"{item['id']}",
            end=" ... ",
            flush=True,
        )

        generated_answer = ""
        latency_ms = ""
        input_tokens = ""
        output_tokens = ""
        error = ""

        try:

            (
                generated_answer,
                latency_ms,
                input_tokens,
                output_tokens,
            ) = call_model(
                client,
                model,
                item["text"],
            )

            print("OK")

        except Exception as exc:

            error = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print("ERROR")

        rows.append({
            "provider": provider,
            "model": model,
            "item_id": item["id"],
            "text": item["text"],
            "reference_answer": item["label"],
            "generated_answer": generated_answer,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error": error,
        })

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        fieldnames = [
            "provider",
            "model",
            "item_id",
            "text",
            "reference_answer",
            "generated_answer",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "error",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print(
        f"Saved results to: {output_path}"
    )


def main():

    providers = get_providers()
    items = load_items()

    print()
    print("=" * 60)
    print("SENTIMENT BENCHMARK")
    print("=" * 60)
    print(
        f"Providers: {', '.join(providers)}"
    )
    print(
        f"Items: {len(items)}"
    )

    for provider in providers:

        try:

            run_provider(
                provider,
                items,
            )

        except Exception as exc:

            print()
            print(
                f"Failed to run {provider}: "
                f"{type(exc).__name__}: {exc}"
            )


if __name__ == "__main__":
    main()