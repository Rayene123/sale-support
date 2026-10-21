"""Evaluate article retrieval without conflating hit rate and evidence recall.

The canonical evaluation format is ``questions.jsonl``. The older
``retrieval_smoke.jsonl`` format remains readable as an explicitly
non-official smoke set.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class DatasetError(ValueError):
    """A malformed or internally inconsistent JSONL evaluation record."""


def _text(value: Any, name: str, line_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"line {line_number}: {name} must be a nonempty string")
    return value.strip()


def adapt_record(raw: Any, line_number: int) -> dict[str, Any]:
    """Normalize canonical questions and the legacy smoke schema.

    Canonical ``gold_evidence`` entries marked ``required: false`` are retained
    as optional context but excluded from evidence-recall denominators.
    Legacy smoke rows have no review state and therefore can never be official.
    """
    if not isinstance(raw, dict):
        raise DatasetError(f"line {line_number}: record must be a JSON object")
    question = _text(raw.get("question"), "question", line_number)
    canonical = "gold_evidence" in raw
    qid = raw.get("question_id")
    if qid is None and not canonical:
        qid = f"legacy-line-{line_number}"
    qid = _text(qid, "question_id", line_number)

    if canonical:
        answerability = raw.get("answerability")
        if answerability not in {"answerable", "unanswerable"}:
            raise DatasetError(f"line {line_number}: invalid answerability")
        review = raw.get("review")
        if not isinstance(review, dict) or not isinstance(review.get("status"), str):
            raise DatasetError(f"line {line_number}: review.status is required")
        evidence = raw.get("gold_evidence")
        if not isinstance(evidence, list):
            raise DatasetError(f"line {line_number}: gold_evidence must be a list")
        required_ids: list[str] = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                raise DatasetError(
                    f"line {line_number}: gold_evidence[{index}] must be an object"
                )
            record_id = _text(item.get("record_id"), "gold record_id", line_number)
            required = item.get("required", True)
            if not isinstance(required, bool):
                raise DatasetError(
                    f"line {line_number}: gold_evidence[{index}].required must be boolean"
                )
            if required and record_id not in required_ids:
                required_ids.append(record_id)
        if answerability == "answerable":
            _text(raw.get("expected_answer"), "expected_answer", line_number)
            if not required_ids:
                raise DatasetError(
                    f"line {line_number}: answerable record has no required gold evidence"
                )
        elif required_ids or raw.get("expected_answer") is not None:
            raise DatasetError(
                f"line {line_number}: unanswerable record must have null answer and no required evidence"
            )
        return {
            "question_id": qid,
            "question": question,
            "answerability": answerability,
            "review_status": review["status"],
            "required_gold_record_ids": required_ids,
            "source_format": "canonical",
        }

    gold_ids = raw.get("gold_record_ids")
    if not isinstance(gold_ids, list) or not gold_ids:
        raise DatasetError(
            f"line {line_number}: legacy gold_record_ids must be a nonempty list"
        )
    normalized_ids = []
    for index, record_id in enumerate(gold_ids):
        record_id = _text(record_id, f"gold_record_ids[{index}]", line_number)
        if record_id not in normalized_ids:
            normalized_ids.append(record_id)
    return {
        "question_id": qid,
        "question": question,
        "answerability": "answerable",
        "review_status": None,
        "required_gold_record_ids": normalized_ids,
        "source_format": "legacy_smoke",
    }


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL, fail explicitly on malformed lines or duplicate question IDs."""
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        item = adapt_record(raw, line_number)
        if item["question_id"] in seen:
            raise DatasetError(
                f"line {line_number}: duplicate question_id {item['question_id']!r}"
            )
        seen.add(item["question_id"])
        questions.append(item)
    return questions


def _result_record_id(result: Any) -> str:
    if isinstance(result, dict):
        record_id = result.get("record_id")
    else:
        record_id = getattr(result, "record_id", None)
    if not isinstance(record_id, str) or not record_id.strip():
        raise DatasetError("retriever returned a result without a nonempty record_id")
    return record_id.strip()


