"""Qdrant-backed semantic retrieval for the legal corpus.

The local :class:`retrieval.semantic.SemanticRetriever` keeps embeddings in a
NumPy array. This module keeps the same :class:`models.retrieval.RetrievalResult`
contract but stores the vectors in a Qdrant collection, which may be Qdrant
Cloud or a self-hosted server.

Configuration comes from the environment (see ``.env.example``)::

    QDRANT_URL=https://<cluster-id>.cloud.qdrant.io:6333
    QDRANT_API_KEY=<secret>
    QDRANT_COLLECTION=librarian-chunks

The API key is a secret. ``.env`` is git-ignored; never commit a real key.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from indexing.chunking import ArticleChunk
from models.retrieval import RetrievalResult

DEFAULT_COLLECTION = "librarian-chunks"
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Point ids must be UUIDs or unsigned integers. Deriving a UUID from the stable
# chunk_id makes re-uploads idempotent: the same chunk always overwrites itself.
POINT_ID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/Rayene123/sale-support/project-2/librarian",
)

# Payload fields that may be used as exact-match filters. They mirror
# retrieval.filters.filter_chunks (except article_suffix, which ArticleChunk
# does not carry).
FILTERABLE_FIELDS = frozenset(
    {
        "chunk_id",
        "record_id",
        "document_id",
        "language",
        "article_number",
        "pdf_page",
        "book",
        "titre",
        "chapitre",
        "section",
        "sous_section",
    }
)


@dataclass(frozen=True)
class QdrantConfig:
    """Connection settings for one Qdrant collection."""

    url: str
    api_key: str | None = None
    collection: str = DEFAULT_COLLECTION
    prefer_grpc: bool = False
    timeout: int = 60

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "QdrantConfig":
        """Read connection settings from the process environment."""
        env = os.environ if environ is None else environ
        url = (env.get("QDRANT_URL") or "").strip()
        if not url:
            raise ValueError(
                "QDRANT_URL is not set. Copy the cluster URL from the Qdrant Cloud "
                "console (for example https://<cluster-id>.cloud.qdrant.io:6333) "
                "into .env or the environment."
            )
        api_key = (env.get("QDRANT_API_KEY") or "").strip() or None
        collection = (env.get("QDRANT_COLLECTION") or "").strip() or DEFAULT_COLLECTION
        prefer_grpc = (env.get("QDRANT_PREFER_GRPC") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(
            url=url,
            api_key=api_key,
            collection=collection,
            prefer_grpc=prefer_grpc,
        )


def _models():
    try:
        from qdrant_client import models
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "qdrant-client is required for Qdrant retrieval; install it with "
            "'python -m pip install -r requirements.txt'"
        ) from exc
    return models


def create_client(config: QdrantConfig, *, client: Any | None = None):
    """Return ``client`` or a new :class:`QdrantClient` for ``config``."""
    if client is not None:
        return client
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "qdrant-client is required for Qdrant retrieval; install it with "
            "'python -m pip install -r requirements.txt'"
        ) from exc
    return QdrantClient(
        url=config.url,
        api_key=config.api_key,
        prefer_grpc=config.prefer_grpc,
        timeout=config.timeout,
    )


def point_id(chunk_id: str) -> str:
    """Return the deterministic Qdrant point id for ``chunk_id``."""
    return str(uuid.uuid5(POINT_ID_NAMESPACE, chunk_id))


def chunk_payload(chunk: ArticleChunk) -> dict[str, Any]:
    """Return the stored payload for one chunk.

    ``book``/``titre``/``chapitre``/``section``/``sous_section`` are flattened
    out of ``heading_path`` so Qdrant can filter on them without client-side
    post-processing.
    """
    headings = list(chunk.heading_path)

    def level(index: int) -> str | None:
        return headings[index] if len(headings) > index else None

    return {
        "chunk_id": chunk.chunk_id,
        "record_id": chunk.record_id,
        "text": chunk.text,
        "chunk_index": chunk.chunk_index,
        "chunk_count": chunk.chunk_count,
        "article": chunk.article,
        "article_number": chunk.article_number,
        "heading_path": headings,
        "document_id": chunk.document_id,
        "language": chunk.language,
        "pdf_page": chunk.pdf_page,
        "printed_page": chunk.printed_page,
        "source_url": chunk.source_url,
        "source_sha256": chunk.source_sha256,
        "source_date": chunk.source_date,
        "source_edition": chunk.source_edition,
        "book": level(0),
        "titre": level(1),
        "chapitre": level(2),
        "section": level(3),
        "sous_section": level(4),
    }


def ensure_collection(
    client: Any,
    collection: str,
    dimension: int,
    *,
    recreate: bool = False,
) -> bool:
    """Create ``collection`` if needed and return whether it was created.

    An existing collection must already use the same vector size and cosine
    distance; otherwise the build stops with an instruction to ``--recreate``.
    """
    if dimension < 1:
        raise ValueError("dimension must be at least 1")
    models = _models()

    exists = client.collection_exists(collection)
    if exists and recreate:
        client.delete_collection(collection)
        exists = False

    if exists:
        info = client.get_collection(collection)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        distance = getattr(vectors, "distance", None)
        if size != dimension:
            raise ValueError(
                f"collection {collection!r} stores {size}-dimensional vectors, "
                f"but the embedder produces {dimension}; pass --recreate to rebuild it"
            )
        if distance is not None and distance != models.Distance.COSINE:
            raise ValueError(
                f"collection {collection!r} uses distance {distance!r}; "
                "expected cosine"
            )
        return False

    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=dimension,
            distance=models.Distance.COSINE,
        ),
    )
    return True


def upload_chunks(
    client: Any,
    chunks: Sequence[ArticleChunk],
    embeddings: np.ndarray,
    *,
    collection: str = DEFAULT_COLLECTION,
    batch_size: int = 128,
    recreate: bool = False,
) -> dict[str, Any]:
    """Create/verify the collection and upsert one point per chunk.

    Embeddings are L2-normalised before upload so cosine similarity is exactly
    the dot product, matching the local retriever.
    """
    models = _models()
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    chunk_list = tuple(chunks)
    if not chunk_list:
        raise ValueError("no chunks to upload")
    chunk_ids = [chunk.chunk_id for chunk in chunk_list]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("chunk_id values must be unique")
    values = np.asarray(embeddings, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] != len(chunk_list):
        raise ValueError("embeddings must be a 2D array with one row per chunk")
    if not np.isfinite(values).all():
        raise ValueError("embeddings must contain only finite values")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("embeddings must not contain zero vectors")
    values = values / norms

    dimension = int(values.shape[1])
    created = ensure_collection(client, collection, dimension, recreate=recreate)

    uploaded = 0
    for start in range(0, len(chunk_list), batch_size):
        batch = chunk_list[start : start + batch_size]
        points = [
            models.PointStruct(
                id=point_id(chunk.chunk_id),
                vector=values[start + offset].tolist(),
                payload=chunk_payload(chunk),
            )
            for offset, chunk in enumerate(batch)
        ]
        client.upsert(collection_name=collection, points=points, wait=True)
        uploaded += len(points)

    return {
        "collection": collection,
        "dimension": dimension,
        "created": created,
        "uploaded": uploaded,
    }


def build_filter(filters: Mapping[str, object] | None):
    """Translate the project's exact-match filters into a Qdrant filter."""
    if not filters:
        return None
    unknown = set(filters) - FILTERABLE_FIELDS
    if unknown:
        raise ValueError(f"unsupported metadata filters: {sorted(unknown)}")
    models = _models()
    conditions = []
    for key, expected in filters.items():
        if expected is None:
            conditions.append(
                models.IsNullCondition(is_null=models.PayloadField(key=key))
            )
        elif isinstance(expected, (list, tuple, set, frozenset)):
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchAny(any=list(expected)),
                )
            )
        else:
            conditions.append(
                models.FieldCondition(
                    key=key,
                    match=models.MatchValue(value=expected),
                )
            )
    return models.Filter(must=conditions)


