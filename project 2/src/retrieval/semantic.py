"""Semantic embedding retrieval using a local Sentence Transformers model."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

from .filters import filter_chunks


class Embedder(Protocol):
    """Small interface that keeps embedding tests independent of model downloads."""

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        ...


class SemanticSearch(Protocol):
    """A semantic backend that can rank chunks for a query.

    The local :class:`SemanticRetriever` and the Qdrant-backed retriever both
    satisfy the parts used by the retrieval service.
    """

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        ...


class SentenceTransformerEmbedder:
    """Load a local or Hugging Face Sentence Transformers model."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for semantic retrieval; "
                "install it with 'python -m pip install -r requirements.txt'"
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class SemanticRetriever:
    """Retrieve chunks by cosine similarity of normalized embeddings."""

    def __init__(
        self,
        chunks: Sequence[ArticleChunk],
        *,
        embedder: Embedder | None = None,
        embeddings: np.ndarray | None = None,
    ) -> None:
        self._chunks = tuple(chunks)
        if len({chunk.chunk_id for chunk in self._chunks}) != len(self._chunks):
            raise ValueError("chunk_id values must be unique")
        if embedder is None and embeddings is None:
            embedder = SentenceTransformerEmbedder()
        self._embedder = embedder

        if embeddings is None:
            assert embedder is not None
            embeddings = embedder.encode(
                [chunk.text for chunk in self._chunks],
                normalize_embeddings=True,
            )
        self._embeddings = self._validate_embeddings(embeddings)

    def _validate_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        values = np.asarray(embeddings, dtype=np.float32)
        if values.ndim != 2 or values.shape[0] != len(self._chunks):
            raise ValueError(
                "embeddings must be a 2D array with one row per chunk"
            )
        if not np.isfinite(values).all():
            raise ValueError("embeddings must contain only finite values")
        norms = np.linalg.norm(values, axis=1)
        if np.any(norms == 0):
            raise ValueError("embeddings must not contain zero vectors")
        return values / norms[:, np.newaxis]

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def embeddings(self) -> np.ndarray:
        """Return a copy suitable for persistence."""
        return self._embeddings.copy()

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not query.strip() or not self._chunks:
            return []
        if self._embedder is None:
            raise RuntimeError("a query embedder is required for search")
        query_vector = self._embedder.encode(
            [query],
            normalize_embeddings=True,
        )
        query_vector = self._validate_query_vector(query_vector)
        scores = self._embeddings @ query_vector
        ranked = sorted(
            enumerate(scores.tolist()),
            key=lambda item: (-item[1], self._chunks[item[0]].chunk_id),
        )
        if filters is not None:
            allowed = {
                chunk.chunk_id for chunk in filter_chunks(self._chunks, filters)
            }
            ranked = [
                item
                for item in ranked
                if self._chunks[item[0]].chunk_id in allowed
            ]
        return [
            self._result(index, score, rank)
            for rank, (index, score) in enumerate(ranked[:top_k], start=1)
            if score > 0
        ]

    @staticmethod
    def _validate_query_vector(vector: np.ndarray) -> np.ndarray:
        values = np.asarray(vector, dtype=np.float32)
        if values.shape[0] != 1 or values.ndim != 2:
            raise ValueError("embedder must return one 2D query vector")
        norm = np.linalg.norm(values[0])
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("query embedding must be a finite non-zero vector")
        return values[0] / norm

    def _result(self, index: int, score: float, rank: int) -> RetrievalResult:
        chunk = self._chunks[index]
        return RetrievalResult(
            chunk_id=chunk.chunk_id,
            record_id=chunk.record_id,
            text=chunk.text,
            score=float(score),
            rank=rank,
            article_number=chunk.article_number,
            article=chunk.article,
            heading_path=chunk.heading_path,
            pdf_page=chunk.pdf_page,
            source_url=chunk.source_url,
            retrieval_method="vector",
        )

    def save(self, directory: Path | str) -> None:
        """Persist embeddings and chunk IDs for reproducible local indexes."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        np.save(target / "embeddings.npy", self._embeddings)
        (target / "chunk_ids.txt").write_text(
            "\n".join(chunk.chunk_id for chunk in self._chunks) + "\n",
            encoding="utf-8",
        )

