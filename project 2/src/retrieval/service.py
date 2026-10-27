"""Stable retrieval facade for the generation/API layer."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from hashlib import sha256
import json

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

from .bm25 import BM25Retriever
from .filters import filter_chunks
from .hybrid import HybridRetriever
from .qdrant import QdrantRetriever
from .rerank import rerank
from .semantic import Embedder, SemanticRetriever, SemanticSearch


class RetrievalService:
    """Expose keyword, semantic, hybrid, and optional reranked retrieval."""

    def __init__(
        self,
        chunks: Sequence[ArticleChunk],
        *,
        embedder: Embedder | None = None,
        semantic_retriever: SemanticSearch | None = None,
    ) -> None:
        self._chunks = tuple(chunks)
        self.index_sha256 = sha256(json.dumps(
            [asdict(c) for c in sorted(self._chunks, key=lambda c: c.chunk_id)],
            ensure_ascii=False, sort_keys=True,
        ).encode()).hexdigest()
        self._embedder = embedder
        self._bm25 = BM25Retriever(self._chunks)
        self._external_semantic = semantic_retriever is not None
        if semantic_retriever is not None:
            self._semantic: SemanticSearch | None = semantic_retriever
        elif embedder is not None:
            self._semantic = SemanticRetriever(self._chunks, embedder=embedder)
        else:
            self._semantic = None
        self._hybrid = (
            HybridRetriever(
                self._chunks,
                semantic_retriever=self._semantic,
            )
            if self._semantic is not None
            else None
        )

    def retrieve(
        self,
        query: str,
        *,
        method: str = "hybrid",
        top_k: int = 5,
        filters: Mapping[str, object] | None = None,
        rerank_results: bool = False,
    ) -> list[RetrievalResult]:
        chunks = filter_chunks(self._chunks, filters)
        if method == "bm25":
            results = (
                self._bm25.search(query, top_k=top_k)
                if not filters
                else BM25Retriever(chunks).search(query, top_k=top_k)
            )
        elif method == "vector":
            if self._semantic is None:
                raise RuntimeError(
                    "an embedder or semantic retriever is required for vector retrieval"
                )
            if self._external_semantic:
                results = self._semantic.search(
                    query,
                    top_k=top_k,
                    filters=filters,
                )
            elif not filters:
                results = self._semantic.search(query, top_k=top_k)
            else:
                if self._semantic is not None and isinstance(self._semantic, QdrantRetriever):
                    results = self._semantic.search(
                        query, top_k=top_k, filters=filters
                    )
                else:
                    results = SemanticRetriever(chunks, embedder=self._embedder).search(
                        query, top_k=top_k
                    )
        elif method == "hybrid":
            if self._hybrid is None:
                raise RuntimeError(
                    "an embedder or semantic retriever is required for hybrid retrieval"
                )
            if self._external_semantic:
                results = self._hybrid.search(
                    query,
                    top_k=top_k,
                    filters=filters,
                )
            elif not filters:
                results = self._hybrid.search(query, top_k=top_k)
            else:
                results = self._hybrid.search(query, top_k=top_k, filters=filters)
        else:
            raise ValueError("method must be one of 'bm25', 'vector', or 'hybrid'")
        return rerank(query, results, top_k=top_k) if rerank_results else results
