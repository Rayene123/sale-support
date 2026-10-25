"""Qdrant-backed semantic retrieval for the indexed article chunks."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

from .semantic import Embedder


class QdrantRetriever:
    """Query a Qdrant collection containing chunk text and citation metadata."""

    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        *,
        embedder: Embedder,
    ) -> None:
        if not collection.strip():
            raise ValueError("Qdrant collection must not be empty")
        self._client = client
        self._collection = collection
        self._embedder = embedder

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not query.strip():
            return []
        vector = self._embedder.encode(
            [query],
            normalize_embeddings=True,
        )
        if getattr(vector, "shape", None) != (1, 384):
            raise ValueError(
                "Qdrant embeddings must have shape (1, 384) for this collection"
            )
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector[0].tolist(),
            query_filter=self._make_filter(filters),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [
            self._result(point.payload or {}, float(point.score), rank)
            for rank, point in enumerate(response.points, start=1)
        ]

    def load_chunks(self) -> list[ArticleChunk]:
        """Load the indexed payloads for the local BM25 leg of hybrid search."""
        chunks: list[ArticleChunk] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self._collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            chunks.extend(
                self._chunk_from_payload(point.payload or {})
                for point in points
            )
            if offset is None:
                break
        chunks.sort(key=lambda chunk: chunk.chunk_id)
        if not chunks:
            raise ValueError(f"Qdrant collection {self._collection!r} is empty")
        return chunks

    @staticmethod
    def _make_filter(filters: Mapping[str, object] | None) -> Filter | None:
        if not filters:
            return None
        supported = {
            "chunk_id",
            "record_id",
            "document_id",
            "language",
            "article_number",
            "book",
            "titre",
            "chapitre",
            "section",
            "sous_section",
            "pdf_page",
        }
        unknown = set(filters) - supported
        if unknown:
            raise ValueError(f"unsupported metadata filters: {sorted(unknown)}")
        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
            ]
        )

    @staticmethod
    def _result(payload: dict[str, Any], score: float, rank: int) -> RetrievalResult:
        required = (
            "chunk_id",
            "record_id",
            "text",
            "article_number",
            "article",
            "pdf_page",
            "source_url",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Qdrant payload is missing fields: {missing}")
        heading_path = payload.get("heading_path", [])
        if not isinstance(heading_path, list):
            raise ValueError("Qdrant heading_path must be a list")
        return RetrievalResult(
            chunk_id=str(payload["chunk_id"]),
            record_id=str(payload["record_id"]),
            text=str(payload["text"]),
            score=score,
            rank=rank,
            article_number=int(payload["article_number"]),
            article=str(payload["article"]),
            heading_path=tuple(str(item) for item in heading_path),
            pdf_page=int(payload["pdf_page"]),
            source_url=str(payload["source_url"]),
            retrieval_method="vector",
        )

    @classmethod
    def _chunk_from_payload(cls, payload: dict[str, Any]) -> ArticleChunk:
        required = (
            "chunk_id",
            "record_id",
            "text",
            "article_number",
            "article",
            "pdf_page",
            "source_url",
            "source_sha256",
            "source_date",
            "source_edition",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Qdrant payload is missing fields: {missing}")
        heading_path = payload.get("heading_path", [])
        if not isinstance(heading_path, list):
            raise ValueError("Qdrant heading_path must be a list")
        return ArticleChunk(
            chunk_id=str(payload["chunk_id"]),
            record_id=str(payload["record_id"]),
            text=str(payload["text"]),
            chunk_index=int(payload.get("chunk_index", 0)),
            chunk_count=int(payload.get("chunk_count", 1)),
            article=str(payload["article"]),
            article_number=int(payload["article_number"]),
            heading_path=tuple(str(item) for item in heading_path),
            document_id=str(payload.get("document_id", "")),
            language=str(payload.get("language", "")),
            pdf_page=int(payload["pdf_page"]),
            printed_page=(
                int(payload["printed_page"])
                if payload.get("printed_page") is not None
                else None
            ),
            source_url=str(payload["source_url"]),
            source_sha256=str(payload["source_sha256"]),
            source_date=str(payload["source_date"]),
            source_edition=str(payload["source_edition"]),
        )
