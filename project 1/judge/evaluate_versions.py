"""Compare Person 4's saved versions using the same local judge."""
import argparse
import json
import urllib.request
from pathlib import Path

from .client import Judge
from .run import PROJECT, load_inputs, main as run_judge, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args(argv)
    judge = Judge()
    if judge.provider != "ollama":
        parser.error("This evaluation uses local Ollama; set JUDGE_PROVIDER=ollama")
    # Check all inputs and local availability before starting a long batch.
    versions = {}
    for version in ("v1", "v2", "v3"):
        path = PROJECT / f"results/baseline_{version}.jsonl"
        items, _, responses = load_inputs(PROJECT / "data/dev.jsonl", PROJECT / "data/human_labels.jsonl", path)
        if {r["item_id"] for r in responses} != set(items):
            parser.error(f"{version} does not cover the entire development set")
        versions[version] = (path, {r["item_id"]: r for r in responses})
    try:
        with urllib.request.urlopen(judge.base + "/api/tags", timeout=10) as response:
            models = json.load(response)["models"]
        if judge.model not in {m["name"] for m in models}:
            parser.error(f"Local model {judge.model} is not installed")
    except (OSError, ValueError, KeyError) as exc:
        parser.error(f"Ollama availability check failed: {exc}")
    if args.output.exists():
        parser.error("Output path exists; choose a new directory")
    args.output.mkdir(parents=True)
    # Deterministic screening sample, one differing pair per category first.
    candidates = [k for k in items if versions["v1"][1][k]["response_text"] != versions["v3"][1][k]["response_text"]]
    selected, categories = [], set()
    for key in candidates:
        category = items[key].get("category")
        if category not in categories:
            selected.append(key)
            categories.add(category)
    selected = (selected + [k for k in candidates if k not in selected])[:10]
    (args.output / "inputs").mkdir()
    (args.output / "archive").mkdir()
    pairs = args.output / "inputs" / "position_pairs.jsonl"
    with pairs.open("x", encoding="utf-8") as stream:
        for key in selected:
            stream.write(json.dumps({"item_id": key, "answer_a": versions["v1"][1][key]["response_text"],
                                     "answer_b": versions["v3"][1][key]["response_text"]}, ensure_ascii=False) + "\n")
    comparison, failed = {}, False
    for version, (path, _) in versions.items():
        output = args.output / version
        options = ["--responses", str(path), "--output", str(output),
                   "--snapshot-dir", str(args.output / "snapshot")]
        if version == "v3":
            options += ["--verbosity-limit", "10"]
            if selected:
                options += ["--pairs", str(pairs)]
        failed |= bool(run_judge(options))
        report = json.loads((output / "reliability.json").read_text(encoding="utf-8"))
        comparison[version] = {k: report[k] for k in ("successful_responses", "failed_responses", "unlabeled_responses", "quality", "position_bias", "verbosity_bias")}
        write_json(args.output / "archive" / f"comparison_{version}.json", comparison[version])
    write_json(args.output / "comparison.json", {
        "versions": comparison,
        "human_validation": "Pending: existing seeded labels cover reference answers, not these system replies.",
        "bias_sample": "First ten distinct v1/v3 pairs, covering categories first; screening only. Padding requires review.",
        "dataset": "40 development items; no final test-set evaluation performed."})
    from .readable import main as write_readable
    # Test doubles and interrupted runs may not have full evidence files.
    if all((args.output / v / "results.jsonl").exists() for v in versions):
        write_readable(["--run", str(args.output)])
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
