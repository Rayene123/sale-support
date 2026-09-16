"""
Score the sentiment classification benchmark.

A prediction is correct only when the normalized model output
is exactly one of the four labels and matches the reference.
"""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RESULTS_DIR = ROOT / "results"

SUMMARY_PATH = RESULTS_DIR / "summary.csv"

VALID_LABELS = {
    "positive",
    "negative",
    "neutral",
    "mixed",
}


def find_result_files() -> list[Path]:
    """
    Discover all per-item result files produced by run.py.

    run.py writes one file per provider/model combination, named
    "per_item_<provider>_<model-slug>.csv". We glob for that pattern
    instead of hardcoding provider-specific filenames, so scoring
    automatically picks up any provider/model that was benchmarked.
    """
    if not RESULTS_DIR.exists():
        return []

    return sorted(
        path
        for path in RESULTS_DIR.glob("per_item_*.csv")
        if path.name != SUMMARY_PATH.name
    )


def normalize_answer(value: str) -> str:
    value = (value or "").strip().lower()

    # Remove surrounding whitespace only.
    # Anything other than an exact label remains wrong.
    return value


def score_file(path: Path):

    if not path.exists():
        return None

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        rows = list(csv.DictReader(file))

    if not rows:
        return None

    correct = 0
    parse_errors = 0
    execution_errors = 0

    latencies = []

    for row in rows:

        reference = normalize_answer(
            row["reference_answer"]
        )

        generated = normalize_answer(
            row["generated_answer"]
        )

        if row.get("error"):
            parse_errors += 1
            row["correct"] = "0"
            continue

        if generated not in VALID_LABELS:
            parse_errors += 1
            row["correct"] = "0"
            continue

        if generated == reference:
            correct += 1
            row["correct"] = "1"
        else:
            row["correct"] = "0"

        if row.get("latency_ms"):
            latencies.append(
                float(row["latency_ms"])
            )

    total = len(rows)

    accuracy = (
        correct / total
        if total
        else 0
    )

    latencies.sort()

    def percentile(values, percentile):
        if not values:
            return ""

        index = (
            (len(values) - 1)
            * percentile
        )

        lower = int(index)
        upper = min(
            lower + 1,
            len(values) - 1,
        )

        fraction = index - lower

        return (
            values[lower]
            + (
                values[upper]
                - values[lower]
            )
            * fraction
        )

    p50 = percentile(
        latencies,
        0.50,
    )

    p95 = percentile(
        latencies,
        0.95,
    )

    input_tokens = sum(
        int(row["input_tokens"])
        for row in rows
        if row.get("input_tokens")
    )

    output_tokens = sum(
        int(row["output_tokens"])
        for row in rows
        if row.get("output_tokens")
    )

    # Rewrite the per-item file with the correct column.
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        fieldnames = list(rows[0].keys())

        if "correct" not in fieldnames:
            fieldnames.append("correct")

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    return {
        "provider": rows[0]["provider"],
        "model": rows[0]["model"],
        "items": total,
        "correct": correct,
        "accuracy": accuracy,
        "parse_errors": parse_errors,
        "execution_errors": execution_errors,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def main():

    summaries = []

    for path in find_result_files():

        result = score_file(path)

        if result:
            summaries.append(result)

    if not summaries:
        raise RuntimeError(
            "No benchmark result files found."
        )

    SUMMARY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with SUMMARY_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        fieldnames = [
            "provider",
            "model",
            "items",
            "correct",
            "accuracy",
            "parse_errors",
            "execution_errors",
            "p50_latency_ms",
            "p95_latency_ms",
            "input_tokens",
            "output_tokens",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(summaries)

    print()
    print("=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    for result in summaries:

        print()
        print(
            f"{result['provider']} / "
            f"{result['model']}"
        )

        print(
            f"Accuracy: "
            f"{result['correct']}/"
            f"{result['items']} "
            f"({result['accuracy']:.2%})"
        )

        if result["p50_latency_ms"] != "":
            print(
                f"P50 latency: "
                f"{result['p50_latency_ms']:.2f} ms"
            )

        if result["p95_latency_ms"] != "":
            print(
                f"P95 latency: "
                f"{result['p95_latency_ms']:.2f} ms"
            )

        print(
            f"Parse errors: "
            f"{result['parse_errors']}"
        )

    print()
    print(
        f"Saved summary to: {SUMMARY_PATH}"
    )


if __name__ == "__main__":
    main()