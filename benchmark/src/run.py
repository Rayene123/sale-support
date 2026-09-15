"""
Run the sentiment classification benchmark with Groq.

Required packages:

    pip install openai python-dotenv

Run:

    python benchmark/src/run.py
"""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from prompt import build_messages


ROOT = Path(__file__).resolve().parents[1]

ITEMS_PATH = ROOT / "data" / "items.jsonl"
OUTPUT_PATH = ROOT / "results" / "per_item.csv"

load_dotenv(ROOT.parent / ".env")


def load_items():
    with ITEMS_PATH.open("r", encoding="utf-8") as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


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

    usage = response.usage

    input_tokens = getattr(
        usage,
        "prompt_tokens",
        None,
    )

    output_tokens = getattr(
        usage,
        "completion_tokens",
        None,
    )

    return (
        output,
        latency_ms,
        input_tokens,
        output_tokens,
    )


def main():

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    if not model:
        raise RuntimeError(
            "GROQ_MODEL is not configured."
        )

    items = load_items()

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    rows = []

    print()
    print("=" * 60)
    print("Groq benchmark")
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
            ) = call_groq(
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
            "provider": "groq",
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