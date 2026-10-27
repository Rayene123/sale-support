"""Evaluate the existing /ask API on approved canonical questions.

Automatic answer matching is a lexical proxy, not a semantic or legal score.
Faithfulness remains a human judgment; exact quote checks only establish that
the cited quotation occurs in the canonical corpus text.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from eval.retrieval import DatasetError, adapt_record


def load_canonical_questions(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Load full canonical rows, preserving reference answers and evidence."""
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"line {line_no}: invalid JSON") from exc
        normalized = adapt_record(row, line_no)
        if normalized["source_format"] != "canonical":
            raise DatasetError(f"line {line_no}: canonical gold_evidence is required")
        qid = normalized["question_id"]
        if qid in seen:
            raise DatasetError(f"line {line_no}: duplicate question_id")
        seen.add(qid)
        status = normalized["review_status"]
        counts[status] = counts.get(status, 0) + 1
        if status == "approved":
            rows.append(dict(row, question_id=qid, question=normalized["question"]))
    return rows, counts


def lexical_f1(reference: str, prediction: str) -> float:
    """Whitespace-token F1 after case-folding and punctuation removal."""
    tokens = lambda text: re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
    ref, pred = tokens(reference), tokens(prediction)
    if not ref or not pred:
        return float(not ref and not pred)
    remaining: dict[str, int] = {}
    for token in ref:
        remaining[token] = remaining.get(token, 0) + 1
    overlap = 0
    for token in pred:
        if remaining.get(token, 0):
            overlap += 1
            remaining[token] -= 1
    precision, recall = overlap / len(pred), overlap / len(ref)
    return 2 * precision * recall / (precision + recall) if overlap else 0.0


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def load_corpus(path: str | Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"corpus line {line_no}: invalid JSON") from exc
        rid = item.get("record_id") if isinstance(item, dict) else None
        if not isinstance(rid, str) or not rid or rid in records:
            raise ValueError(f"corpus line {line_no}: missing or duplicate record_id")
        records[rid] = item
    return records


def score_response(question: dict[str, Any], response: dict[str, Any], corpus: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for name in ("usage", "timings_ms"):
        values = response.get(name, {})
        if not isinstance(values, dict):
            raise ValueError(f"API response {name} must be an object")
        for value in values.values():
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"API response {name} must contain nonnegative finite measurements")
        if name == "usage" and any(v is not None and not isinstance(v, int) for v in values.values()):
            raise ValueError("token counts must be integers")
    citations = response.get("citations")
    if not isinstance(citations, list):
        raise ValueError("API response citations must be a list")
    returned_ids = [c.get("record_id") for c in citations if isinstance(c, dict) and isinstance(c.get("record_id"), str)]
    unique_ids = list(dict.fromkeys(returned_ids))
    gold_ids = [e["record_id"] for e in question.get("gold_evidence", []) if e.get("required", True)]
    gold = set(gold_ids)
    returned = set(unique_ids)
    citation_precision = (len(gold & returned) / len(returned) if returned else 0.0) if question["answerability"] == "answerable" else None
    citation_recall = len(gold & returned) / len(gold) if gold else None
    quote_checks = []
    for citation in citations:
        if not isinstance(citation, dict):
            quote_checks.append(False)
            continue
        record_id = citation.get("record_id")
        record = corpus.get(record_id) if isinstance(record_id, str) else None
        quote = citation.get("quote")
        quote_checks.append(bool(
            record and record.get("status") == "published" and isinstance(record.get("text"), str)
            and isinstance(quote, str) and quote.strip()
            and " ".join(quote.split()) in " ".join(record["text"].split())
        ))
    abstain = response.get("abstain")
    if not isinstance(abstain, bool):
        raise ValueError("API response abstain must be boolean")
    answerable = question["answerability"] == "answerable"
    reference = question.get("expected_answer")
    prediction = response.get("answer_fr")
    if not isinstance(prediction, str) or not prediction.strip():
        raise ValueError("API response answer_fr must be a nonempty string")
    return {
        "question_id": question["question_id"],
        "answerability": question["answerability"],
        "abstain": abstain,
        "answer_lexical_f1_proxy": lexical_f1(reference or "", prediction or "") if answerable and isinstance(prediction, str) else None,
        "citation_record_ids": unique_ids,
        "citation_precision_against_gold": citation_precision,
        "citation_recall_against_gold": citation_recall,
        "quote_exact_corpus_match_rate": sum(quote_checks) / len(quote_checks) if quote_checks else None,
        "quote_checks_passed": sum(quote_checks),
        "quote_checks_total": len(quote_checks),
        "timings_ms": response.get("timings_ms", {}),
        "usage": response.get("usage", {}),
        "model": response.get("model"),
        "reason": response.get("reason"),
        "configuration": response.get("configuration"),
    }


