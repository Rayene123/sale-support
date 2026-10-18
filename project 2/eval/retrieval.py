"""Measure recall@k and latency for Person 2 retrieval ablations."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from retrieval.bm25 import BM25Retriever
from retrieval.hybrid import HybridRetriever
from retrieval.rerank import rerank
from retrieval.semantic import SemanticRetriever, SentenceTransformerEmbedder


def evaluate(
    retriever,
    questions: list[dict],
    method: str,
    ks: tuple[int, ...],
    *,
    rerank_results: bool = False,
) -> dict:
    latencies: list[float] = []
    hits = {k: 0 for k in ks}
    for item in questions:
        started = time.perf_counter()
        results = retriever.search(item["question"], top_k=max(ks))
        if rerank_results:
            results = rerank(item["question"], results, top_k=max(ks))
        latencies.append((time.perf_counter() - started) * 1000)
        ids = {result.record_id for result in results}
        for k in ks:
            top_ids = {result.record_id for result in results[:k]}
            if top_ids & set(item["gold_record_ids"]):
                hits[k] += 1
    count = len(questions)
    return {
        "method": method,
        "questions": count,
        **{f"recall@{k}": hits[k] / count if count else 0 for k in ks},
        "p50_latency_ms": statistics.median(latencies) if latencies else 0,
        "p95_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]
        if latencies
        else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        default=str(PROJECT_DIR / "data" / "eval" / "retrieval_smoke.jsonl"),
    )
    parser.add_argument("--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--output", default=str(PROJECT_DIR / "data" / "eval" / "retrieval_results.json"))
    args = parser.parse_args()

    questions = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    chunks = chunk_records(load_corpus(PROJECT_DIR / "data" / "processed" / "corpus.jsonl"))
    bm25 = BM25Retriever(chunks)
    embedder = SentenceTransformerEmbedder(args.model)
    semantic = SemanticRetriever(chunks, embedder=embedder)
    hybrid = HybridRetriever(chunks, embedder=embedder)
    rows = [
        evaluate(bm25, questions, "bm25", (1, 3, 5, 10)),
        evaluate(semantic, questions, "semantic", (1, 3, 5, 10)),
        evaluate(hybrid, questions, "hybrid", (1, 3, 5, 10)),
        evaluate(
            hybrid,
            questions,
            "hybrid+reranker",
            (1, 3, 5, 10),
            rerank_results=True,
        ),
    ]
    payload = {"results": rows}
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
