"""Deterministic first-stage reranking for hybrid candidates."""
from __future__ import annotations

import re
from collections.abc import Sequence

from models.retrieval import RetrievalResult

from .bm25 import tokenize


def rerank(
    query: str,
    results: Sequence[RetrievalResult],
    *,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """Rerank candidates using exact-term coverage and phrase matching."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    query_terms = set(tokenize(query))
    normalized_query = " ".join(tokenize(query))
    scored: list[tuple[float, RetrievalResult]] = []
    for result in results:
        terms = set(tokenize(result.text))
        coverage = len(query_terms & terms) / len(query_terms) if query_terms else 0
        normalized_text = " ".join(tokenize(result.text))
        phrase_bonus = 1.0 if normalized_query and normalized_query in normalized_text else 0.0
        article_bonus = 0.5 if re.search(
            rf"\b{re.escape(str(result.article_number))}\b", query
        ) else 0.0
        # Results may come from BM25, cosine similarity, or RRF, whose raw
        # scores are not comparable. Rank-based evidence keeps the heuristic
        # from overwhelming the original retrieval ordering.
        rank_signal = 1 / result.rank
        score = (
            0.55 * rank_signal
            + 0.35 * coverage
            + 0.07 * phrase_bonus
            + 0.03 * article_bonus
        )
        scored.append((score, result))

    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    return [
        RetrievalResult(
            **{
                **result.to_dict(),
                "score": score,
                "rank": rank,
                "retrieval_method": "reranked",
            }
        )
        for rank, (score, result) in enumerate(scored[:top_k], start=1)
    ]