def summarize(rows: list[dict[str, Any]], total_approved: int, excluded_duplicates: int,
              prompt_rate: float | None = None, completion_rate: float | None = None) -> dict[str, Any]:
    completed = [r for r in rows if r.get("error") is None]
    ans = [r for r in completed if r["answerability"] == "answerable"]
    unans = [r for r in completed if r["answerability"] == "unanswerable"]
    correct_abstentions = sum(r["abstain"] for r in unans)
    false_answers = len(unans) - correct_abstentions
    false_abstentions = sum(r["abstain"] for r in ans)
    true_answers = len(ans) - false_abstentions
    abstention_precision = correct_abstentions / (correct_abstentions + false_abstentions) if correct_abstentions + false_abstentions else None
    abstention_recall = correct_abstentions / len(unans) if unans else None
    abstention_f1 = 2 * abstention_precision * abstention_recall / (abstention_precision + abstention_recall) if abstention_precision is not None and abstention_recall and abstention_precision + abstention_recall else 0.0 if abstention_precision is not None else None
    latencies = [r.get("timings_ms", {}).get("total") for r in completed if isinstance(r.get("timings_ms"), dict) and isinstance(r["timings_ms"].get("total"), (int, float))]
    token_prompt = sum(((r.get("usage") or {}).get("prompt_tokens") or 0) + ((r.get("usage") or {}).get("rewrite_prompt_tokens") or 0) for r in completed)
    token_completion = sum(((r.get("usage") or {}).get("completion_tokens") or 0) + ((r.get("usage") or {}).get("rewrite_completion_tokens") or 0) for r in completed)
    usage_complete = sum(
        isinstance((r.get("usage") or {}).get("prompt_tokens"), int)
        and isinstance((r.get("usage") or {}).get("completion_tokens"), int)
        and all(k not in (r.get("usage") or {}) or isinstance(r["usage"][k], int)
                for k in ("rewrite_prompt_tokens", "rewrite_completion_tokens"))
        for r in completed
    )
    cost = None
    if prompt_rate is not None and completion_rate is not None and usage_complete == len(completed):
        cost = (token_prompt * prompt_rate + token_completion * completion_rate) / 1_000_000
    client_latencies = [r["client_wall_ms"] for r in completed if isinstance(r.get("client_wall_ms"), (int, float))]
    return {
        "official_status": "approved_questions_scored; semantic_and_legal_correctness_not_established",
        "question_counts": {"approved": total_approved, "completed": len(completed), "failed": len(rows)-len(completed), "answerable_completed": len(ans), "unanswerable_completed": len(unans), "excluded_duplicates": excluded_duplicates},
        "answer_lexical_f1_proxy": {"mean": statistics.mean([r["answer_lexical_f1_proxy"] for r in ans if r["answer_lexical_f1_proxy"] is not None]) if any(r["answer_lexical_f1_proxy"] is not None for r in ans) else None, "denominator": sum(r["answer_lexical_f1_proxy"] is not None for r in ans), "definition": "Mean token-overlap F1 against reference answer; not semantic correctness."},
        "citation_accuracy": {"answerable_precision_mean": statistics.mean([r["citation_precision_against_gold"] for r in ans if r["citation_precision_against_gold"] is not None]) if ans else None, "precision_denominator_answerable": sum(r["citation_precision_against_gold"] is not None for r in ans), "answerable_gold_recall_mean": statistics.mean([r["citation_recall_against_gold"] for r in ans if r["citation_recall_against_gold"] is not None]) if ans else None, "answerable_recall_denominator": sum(r["citation_recall_against_gold"] is not None for r in ans), "unanswerable_cited_any_rate": sum(bool(r["citation_record_ids"]) for r in unans)/len(unans) if unans else None, "unanswerable_denominator": len(unans), "exact_quote_match_rate": sum(r["quote_checks_passed"] for r in completed)/sum(r["quote_checks_total"] for r in completed) if sum(r["quote_checks_total"] for r in completed) else None, "quote_denominator": sum(r["quote_checks_total"] for r in completed)},
        "abstention": {"true_abstain_unanswerable": correct_abstentions, "unanswerable_denominator": len(unans), "answered_unanswerable": false_answers, "abstained_answerable": false_abstentions, "answerable_denominator": len(ans), "abstention_precision": abstention_precision, "abstention_recall": abstention_recall, "abstention_f1": abstention_f1, "answer_rate_on_answerable": true_answers/len(ans) if ans else None},
        "latency_ms": {"server_total_denominator": len(latencies), "server_total_p50": statistics.median(latencies) if latencies else None, "server_total_p95": _percentile(latencies, .95), "client_wall_denominator": len(client_latencies), "client_wall_p50": statistics.median(client_latencies) if client_latencies else None, "client_wall_p95": _percentile(client_latencies, .95), "retrieval_p50": statistics.median([r["timings_ms"]["retrieval"] for r in completed if isinstance(r.get("timings_ms"), dict) and isinstance(r["timings_ms"].get("retrieval"), (int,float))]) if any(isinstance(r.get("timings_ms"), dict) and isinstance(r["timings_ms"].get("retrieval"), (int,float)) for r in completed) else None, "generation_p50": statistics.median([r["timings_ms"]["generation"] for r in completed if isinstance(r.get("timings_ms"), dict) and isinstance(r["timings_ms"].get("generation"), (int,float))]) if any(isinstance(r.get("timings_ms"), dict) and isinstance(r["timings_ms"].get("generation"), (int,float)) for r in completed) else None, "note": "API client wall time includes network; server timings exclude client/network overhead."},
        "token_usage": {"prompt_tokens": token_prompt if usage_complete == len(completed) else None, "completion_tokens": token_completion if usage_complete == len(completed) else None, "usage_complete_count": usage_complete, "denominator_completed": len(completed)},
        "estimated_cost": {"amount": cost, "currency": "USD", "prompt_usd_per_million_tokens": prompt_rate, "completion_usd_per_million_tokens": completion_rate, "note": "Null until both rates and complete usage counts are supplied; local Ollama electricity/hardware cost is not included."},
        "faithfulness": {"score": None, "reason": "Requires human assessment that each claim is entailed by its cited evidence; exact quote match is not entailment."},
        "clarifications": sum(r.get("reason") == "clarification" for r in completed),
        "definitions": {"approved_only": "Only review.status=approved rows are sent to /ask; excluded duplicates are never scored.", "answer_lexical_f1_proxy": "Token overlap only; never interpret as legal or semantic correctness.", "citation_precision": "For answerable questions, returned distinct cited record IDs that are required gold IDs / returned distinct cited record IDs; question-level value is zero when no citation is returned.", "citation_recall": "Required gold record IDs returned / required gold record IDs, answerable rows only.", "unanswerable_cited_any_rate": "Unanswerable questions with one or more citations / completed unanswerable questions.", "quote_match": "Whitespace-normalized citation quote occurs in normalized text of a published corpus record; does not establish support."},
    }


