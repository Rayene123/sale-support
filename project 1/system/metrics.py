import json
import statistics
import sys
from pathlib import Path


RESULT_FILES = [
    ("v1", Path(__file__).resolve().parent.parent / "results" / "baseline_v1.jsonl"),
    ("v2", Path(__file__).resolve().parent.parent / "results" / "baseline_v2.jsonl"),
    ("v3", Path(__file__).resolve().parent.parent / "results" / "baseline_v3.jsonl"),
]


def load_results(path):
    results = []

    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return results

    # Detect UTF-8 / UTF-16 automatically.
    raw = path.read_bytes()

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        encoding = "utf-16"
    else:
        encoding = "utf-8-sig"

    text = raw.decode(encoding)

    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()

        if not line:
            continue

        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(
                f"WARNING: invalid JSON in {path.name}, "
                f"line {line_number}: {e}",
                file=sys.stderr,
            )

    return results

def calculate_metrics(results):
    total_cases = len(results)

    errors = [
        r for r in results
        if "error" in r
    ]

    successful = [
        r for r in results
        if "error" not in r
        and isinstance(r.get("latency_ms"), (int, float))
    ]

    latencies = [
        r["latency_ms"]
        for r in successful
    ]

    prompt_tokens = [
        r.get("prompt_tokens", 0)
        for r in successful
    ]

    completion_tokens = [
        r.get("completion_tokens", 0)
        for r in successful
    ]

    total_tokens = [
        r.get("total_tokens", 0)
        for r in successful
    ]

    def avg(values):
        return sum(values) / len(values) if values else 0

    def median(values):
        return statistics.median(values) if values else 0

    def percentile(values, p):
        if not values:
            return 0

        values = sorted(values)

        index = (len(values) - 1) * p
        lower = int(index)
        upper = min(lower + 1, len(values))

        if lower == upper:
            return values[lower]

        weight = index - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    return {
        "cases": total_cases,
        "successful": len(successful),
        "errors": len(errors),

        "avg_latency_ms": avg(latencies),
        "median_latency_ms": median(latencies),
        "p95_latency_ms": percentile(latencies, 0.95),

        "total_prompt_tokens": sum(prompt_tokens),
        "avg_prompt_tokens": avg(prompt_tokens),

        "total_completion_tokens": sum(completion_tokens),
        "avg_completion_tokens": avg(completion_tokens),

        "total_tokens": sum(total_tokens),
        "avg_total_tokens": avg(total_tokens),
        "median_total_tokens": median(total_tokens),
    }


def print_table(all_metrics):
    headers = [
        "Version",
        "Cases",
        "Errors",
        "Avg Latency",
        "Median Latency",
        "P95 Latency",
        "Avg Prompt",
        "Avg Completion",
        "Avg Total",
        "Total Tokens",
    ]

    rows = []

    for version, metrics in all_metrics.items():
        rows.append([
            version,
            metrics["cases"],
            metrics["errors"],
            f'{metrics["avg_latency_ms"]:.2f}',
            f'{metrics["median_latency_ms"]:.2f}',
            f'{metrics["p95_latency_ms"]:.2f}',
            f'{metrics["avg_prompt_tokens"]:.2f}',
            f'{metrics["avg_completion_tokens"]:.2f}',
            f'{metrics["avg_total_tokens"]:.2f}',
            metrics["total_tokens"],
        ])

    widths = [
        max(len(headers[i]), max(len(str(row[i])) for row in rows))
        for i in range(len(headers))
    ]

    separator = "-+-".join("-" * width for width in widths)

    print()
    print("PROMPT EXPERIMENT METRICS")
    print("=" * len(separator))

    print(" | ".join(
        headers[i].ljust(widths[i])
        for i in range(len(headers))
    ))

    print(separator)

    for row in rows:
        print(" | ".join(
            str(row[i]).ljust(widths[i])
            for i in range(len(row))
        ))

    print()


def main():
    all_metrics = {}

    for version, path in RESULT_FILES:
        results = load_results(path)

        if not results:
            continue

        all_metrics[version] = calculate_metrics(results)

    if not all_metrics:
        print("ERROR: No result files found.", file=sys.stderr)
        sys.exit(1)

    print_table(all_metrics)


if __name__ == "__main__":
    main()