"""Run from project 1 with: python -m judge.run --help"""
import argparse
import hashlib
import itertools
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .client import Judge, JudgeError, LIMITS, validate_scores

PROJECT = Path(__file__).resolve().parents[1]
PADDING = " Thank you for contacting us. We appreciate your time. Please let us know if you have any other questions."


def read_jsonl(path):
    rows = []
    path = Path(path)
    content = path.read_bytes()
    encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    for number, line in enumerate(content.decode(encoding).splitlines(), 1):
        if not line.strip():
            raise ValueError(f"{path}:{number}: empty record")
        try:
            row = json.loads(line)
        except ValueError:
            raise ValueError(f"{path}:{number}: invalid JSON") from None
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{number}: expected an object")
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no records")
    return rows


def load_inputs(dataset_path, labels_path, responses_path=None):
    items = {}
    for row in read_jsonl(dataset_path):
        if not isinstance(row.get("id"), str) or not row["id"] or row["id"] in items:
            raise ValueError("Dataset IDs must be nonempty and unique")
        if not isinstance(row.get("customer_message"), str) or not row["customer_message"].strip() or not isinstance(row.get("order_context"), dict):
            raise ValueError(f"Invalid dataset input: {row['id']}")
        items[row["id"]] = row
    labels = defaultdict(list)
    seen = set()
    for row in read_jsonl(labels_path):
        for field in ("item_id", "response_id", "response_text", "evaluator_id"):
            if not isinstance(row.get(field), str) or (field != "response_text" and not row[field]):
                raise ValueError(f"Invalid label field: {field}")
        validate_scores(row.get("scores"), reason=False)
        key = (row["item_id"], row["response_id"])
        identity = (*key, row["evaluator_id"])
        if identity in seen:
            raise ValueError(f"Duplicate evaluator label: {identity}")
        seen.add(identity)
        if labels[key] and labels[key][0]["response_text"] != row["response_text"]:
            raise ValueError(f"Different response text for {key}")
        labels[key].append(row)
    responses = []
    if responses_path:
        response_keys = set()
        responses_path = Path(responses_path)
        for row in read_jsonl(responses_path):
            # Accept both this judge's normalized schema and Person 4's saved
            # system-run schema (id/response, currently written as UTF-16).
            item_id = row.get("item_id", row.get("id"))
            response_text = row.get("response_text", row.get("response"))
            response_id = row.get("response_id", responses_path.stem)
            if any(not isinstance(v, str) or not v for v in (item_id, response_id)) or not isinstance(response_text, str):
                raise ValueError("Responses require item_id/ id and response_text/ response")
            row = {**row, "item_id": item_id, "response_id": response_id, "response_text": response_text}
            key = (item_id, response_id)
            if row["item_id"] not in items or key in response_keys:
                raise ValueError(f"Unknown item or duplicate response: {key}")
            if key in labels and labels[key][0]["response_text"] != row["response_text"]:
                raise ValueError(f"Human label refers to different text: {key}")
            response_keys.add(key)
            responses.append(row)
    else:
        responses = [{k: group[0][k] for k in ("item_id", "response_id", "response_text")}
                     for key, group in labels.items() if key[0] in items]
    if not responses:
        raise ValueError("No responses matched this dataset")
    return items, labels, responses


def agreement(pairs):
    metrics = {}
    for field in [*LIMITS, "total"]:
        differences = [abs(a[field] - b[field]) for a, b in pairs]
        n = len(differences)
        count = differences.count(0)
        metrics[field] = {"comparisons": n, "agreements": count,
                          "disagreements": n - count,
                          "agreement_percent": 100 * count / n if n else None,
                          "mean_absolute_difference": sum(differences) / n if n else None}
    return metrics


