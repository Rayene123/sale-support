"""Hybrid BM25 and semantic retrieval using reciprocal rank fusion."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Protocol

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

from .bm25 import BM25Retriever
from .filters import filter_chunks
from .semantic import Embedder, SemanticRetriever


class SemanticBackend(Protocol):
    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        ...


class HybridRetriever:
    """Fuse keyword and semantic rankings without comparing score scales."""

    def __init__(
        self,
        chunks: Sequence[ArticleChunk],
        *,
        embedder: Embedder | None = None,
        semantic_backend: SemanticBackend | None = None,
        rrf_k: int = 60,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")
        self._chunks = tuple(chunks)
        self.rrf_k = rrf_k
        self._embedder = embedder
        self._semantic_backend = semantic_backend
        self._bm25 = BM25Retriever(self._chunks)
        self._semantic = (
            SemanticRetriever(self._chunks, embedder=embedder)
            if embedder is not None
            else None
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        candidate_k: int | None = None,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        candidate_k = candidate_k or max(top_k * 3, 10)
        filtered = filter_chunks(self._chunks, filters)
        if not filtered:
            return []
        if not filters:
            keyword = self._bm25.search(query, top_k=candidate_k)
            if self._semantic is None:
                raise RuntimeError(
                    "an embedder is required for unfiltered hybrid retrieval"
                )
            semantic = (
                self._semantic_backend.search(query, top_k=candidate_k)
                if self._semantic_backend is not None
                else self._semantic.search(query, top_k=candidate_k)
            )
        else:
            keyword = BM25Retriever(filtered).search(query, top_k=candidate_k)
            semantic = (
                self._semantic_backend.search(
                    query, top_k=candidate_k, filters=filters
                )
                if self._semantic_backend is not None
                else SemanticRetriever(filtered, embedder=self._embedder).search(
                    query, top_k=candidate_k
                )
            )
        by_id = {chunk.chunk_id: chunk for chunk in filtered}
        fused: defaultdict[str, float] = defaultdict(float)
        for results in (keyword, semantic):
            for result in results:
                fused[result.chunk_id] += 1 / (self.rrf_k + result.rank)

        ranked = sorted(
            fused.items(),
            key=lambda item: (-item[1], item[0]),
        )[:top_k]
        output: list[RetrievalResult] = []
        for rank, (chunk_id, score) in enumerate(ranked, start=1):
            chunk = by_id[chunk_id]
            output.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    record_id=chunk.record_id,
                    text=chunk.text,
                    score=score,
                    rank=rank,
                    article_number=chunk.article_number,
                    article=chunk.article,
                    heading_path=chunk.heading_path,
                    pdf_page=chunk.pdf_page,
                    source_url=chunk.source_url,
                    retrieval_method="hybrid",
                )
            )
        return output