def _result_from_hit(hit: Any, rank: int) -> RetrievalResult:
    payload = hit.payload or {}
    required = (
        "chunk_id",
        "record_id",
        "text",
        "article",
        "article_number",
        "pdf_page",
        "source_url",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(
            f"Qdrant point {hit.id} is missing payload fields {missing}; "
            "re-upload the collection with the current chunker"
        )
    return RetrievalResult(
        chunk_id=payload["chunk_id"],
        record_id=payload["record_id"],
        text=payload["text"],
        score=float(hit.score),
        rank=rank,
        article_number=int(payload["article_number"]),
        article=payload["article"],
        heading_path=tuple(payload.get("heading_path") or ()),
        pdf_page=int(payload["pdf_page"]),
        source_url=payload["source_url"],
        retrieval_method="vector",
    )


class QdrantRetriever:
    """Semantic retrieval backed by a Qdrant collection.

    The class is a drop-in replacement for ``SemanticRetriever`` where only
    :meth:`search` is needed. It embeds the query with the same model that
    produced the stored vectors.
    """

    def __init__(self, client: Any, *, collection: str, embedder: Any) -> None:
        self._client = client
        self._collection = collection
        self._embedder = embedder

    def load_chunks(self) -> list[ArticleChunk]:
        """Load payloads for the local BM25 leg of hybrid retrieval."""
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
            for point in points:
                payload = point.payload or {}
                headings = tuple(payload.get("heading_path") or ())
                required = (
                    "chunk_id", "record_id", "text", "article",
                    "article_number", "document_id", "language", "pdf_page",
                    "source_url", "source_sha256", "source_date",
                    "source_edition",
                )
                missing = [field for field in required if field not in payload]
                if missing:
                    raise ValueError(
                        f"Qdrant point {point.id} is missing payload fields {missing}"
                    )
                chunks.append(ArticleChunk(
                    chunk_id=payload["chunk_id"],
                    record_id=payload["record_id"],
                    text=payload["text"],
                    chunk_index=int(payload.get("chunk_index", 0)),
                    chunk_count=int(payload.get("chunk_count", 1)),
                    article=payload["article"],
                    article_number=int(payload["article_number"]),
                    heading_path=headings,
                    document_id=payload["document_id"],
                    language=payload["language"],
                    pdf_page=int(payload["pdf_page"]),
                    printed_page=(
                        int(payload["printed_page"])
                        if payload.get("printed_page") is not None
                        else None
                    ),
                    source_url=payload["source_url"],
                    source_sha256=payload["source_sha256"],
                    source_date=payload["source_date"],
                    source_edition=payload["source_edition"],
                ))
            if offset is None:
                break
        chunks.sort(key=lambda chunk: chunk.chunk_id)
        if not chunks:
            raise ValueError(f"Qdrant collection {self._collection!r} is empty")
        return chunks

    @property
    def collection(self) -> str:
        return self._collection

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: Mapping[str, object] | None = None,
    ) -> list[RetrievalResult]:
        """Return up to ``top_k`` chunks ranked by cosine similarity."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not query.strip():
            return []
        vector = np.asarray(
            self._embedder.encode([query], normalize_embeddings=True),
            dtype=np.float32,
        )
        if vector.ndim != 2 or vector.shape[0] != 1:
            raise ValueError("embedder must return one 2D query vector")
        norm = np.linalg.norm(vector[0])
        if not np.isfinite(norm) or norm == 0:
            raise ValueError("query embedding must be a finite non-zero vector")

        response = self._client.query_points(
            collection_name=self._collection,
            query=(vector[0] / norm).tolist(),
            query_filter=build_filter(filters),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
            score_threshold=0.0,
        )
        results: list[RetrievalResult] = []
        for hit in response.points:
            if hit.score <= 0:
                continue
            results.append(_result_from_hit(hit, len(results) + 1))
        return results


def retriever_from_env(
    *,
    embedder: Any | None = None,
    collection: str | None = None,
    client: Any | None = None,
) -> QdrantRetriever:
    """Build a :class:`QdrantRetriever` from the QDRANT_* environment."""
    config = QdrantConfig.from_env()
    if embedder is None:
        from .semantic import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder()
    return QdrantRetriever(
        create_client(config, client=client),
        collection=collection or config.collection,
        embedder=embedder,
    )
