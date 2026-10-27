"""Calibrate a retrieval admission threshold on a separate development set."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT), str(PROJECT / "src")]
from dotenv import load_dotenv
from api.app import _build_retriever
from generation.questions import prepare_question


def select_threshold(rows: list[dict], min_recall: float = .9) -> tuple[float, list[dict]]:
    if not rows or not 0 < min_recall <= 1:
        raise ValueError("development rows and a recall target in (0, 1] are required")
    if {r["answerable"] for r in rows} != {True, False}:
        raise ValueError("development data must contain both answerable and unanswerable cases")
    if any(not isinstance(r["answerable"], bool) or not isinstance(r["has_results"], bool)
           or isinstance(r["score"], bool) or not isinstance(r["score"], (int, float))
           or not math.isfinite(r["score"]) or r["score"] < 0 for r in rows):
        raise ValueError("retrieval scores must be finite and nonnegative")
    candidates = sorted({0., *(math.nextafter(r["score"], math.inf) for r in rows)})
    table = []
    positives = sum(r["answerable"] for r in rows)
    negatives = len(rows) - positives
    for threshold in candidates:
        fn = sum(r["answerable"] and (not r["has_results"] or r["score"] < threshold) for r in rows)
        fp = sum(not r["answerable"] and r["has_results"] and r["score"] >= threshold for r in rows)
        table.append({"threshold": threshold, "false_reject": fn, "false_accept": fp,
                      "answerable_recall": (positives - fn) / positives,
                      "unanswerable_admission_rate": fp / negatives})
    eligible = [r for r in table if r["answerable_recall"] >= min_recall]
    if not eligible:
        raise ValueError("retrieval cannot meet the recall target even without a threshold")
    selected = min(eligible, key=lambda r: (r["false_accept"], r["false_reject"], r["threshold"]))
    return selected["threshold"], table


def main():
    load_dotenv(PROJECT / ".env")
    load_dotenv(PROJECT.parent / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", default=str(PROJECT / "data/eval/person3_dev.jsonl"))
    parser.add_argument("--backend", choices=["local", "qdrant"], default="local")
    parser.add_argument("--min-recall", type=float, default=.9)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("refusing to overwrite a calibration")
    dev = [json.loads(s) for s in Path(args.dev).read_text(encoding="utf-8").splitlines() if s.strip()]
    canonical = [json.loads(s) for s in (PROJECT / "data/eval/questions.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    normalize = lambda s: " ".join(s.casefold().split())
    official = {normalize(q["question"]) for q in canonical}
    ids = {q["question_id"] for q in canonical}
    if (len({q["question_id"] for q in dev}) != len(dev)
            or any(q["question_id"] in ids or normalize(q["question"]) in official for q in dev)):
        parser.error("development IDs/questions must be separate from the canonical evaluation")
    corpus_path = PROJECT / "data/processed/corpus.jsonl"
    retriever, method = _build_retriever(use_qdrant=args.backend == "qdrant")
    if args.backend == "qdrant" and method != "hybrid":
        parser.error("Qdrant calibration requires complete Qdrant configuration")
    rows = []
    for q in dev:
        if not isinstance(q.get("answerable"), bool):
            parser.error("answerable must be a boolean")
        plan, _ = prepare_question(q["question"], q.get("history", []))
        passages = [p for query in plan.queries for p in retriever.retrieve(query, method=method, top_k=10)]
        rows.append({"question_id": q["question_id"], "answerable": q["answerable"],
                     "has_results": bool(passages), "score": max((p.score for p in passages), default=0.)})
    threshold, table = select_threshold(rows, args.min_recall)
    report = {"backend": args.backend, "method": method, "index_sha256": retriever.index_sha256,
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "selected_threshold": threshold,
              "corpus_sha256": sha256(corpus_path.read_bytes()).hexdigest(),
              "development_sha256": sha256(Path(args.dev).read_bytes()).hexdigest(),
              "canonical_sha256": sha256((PROJECT / "data/eval/questions.jsonl").read_bytes()).hexdigest(),
              "min_answerable_recall": args.min_recall, "rows": rows, "candidates": table,
              "note": "Retrieval admission only, not measured generation faithfulness or legal correctness. Validate on development generation before freezing final evaluation."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "selected_threshold": threshold, "development_cases": len(rows)}))


if __name__ == "__main__":
    main()