def review_items(rows: list[dict], corpus: dict) -> list[dict]:
    items = []
    for row in rows:
        if row.get("error"):
            continue
        for i, citation in enumerate(row.get("response", {}).get("citations", []), 1):
            record = corpus.get(citation.get("record_id"), {})
            text = citation.get("text")
            if not isinstance(text, str) or not text.strip() or not record:
                raise ValueError("semantic review requires complete claims and corpus records")
            evidence = {"record_id": citation["record_id"], "claim": text, "quote": citation.get("quote"), "passage": record["text"],
                        "question": row.get("question"), "model": row.get("model")}
            digest = sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            items.append({"review_id": f'{row["question_id"]}:claim-{i}', "claim_sha256": digest,
                          **evidence,
                          "label": "", "reviewer": "", "reason": ""})
    return items


def score_reviews(items: list[dict], reviews: list[dict]) -> dict:
    known = {item["review_id"]: item for item in items}
    labels = {"supported", "partially_supported", "unsupported", "unclear"}
    grouped = {}
    seen = set()
    for review in reviews:
        rid = review.get("review_id")
        if (rid not in known or review.get("claim_sha256") != known[rid]["claim_sha256"]
                or review.get("label") not in labels
                or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
                or not isinstance(review.get("reason"), str) or not review["reason"].strip()):
            raise ValueError("review must bind to the exact claim and supply a label, reviewer and reason")
        key = (rid, review["reviewer"].strip())
        if key in seen:
            raise ValueError("duplicate claim/reviewer label")
        seen.add(key)
        grouped.setdefault(rid, set()).add(review["label"])
    counts = {label: 0 for label in labels}
    disagreements = 0
    for values in grouped.values():
        if len(values) > 1:
            disagreements += 1
        counts[next(iter(values)) if len(values) == 1 else "unclear"] += 1
    scored = sum(counts[k] for k in labels - {"unclear"})
    return {"score": counts["supported"] / scored if scored else None,
            "denominator_scored_claims": scored, "total_claims": len(items),
            "reviewed_claims": len(grouped), "unreviewed_claims": len(items) - len(grouped),
            "disagreements": disagreements, "labels": counts,
            "definition": "Strict supported share among reviewed non-unclear claims; partial support is not full support. Disagreements remain unclear. Not legal correctness."}


