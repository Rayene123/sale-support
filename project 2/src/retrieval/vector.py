"""Local TF-IDF vector retrieval with cosine similarity."""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

from .bm25 import tokenize


class VectorRetriever:
    """Retrieve chunks using deterministic TF-IDF vectors.

    This is a local vector baseline, not a semantic embedding model: terms
    receive numeric weights and are compared with cosine similarity. The
    retrieval interface can later be backed by neural embeddings unchanged.
    """

    def __init__(self, chunks: Sequence[ArticleChunk]) -> None:
        self._chunks = tuple(chunks)
        if len({chunk.chunk_id for chunk in self._chunks}) != len(self._chunks):
            raise ValueError("chunk_id values must be unique")

        token_lists = tuple(tokenize(chunk.text) for chunk in self._chunks)
        document_frequency = Counter(
            token for tokens in token_lists for token in set(tokens)
        )
        document_count = len(self._chunks)
        self._idf = {
            token: math.log((1 + document_count) / (1 + frequency)) + 1
            for token, frequency in document_frequency.items()
        }
        self._vectors = tuple(
            self._weighted_vector(tokens) for tokens in token_lists
        )

    def _weighted_vector(self, tokens: list[str]) -> dict[str, float]:
        frequencies = Counter(tokens)
        vector = {
            token: (1 + math.log(frequency)) * self._idf[token]
            for token, frequency in frequencies.items()
            if token in self._idf
        }
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        return {token: weight / norm for token, weight in vector.items()} if norm else {}

    @property
    def chunk_count(self) -> int:
        """Return the number of indexed chunks."""
        return len(self._chunks)

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        """Return up to ``top_k`` chunks ranked by cosine similarity."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query_tokens = tokenize(query)
        if not query_tokens or not self._chunks:
            return []

        query_vector = self._weighted_vector(query_tokens)
        if not query_vector:
            return []

        scored: list[tuple[float, int]] = []
        for index, document_vector in enumerate(self._vectors):
            score = sum(
                query_weight * document_vector.get(token, 0.0)
                for token, query_weight in query_vector.items()
            )
            if score > 0:
                scored.append((score, index))

        scored.sort(key=lambda item: (-item[0], self._chunks[item[1]].chunk_id))
        return [
            self._result(score, index, rank)
            for rank, (score, index) in enumerate(scored[:top_k], start=1)
        ]

    def _result(self, score: float, index: int, rank: int) -> RetrievalResult:
        chunk = self._chunks[index]
        return RetrievalResult(
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
            retrieval_method="vector",
        )
