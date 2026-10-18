"""Dependency-free BM25 keyword retrieval."""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Tokenize text consistently for documents and queries."""
    return [token.casefold() for token in TOKEN_RE.findall(text)]


class BM25Retriever:
    """Search article chunks using Okapi BM25."""

    def __init__(
        self,
        chunks: Sequence[ArticleChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 < 0:
            raise ValueError("k1 must not be negative")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")

        self._chunks = tuple(chunks)
        if len({chunk.chunk_id for chunk in self._chunks}) != len(self._chunks):
            raise ValueError("chunk_id values must be unique")

        self.k1 = k1
        self.b = b
        self._tokens = tuple(tokenize(chunk.text) for chunk in self._chunks)
        self._term_frequencies = tuple(Counter(tokens) for tokens in self._tokens)
        self._document_frequency = Counter(
            token for tokens in self._tokens for token in set(tokens)
        )
        self._average_length = (
            sum(len(tokens) for tokens in self._tokens) / len(self._tokens)
            if self._tokens
            else 0.0
        )

    @property
    def chunk_count(self) -> int:
        """Return the number of indexed chunks."""
        return len(self._chunks)

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        """Return up to ``top_k`` matching chunks, ranked by BM25 score."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        query_tokens = tokenize(query)
        if not query_tokens or not self._chunks:
            return []

        query_terms = set(query_tokens)
        scored: list[tuple[float, int]] = []
        document_count = len(self._chunks)
        for index, term_frequencies in enumerate(self._term_frequencies):
            document_length = len(self._tokens[index])
            score = 0.0
            for term in query_terms:
                frequency = term_frequencies.get(term, 0)
                if not frequency:
                    continue
                document_frequency = self._document_frequency[term]
                idf = math.log(
                    1
                    + (document_count - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                length_factor = (
                    1 - self.b + self.b * document_length / self._average_length
                    if self._average_length
                    else 1.0
                )
                score += idf * (
                    frequency * (self.k1 + 1)
                    / (frequency + self.k1 * length_factor)
                )
            if score > 0:
                scored.append((score, index))

        scored.sort(key=lambda item: (-item[0], self._chunks[item[1]].chunk_id))
        results: list[RetrievalResult] = []
        for rank, (score, index) in enumerate(scored[:top_k], start=1):
            chunk = self._chunks[index]
            results.append(
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
                    retrieval_method="bm25",
                )
            )
        return results