def run(api_url: str, questions: list[dict[str, Any]], corpus: dict[str, dict[str, Any]], timeout: float,
        checkpoint: Path | None = None) -> list[dict[str, Any]]:
    rows = []
    for question in questions:
        req = urllib.request.Request(api_url.rstrip("/") + "/ask", data=json.dumps({"question": question["question"]}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="POST")
        start = time.perf_counter()
        payload = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("API response must be an object")
            scored = score_response(question, payload, corpus)
            scored["response"] = payload
            scored["question"] = question["question"]
            scored["client_wall_ms"] = (time.perf_counter() - start) * 1000
            rows.append(scored)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            failed = {"question_id": question["question_id"], "answerability": question["answerability"], "error": type(exc).__name__, "client_wall_ms": (time.perf_counter()-start)*1000}
            if isinstance(exc, urllib.error.HTTPError):
                failed["http_status"] = exc.code
            if payload is not None:
                failed["response"] = payload
            rows.append(failed)
        if checkpoint is not None:
            with checkpoint.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(rows[-1], ensure_ascii=False) + "\n")
    return rows


def run_metadata(questions_path: str | Path, corpus_path: str | Path, api_url: str) -> dict[str, Any]:
    sources = [Path(__file__), PROJECT_DIR / "eval/retrieval.py", *sorted((PROJECT_DIR / "src").rglob("*.py"))]
    return {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "questions_sha256": sha256(Path(questions_path).read_bytes()).hexdigest(),
        "corpus_sha256": sha256(Path(corpus_path).read_bytes()).hexdigest(),
        "source_sha256": {str(p.relative_to(PROJECT_DIR)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in sources},
        "configuration_note": "Source hashes describe this checkout. observed_configurations records the running server's startup snapshot when supplied; older servers without it remain unverified.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=str(PROJECT_DIR / "data/eval/questions.jsonl"))
    parser.add_argument("--corpus", default=str(PROJECT_DIR / "data/processed/corpus.jsonl"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8002")
    parser.add_argument("--output", required=True, help="new JSON output path; existing paths are refused")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--prompt-usd-per-million-tokens", type=float)
    parser.add_argument("--completion-usd-per-million-tokens", type=float)
    parser.add_argument("--review-export", help="new JSONL review queue; no labels are fabricated")
    parser.add_argument("--reviews", help="completed JSONL claim reviews to score")
    parser.add_argument("--score-existing", help="rescore a saved evaluation without API calls")
    parser.add_argument("--checkpoint", help="new JSONL file flushed after each question")
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    if args.review_export and Path(args.review_export).exists():
        parser.error("refusing to overwrite an existing review queue")
    if args.checkpoint and Path(args.checkpoint).exists():
        parser.error("refusing to overwrite a checkpoint")
    if (args.prompt_usd_per_million_tokens is None) != (args.completion_usd_per_million_tokens is None):
        parser.error("provide both token rates or neither")
    try:
        approved, review_counts = load_canonical_questions(args.questions)
        if not approved:
            parser.error("no approved questions available; no generation score")
        corpus = load_corpus(args.corpus)
    except (OSError, DatasetError, ValueError) as exc:
        parser.error(str(exc))
    excluded = review_counts.get("excluded_duplicate", 0)
    provenance = run_metadata(args.questions, args.corpus, args.api_url)
    if args.score_existing:
        saved = json.loads(Path(args.score_existing).read_text(encoding="utf-8"))
        rows = saved["per_question"]
        if len(rows) != len(approved) or {r["question_id"] for r in rows} != {q["question_id"] for q in approved}:
            parser.error("saved results do not match the selected questions")
        if any(saved.get("provenance", {}).get(key) != provenance[key]
               for key in ("questions_sha256", "corpus_sha256")):
            parser.error("saved results do not match the question/corpus fingerprints")
        provenance = saved.get("provenance", {})
    else:
        checkpoint = Path(args.checkpoint) if args.checkpoint else None
        if checkpoint:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
        rows = run(args.api_url, approved, corpus, args.timeout, checkpoint) if checkpoint else run(args.api_url, approved, corpus, args.timeout)
    questions_by_id = {q["question_id"]: q["question"] for q in approved}
    for row in rows:
        row.setdefault("question", questions_by_id[row["question_id"]])
    provenance["observed_models"] = sorted({r["model"] for r in rows if isinstance(r.get("model"), str)})
    provenance["observed_configurations"] = list({json.dumps(r["configuration"], sort_keys=True): r["configuration"]
        for r in rows if isinstance(r.get("configuration"), dict)}.values())
    result = {"evaluation_mode": "approved_canonical_generation", "review_status_counts": review_counts, "provenance": provenance, "metrics": summarize(rows, len(approved), excluded, args.prompt_usd_per_million_tokens, args.completion_usd_per_million_tokens), "per_question": rows}
    if args.review_export or args.reviews:
        items = review_items(rows, corpus)
        if args.review_export:
            queue = Path(args.review_export)
            queue.parent.mkdir(parents=True, exist_ok=True)
            queue.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8")
        if args.reviews:
            reviews = [json.loads(s) for s in Path(args.reviews).read_text(encoding="utf-8").splitlines() if s.strip()]
            result["metrics"]["faithfulness"] = score_reviews(items, reviews)
            result["provenance"]["reviews_sha256"] = sha256(Path(args.reviews).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metrics": result["metrics"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