def summarize(records, labels, reviewed=False):
    judge_pairs = defaultdict(list)
    human_pairs = []
    major = []
    comparisons = []
    for row in records:
        key = (row["item_id"], row["response_id"])
        group = labels.get(key, [])
        human_pairs.extend((a["scores"], b["scores"]) for a, b in itertools.combinations(group, 2))
        if row["status"] != "ok":
            continue
        for label in group:
            scores = row["result"]["scores"]
            judge_pairs[label["evaluator_id"]].append((label["scores"], scores))
            comparisons.append({"item_id": key[0], "response_id": key[1],
                "evaluator_id": label["evaluator_id"], "human_scores": label["scores"],
                "judge_scores": scores,
                "differences_judge_minus_human": {k: scores[k] - label["scores"][k] for k in [*LIMITS, "total"]}})
            if abs(scores["total"] - label["scores"]["total"]) >= 2:
                major.append({"item_id": key[0], "response_id": key[1],
                              "evaluator_id": label["evaluator_id"],
                              "human_total": label["scores"]["total"], "judge_total": scores["total"],
                              "judge_reason": row["result"]["reason"],
                              "human_reason": label.get("explanation", "")})
    successful = sum(r["status"] == "ok" for r in records)
    total_pairs = sum(len(p) for p in judge_pairs.values())
    return {"label_status": "independently_reviewed_user_attestation" if reviewed else "seeded_unverified",
            "attempted_responses": len(records), "successful_responses": successful,
            "failed_responses": len(records) - successful,
            "unlabeled_responses": sum((r["item_id"], r["response_id"]) not in labels for r in records),
            "human_agreement": agreement(human_pairs),
            "judge_agreement_by_evaluator": {k: agreement(v) for k, v in judge_pairs.items()},
            "major_disagreement_threshold": 2, "major_disagreement_count": len(major),
            "major_disagreement_percent": 100 * len(major) / total_pairs if total_pairs else None,
            "major_disagreements": major,
            "per_response_comparisons": comparisons,
            "note": "Agreement excludes failed API calls; coverage is reported separately. Compare each evaluator separately; no arbitrary consensus is invented. Seeded labels do not establish human reliability."}


def safe_call(function, *args):
    started = time.perf_counter()
    try:
        return {"status": "ok", "result": function(*args)}
    except JudgeError as exc:
        return {"status": "error", "error_type": exc.kind, "error": str(exc),
                "latency_ms": (time.perf_counter() - started) * 1000, **exc.metadata}