def _unique_ranked_ids(results: list[Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for result in results:
        record_id = _result_record_id(result)
        if record_id not in seen:
            seen.add(record_id)
            ids.append(record_id)
    return ids


def _percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    return sorted(values)[max(0, int(len(values) * 0.95) - 1)]


def evaluate(
    retriever: Any,
    questions: list[dict[str, Any]],
    method: str,
    ks: tuple[int, ...],
    *,
    rerank_results: bool = False,
) -> dict[str, Any]:
    """Evaluate approved answerable items; report unanswerables separately.

    Recall@k is computed per question as matched required article IDs divided
    by required article IDs, then macro-averaged across answerable questions.
    Strict multi-evidence success uses only questions with at least two required
    IDs as its denominator. Any-gold hit uses all answerable questions.
    Top-k counts distinct article IDs, not chunks.
    """
    if not ks or any(not isinstance(k, int) or k < 1 for k in ks):
        raise ValueError("ks must contain positive integers")
    answerable = [q for q in questions if q["answerability"] == "answerable"]
    unanswerable_count = sum(q["answerability"] == "unanswerable" for q in questions)
    multi = [q for q in answerable if len(q["required_gold_record_ids"]) > 1]
    per_question: list[dict[str, Any]] = []
    latency: list[float] = []
    aggregate: dict[int, dict[str, float | int]] = {}
    for k in ks:
        aggregate[k] = {
            "recall_macro_average": 0.0,
            "recall_denominator_questions": len(answerable),
            "strict_multi_evidence_success": 0.0,
            "strict_denominator_multi_evidence_questions": len(multi),
            "any_gold_hit": 0.0,
            "any_gold_denominator_answerable_questions": len(answerable),
        }
    for q in answerable:
        started = time.perf_counter()
        results = retriever.search(q["question"], top_k=max(ks))
        if rerank_results:
            from retrieval.rerank import rerank

            results = rerank(q["question"], results, top_k=max(ks))
        latency.append((time.perf_counter() - started) * 1000)
        ranked_ids = _unique_ranked_ids(results)
        gold = set(q["required_gold_record_ids"])
        row: dict[str, Any] = {
            "question_id": q["question_id"],
            "required_gold_count": len(gold),
            "retrieved_unique_record_ids": ranked_ids,
            "metrics": {},
        }
        for k in ks:
            matched = gold.intersection(ranked_ids[:k])
            recall = len(matched) / len(gold) if gold else 0.0
            strict = bool(gold) and len(matched) == len(gold)
            any_hit = bool(matched)
            row["metrics"][f"@{k}"] = {
                "recall": recall,
                "strict_multi_evidence_success": int(strict) if len(gold) > 1 else None,
                "any_gold_hit": int(any_hit),
                "matched_gold_record_ids": sorted(matched),
            }
            aggregate[k]["recall_macro_average"] += recall
            aggregate[k]["any_gold_hit"] += int(any_hit)
            if len(gold) > 1:
                aggregate[k]["strict_multi_evidence_success"] += int(strict)
        per_question.append(row)
    for k in ks:
        den = aggregate[k]["recall_denominator_questions"]
        any_den = aggregate[k]["any_gold_denominator_answerable_questions"]
        strict_den = aggregate[k]["strict_denominator_multi_evidence_questions"]
        aggregate[k]["recall_macro_average"] = (
            aggregate[k]["recall_macro_average"] / den if den else None
        )
        aggregate[k]["any_gold_hit"] = aggregate[k]["any_gold_hit"] / any_den if any_den else None
        aggregate[k]["strict_multi_evidence_success"] = (
            aggregate[k]["strict_multi_evidence_success"] / strict_den if strict_den else None
        )
    return {
        "method": method,
        "question_counts": {
            "evaluated_total": len(questions),
            "answerable": len(answerable),
            "unanswerable_excluded_from_recall": unanswerable_count,
        },
        "metrics_by_k": {str(k): aggregate[k] for k in ks},
        "latency_ms": {
            "denominator_answerable_questions": len(latency),
            "p50": statistics.median(latency) if latency else None,
            "p95": _percentile95(latency) if latency else None,
        },
        "per_question": per_question,
        "definitions": {
            "recall_at_k": "Per answerable question: required gold record IDs in top k distinct retrieved records divided by required gold IDs; aggregate is macro-average over answerable questions.",
            "strict_multi_evidence_success_at_k": "Share of answerable questions with at least two required gold IDs for which all required IDs are in top k distinct retrieved records.",
            "any_gold_hit_at_k": "Share of answerable questions with at least one required gold ID in top k distinct retrieved records.",
            "unanswerable": "Counted separately and excluded from retrieval recall, strict success, any-gold hit, and retrieval latency denominators.",
            "deduplication": "Repeated chunks from one record_id count once, preserving first-ranked occurrence.",
        },
    }


def official_questions(questions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return approved canonical rows and auditable review-state counts."""
    counts: dict[str, int] = {}
    for q in questions:
        status = q.get("review_status") or "missing_review_status"
        counts[status] = counts.get(status, 0) + 1
    return [q for q in questions if q.get("review_status") == "approved"], counts


def _build_retrievers(
    model_name: str,
    corpus_path: Path,
    method: str = "all",
) -> list[tuple[str, Any, bool]]:
    """Build only the requested retriever, or all variants for compatibility."""
    methods = {"all", "bm25", "vector", "hybrid", "hybrid_reranker"}
    if method not in methods:
        raise ValueError(f"method must be one of {sorted(methods)}")

    from indexing.chunking import chunk_records
    from indexing.corpus import load_corpus

    chunks = chunk_records(load_corpus(corpus_path))
    if method == "bm25":
        from retrieval.bm25 import BM25Retriever

        return [("bm25", BM25Retriever(chunks), False)]

    if method == "vector":
        from retrieval.semantic import SemanticRetriever, SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder(model_name)
        return [("vector", SemanticRetriever(chunks, embedder=embedder), False)]

    if method in {"hybrid", "hybrid_reranker"}:
        from retrieval.hybrid import HybridRetriever
        from retrieval.semantic import SentenceTransformerEmbedder

        hybrid = HybridRetriever(
            chunks,
            embedder=SentenceTransformerEmbedder(model_name),
        )
        if method == "hybrid":
            return [("hybrid", hybrid, False)]
        from retrieval.rerank import rerank  # noqa: F401 - verify reranker availability

        return [("hybrid_reranker", hybrid, True)]

    # Preserve the original default behavior and output method labels.
    from retrieval.bm25 import BM25Retriever
    from retrieval.hybrid import HybridRetriever
    from retrieval.rerank import rerank  # noqa: F401 - verify reranker availability
    from retrieval.semantic import SemanticRetriever, SentenceTransformerEmbedder

    bm25 = BM25Retriever(chunks)
    embedder = SentenceTransformerEmbedder(model_name)
    semantic = SemanticRetriever(chunks, embedder=embedder)
    hybrid = HybridRetriever(chunks, embedder=embedder)
    return [
        ("bm25", bm25, False),
        ("semantic", semantic, False),
        ("hybrid", hybrid, False),
        ("hybrid+reranker", hybrid, True),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions", default=str(PROJECT_DIR / "data" / "eval" / "retrieval_smoke.jsonl")
    )
    parser.add_argument(
        "--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    parser.add_argument(
        "--output", default=str(PROJECT_DIR / "data" / "eval" / "retrieval_results.json")
    )
    parser.add_argument("--k", nargs="+", type=int, default=[1, 3, 5, 10])
    parser.add_argument(
        "--method",
        choices=("all", "bm25", "vector", "hybrid", "hybrid_reranker"),
        default="all",
        help="retrieval method to evaluate; 'all' preserves the original behavior",
    )
    args = parser.parse_args(argv)
    try:
        questions = load_questions(args.questions)
    except (OSError, DatasetError) as exc:
        parser.error(str(exc))

    approved, review_counts = official_questions(questions)
    canonical = any(q["source_format"] == "canonical" for q in questions)
    if canonical and not approved:
        candidate_answerability_counts = {
            "answerable": sum(q["answerability"] == "answerable" for q in questions),
            "unanswerable": sum(q["answerability"] == "unanswerable" for q in questions),
        }
        print(
            json.dumps(
                {
                    "official_score_available": False,
                    "reason": "No questions have review.status=approved.",
                    "question_count": len(questions),
                    "approved_question_count": 0,
                    "candidate_answerability_counts": candidate_answerability_counts,
                    "review_status_counts": review_counts,
                    "metrics": None,
                },
                indent=2,
            )
        )
        return 0

    # Legacy smoke rows lack review metadata; retain their historical exploratory
    # behavior but label the result non-official and never treat them as approved.
    selected = approved if canonical else questions
    exploratory = not canonical
    output_path = Path(args.output)
    if output_path.exists():
        parser.error(f"refusing to overwrite existing output: {output_path}")
    try:
        retrievers = _build_retrievers(
            args.model,
            PROJECT_DIR / "data" / "processed" / "corpus.jsonl",
            args.method,
        )
    except Exception as exc:
        parser.error(f"could not initialize retrieval components: {exc}")
    results = [
        evaluate(r, selected, name, tuple(args.k), rerank_results=use_reranker)
        for name, r, use_reranker in retrievers
    ]
    payload = {
        "official_score_available": not exploratory,
        "evaluation_mode": "legacy_smoke_exploratory" if exploratory else "approved_canonical",
        "selected_method": args.method,
        "review_status_counts": review_counts,
        "results": results,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
