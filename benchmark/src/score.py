"""Provider-independent sentiment scoring; raw CSVs are never rewritten."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
from run import ITEMS_PATH, RESULTS_DIR, LABELS, load_items

VALID_LABELS = LABELS


def normalize_answer(value):
    return (value or "").strip().lower()


def percentile(values, p):
    if not values:
        return ""
    values = sorted(values)
    pos = (len(values) - 1) * p
    low = int(pos)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (pos - low)


def score_file(path, items=None):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"provider", "model", "item_id", "text", "reference_answer", "generated_answer"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing required columns: {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty result file: {path}")
    seen = set()
    expected = {item["id"]: item for item in items} if items is not None else None
    kinds = {"parse_errors": 0, "execution_errors": 0, "refusals": 0, "timeouts": 0, "truncations": 0}
    correct, latencies = 0, []
    for row in rows:
        identifier = row["item_id"]
        if identifier in seen:
            raise ValueError(f"Duplicate item {identifier}: {path}")
        seen.add(identifier)
        if (row["provider"], row["model"]) != (rows[0]["provider"], rows[0]["model"]):
            raise ValueError("Each per-item file must contain one provider/model.")
        if expected is not None:
            item = expected.get(identifier)
            if not item or (row["text"], row["reference_answer"]) != (item["text"], item["label"]):
                raise ValueError(f"Dataset mismatch for {identifier}: {path}")
        reference = normalize_answer(row["reference_answer"])
        if reference not in LABELS:
            raise ValueError(f"Invalid reference label for {identifier}")
        if row.get("latency_ms"):
            latency = float(row["latency_ms"])
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("Latency must be finite and nonnegative.")
            latencies.append(latency)
        answer = normalize_answer(row["generated_answer"])
        error_type = row.get("error_type", "")
        if row.get("error") or error_type:
            field = {"refusal": "refusals", "timeout": "timeouts", "truncated": "truncations"}.get(error_type, "execution_errors")
            kinds[field] += 1
            row["correct"] = "0"
        elif answer not in LABELS:
            kinds["parse_errors"] += 1
            row["correct"] = "0"
        else:
            row["correct"] = str(int(answer == reference))
            correct += int(row["correct"])
    total = len(expected) if expected is not None else len(rows)
    missing = total - len(rows)
    summary = dict(provider=rows[0]["provider"], model=rows[0]["model"],
                   items=total, recorded_items=len(rows), missing_items=missing,
                   correct=correct, accuracy=correct / total, **kinds,
                   p50_latency_ms=percentile(latencies, .5),
                   p95_latency_ms=percentile(latencies, .95), latency_samples=len(latencies))
    for key in ("input_tokens", "output_tokens"):
        known = [int(row[key]) for row in rows if row.get(key) not in (None, "")]
        if any(x < 0 for x in known):
            raise ValueError("Token counts must be nonnegative.")
        summary[key] = sum(known) if len(known) == len(rows) and not missing else ""
        summary["recorded_" + key] = sum(known) if known else ""
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--items", type=Path, default=ITEMS_PATH)
    p.add_argument("--output", type=Path, help="Defaults to RESULTS_DIR/summary.csv.")
    args = p.parse_args()
    items = load_items(args.items)
    paths = sorted(args.results_dir.glob("per_item_*.csv"))
    if not paths:
        raise ValueError("No per_item_*.csv files found.")
    summaries = [dict(score_file(path, items), result_file=path.name) for path in paths]
    output = args.output or args.results_dir / "summary.csv"
    if output.resolve() in [path.resolve() for path in paths] or output.resolve() == args.items.resolve():
        raise ValueError("Summary output cannot overwrite source data.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    for result in summaries:
        print(f"{result['provider']} / {result['model']}: {result['correct']}/{result['items']} ({result['accuracy']:.2%}), missing={result['missing_items']}")
    print(output)


if __name__ == "__main__":
    main()