def canonical_winner(winner, swapped=False):
    if winner == "tie":
        return winner
    return {"A": "B", "B": "A"}[winner] if swapped else winner


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=PROJECT / "data/dev.jsonl")
    parser.add_argument("--labels", type=Path, default=PROJECT / "data/human_labels.jsonl")
    parser.add_argument("--responses", type=Path, help="Optional actual system replies as JSONL")
    parser.add_argument("--pairs", type=Path, help="Reviewed bias pairs: item_id, answer_a, answer_b")
    parser.add_argument("--limit", type=int, help="Limit graded responses for a pilot")
    parser.add_argument("--verbosity-limit", type=int, default=0)
    parser.add_argument("--labels-reviewed", action="store_true", help="Assert that labels were independently human reviewed")
    parser.add_argument("--output", type=Path, required=True, help="New run directory; existing paths are refused")
    args = parser.parse_args(argv)
    if (args.limit is not None and args.limit < 1) or args.verbosity_limit < 0:
        parser.error("Limits must be positive (--verbosity-limit may be zero)")
    try:
        items, labels, responses = load_inputs(args.dataset, args.labels, args.responses)
        pairs = read_jsonl(args.pairs) if args.pairs else []
        for pair in pairs:
            if not isinstance(pair.get("item_id"), str) or pair["item_id"] not in items or any(not isinstance(pair.get(k), str) or not pair[k].strip() for k in ("answer_a", "answer_b")):
                raise ValueError("Each pair needs a known item_id and two nonempty answer strings")
            if pair["answer_a"] == pair["answer_b"]:
                raise ValueError("Position pairs must contain distinct replies")
        judge = Judge()
        if args.output.exists():
            raise ValueError("Output path exists; choose a new run directory")
        args.output.mkdir(parents=True)
    except (ValueError, OSError, JudgeError) as exc:
        parser.error(str(exc))
    paths = {"dataset": args.dataset, "labels": args.labels,
             "responses": args.responses, "pairs": args.pairs}
    write_json(args.output / "metadata.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(), "model": judge.model,
        "base_url": judge.base, "temperature": 0, "max_tokens": judge.max_tokens,
        "timeout_seconds": judge.timeout, "prompt_sha256": judge.prompt_hash,
        "pairwise_prompt_suffix": "See client.py prefer() in saved source snapshot",
        "input_hashes": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items() if path},
        "limit": args.limit, "verbosity_limit": args.verbosity_limit,
        "labels_reviewed": args.labels_reviewed})
    # Save exact prompt/code for later reproduction, never save .env or keys.
    for name in ("client.py", "run.py"):
        with (args.output / name).open("x", encoding="utf-8") as stream:
            stream.write((Path(__file__).parent / name).read_text(encoding="utf-8"))
    with (args.output / "judge_prompt.txt").open("x", encoding="utf-8") as stream:
        stream.write(judge.prompt)
    records, verbosity, positions = [], [], []
    with (args.output / "results.jsonl").open("x", encoding="utf-8") as stream:
        for response in responses[:args.limit]:
            item = items[response["item_id"]]
            row = {**response, **safe_call(judge.grade, item["customer_message"], item["order_context"], response["response_text"])}
            records.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"{len(records)}: {row['item_id']} {row['status']}")
    with (args.output / "verbosity.jsonl").open("x", encoding="utf-8") as stream:
        for row in records[:args.verbosity_limit]:
            item = items[row["item_id"]]
            padded_text = row["response_text"] + PADDING
            padded = safe_call(judge.grade, item["customer_message"], item["order_context"], padded_text)
            valid = row["status"] == padded["status"] == "ok"
            result = {"item_id": row["item_id"], "response_id": row["response_id"], "original_text": row["response_text"],
                      "padded_text": padded_text, "original": row, "padded": padded,
                      "delta": padded["result"]["scores"]["total"] - row["result"]["scores"]["total"] if valid else None}
            verbosity.append(result)
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            stream.flush()
    with (args.output / "position.jsonl").open("x", encoding="utf-8") as stream:
        for pair in pairs:
            item = items[pair["item_id"]]
            forward = safe_call(judge.prefer, item, pair["answer_a"], pair["answer_b"])
            reverse = safe_call(judge.prefer, item, pair["answer_b"], pair["answer_a"])
            valid = forward["status"] == reverse["status"] == "ok"
            changed = canonical_winner(forward["result"]["winner"]) != canonical_winner(reverse["result"]["winner"], True) if valid else None
            result = {**pair, "forward": forward, "reverse": reverse, "changed": changed}
            positions.append(result)
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            stream.flush()
    report = summarize(records, labels, args.labels_reviewed)
    deltas = [r["delta"] for r in verbosity if r["delta"] is not None]
    changes = [r["changed"] for r in positions if r["changed"] is not None]
    report["verbosity_bias"] = {"attempted": len(verbosity), "valid_pairs": len(deltas),
        "failed_pairs": len(verbosity) - len(deltas), "changed_scores": sum(d != 0 for d in deltas),
        "changed_percent": 100 * sum(d != 0 for d in deltas) / len(deltas) if deltas else None,
        "average_score_change": sum(deltas) / len(deltas) if deltas else None,
        "note": "Screening test: manually check that padding preserves tone and relevance. Changes can reflect tone, relevance, or model variability, not solely length bias."}
    report["position_bias"] = {"attempted": len(positions), "valid_pairs": len(changes),
        "failed_pairs": len(positions) - len(changes), "changed_verdicts": sum(changes),
        "changed_percent": 100 * sum(changes) / len(changes) if changes else None,
        "note": "Verdicts mapped to original reply identities. One swap measures observed sensitivity; repeated trials are needed to distinguish order effects from random variability."}
    report["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(args.output / "reliability.json", report)
    print(f"Saved results in {args.output}")
    return 1 if report["failed_responses"] or any(r["delta"] is None for r in verbosity) or any(r["changed"] is None for r in positions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
