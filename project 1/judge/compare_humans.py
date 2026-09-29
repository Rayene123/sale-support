"""Compare saved judge scores with new human labels without calling a model."""
import argparse
import hashlib
import json
from pathlib import Path

from .run import PROJECT, load_inputs, read_jsonl, summarize, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Completed judge run directory")
    parser.add_argument("--dataset", type=Path, default=PROJECT / "data/dev.jsonl")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--labels-reviewed", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="New JSON output file")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Output exists; choose a new file")
        metadata = json.loads((args.run / "metadata.json").read_text(encoding="utf-8"))
        if metadata["input_hashes"]["dataset"] != hashlib.sha256(args.dataset.read_bytes()).hexdigest():
            raise ValueError("Dataset differs from the saved evaluation")
        results_path = args.run / "results.jsonl"
        _, labels, _ = load_inputs(args.dataset, args.labels, results_path)
        records = read_jsonl(results_path)
        matching = sum((r["item_id"], r["response_id"]) in labels for r in records)
        if not matching:
            raise ValueError("No labels match these exact system replies")
        report = summarize(records, labels, args.labels_reviewed)
        report["judge_run"] = str(args.run)
        report["human_labels_sha256"] = hashlib.sha256(args.labels.read_bytes()).hexdigest()
        write_json(args.output, report)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Saved comparison for {matching} labeled replies to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
