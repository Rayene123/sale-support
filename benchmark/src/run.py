"""
Run the sentiment classification benchmark with local Ollama.

Required packages:

    pip install ollama python-dotenv

Run:

    python benchmark/src/run.py
"""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

import ollama
from dotenv import load_dotenv

from prompt import build_messages


ROOT = Path(__file__).resolve().parents[1]

ITEMS_PATH = ROOT / "data" / "items.jsonl"
OUTPUT_PATH = ROOT / "results" / "per_item_ollama.csv"

load_dotenv(ROOT.parent / ".env")


def load_items():
    with ITEMS_PATH.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


def get_model() -> str:
    return os.getenv(
        "OLLAMA_MODEL",
        "qwen2.5:14b",
    )


def get_ollama_url() -> str:
    return os.getenv(
        "OLLAMA_URL",
        "http://localhost:11434",
    ).rstrip("/")


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


def main():

    model = get_model()

    items = load_items()

    client = ollama.Client(
        host=get_ollama_url(),
    )

    rows = []

    print()
    print("=" * 60)
    print("Ollama benchmark")
    print(model)
    print("=" * 60)

    for index, item in enumerate(items, start=1):

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
            ) = call_ollama(
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
            "provider": "ollama",
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

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
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
        f"Saved results to: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()