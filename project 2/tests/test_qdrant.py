"""Tests for the Qdrant-backed retriever using the in-memory client."""
from __future__ import annotations

import unittest

import numpy as np

import _paths  # noqa: F401

try:
    from qdrant_client import QdrantClient
except ImportError:  # pragma: no cover - only when the optional dependency is absent
    raise unittest.SkipTest("qdrant-client is not installed")

from indexing.chunking import ArticleChunk
from retrieval.qdrant import (
    QdrantConfig,
    QdrantRetriever,
    build_filter,
    chunk_payload,
    ensure_collection,
    point_id,
    upload_chunks,
)
from retrieval.service import RetrievalService


def make_chunk(
    chunk_id: str,
    article_number: int,
    text: str,
    *,
    document_id: str = "code-commerce-tn",
    heading_path: tuple[str, ...] = ("Livre II — DU FONDS DE COMMERCE",),
) -> ArticleChunk:
    return ArticleChunk(
        chunk_id=chunk_id,
        record_id=f"{document_id}:article-{article_number}",
        text=text,
        chunk_index=0,
        chunk_count=1,
        article=f"Article {article_number}",
        article_number=article_number,
        heading_path=heading_path,
        document_id=document_id,
        language="fr",
        pdf_page=11,
        printed_page=11,
        source_url="https://example.invalid/source.pdf",
        source_sha256="a" * 64,
        source_date="2024-02-15",
        source_edition="edition",
    )


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        return np.asarray([self.vectors[text] for text in texts], dtype=np.float32)


class QdrantConfigTests(unittest.TestCase):
    def test_missing_url_is_rejected(self):
        with self.assertRaises(ValueError):
            QdrantConfig.from_env({})

    def test_defaults_and_grpc_flag(self):
        config = QdrantConfig.from_env(
            {
                "QDRANT_URL": "https://example.cloud.qdrant.io:6333",
                "QDRANT_API_KEY": "secret",
                "QDRANT_PREFER_GRPC": "true",
            }
        )
        self.assertEqual(config.collection, "librarian-chunks")
        self.assertEqual(config.api_key, "secret")
        self.assertTrue(config.prefer_grpc)


class QdrantIndexTests(unittest.TestCase):
    def setUp(self):
        self.client = QdrantClient(location=":memory:")
        self.chunks = [
            make_chunk(
                "code-commerce-tn:article-1:chunk-0",
                1,
                "fonds de commerce",
                heading_path=("Livre II", "Titre I"),
            ),
            make_chunk(
                "code-commerce-tn:article-2:chunk-0",
                2,
                "lettre de change",
                heading_path=("Livre II", "Titre II"),
            ),
            make_chunk(
                "loi-59-129-1959:article-1:chunk-0",
                1,
                "promulgation",
                document_id="loi-59-129-1959",
                heading_path=(),
            ),
        ]
        self.embeddings = np.asarray(
            [
                [1.0, 0.2, 0.0],
                [0.2, 1.0, 0.0],
                [0.0, 0.2, 1.0],
            ],
            dtype=np.float32,
        )
        self.embedder = FakeEmbedder(
            {
                "fonds de commerce": [1.0, 0.2, 0.0],
                "lettre de change": [0.2, 1.0, 0.0],
                "promulgation": [0.0, 0.2, 1.0],
                "vente fonds": [1.0, 0.1, 0.0],
            }
        )

    def _retriever(self, collection: str = "test") -> QdrantRetriever:
        return QdrantRetriever(
            self.client,
            collection=collection,
            embedder=self.embedder,
        )

    def _upload(self, collection: str = "test", *, recreate: bool = True) -> dict:
        return upload_chunks(
            self.client,
            self.chunks,
            self.embeddings,
            collection=collection,
            recreate=recreate,
        )

    def test_point_ids_are_deterministic(self):
        self.assertEqual(point_id("a:chunk-0"), point_id("a:chunk-0"))
        self.assertNotEqual(point_id("a:chunk-0"), point_id("b:chunk-0"))

    def test_payload_carries_citation_and_heading_levels(self):
        payload = chunk_payload(self.chunks[0])
        self.assertEqual(payload["chunk_id"], "code-commerce-tn:article-1:chunk-0")
        self.assertEqual(payload["article_number"], 1)
        self.assertEqual(payload["book"], "Livre II")
        self.assertEqual(payload["titre"], "Titre I")
        self.assertIsNone(payload["chapitre"])

    def test_upload_creates_collection_and_is_idempotent(self):
        summary = self._upload()
        self.assertTrue(summary["created"])
        self.assertEqual(summary["uploaded"], 3)
        self.assertEqual(
            self.client.count(collection_name="test", exact=True).count,
            3,
        )

        summary = self._upload(recreate=False)
        self.assertFalse(summary["created"])
        self.assertEqual(
            self.client.count(collection_name="test", exact=True).count,
            3,
        )

    def test_dimension_mismatch_is_rejected(self):
        self._upload()
        with self.assertRaises(ValueError):
            ensure_collection(self.client, "test", 2)

    def test_upload_rejects_duplicate_chunk_ids(self):
        with self.assertRaises(ValueError):
            upload_chunks(
                self.client,
                [self.chunks[0], self.chunks[0]],
                np.ones((2, 3), dtype=np.float32),
                collection="duplicate",
            )

    def test_upload_rejects_bad_matrices(self):
        with self.assertRaises(ValueError):
            upload_chunks(
                self.client,
                self.chunks,
                np.ones((1, 3), dtype=np.float32),
                collection="bad",
            )
        with self.assertRaises(ValueError):
            upload_chunks(
                self.client,
                self.chunks,
                np.zeros((3, 3), dtype=np.float32),
                collection="bad",
            )

    def test_search_returns_ranked_citation_metadata(self):
        self._upload()
        results = self._retriever().search("vente fonds", top_k=2)
        self.assertEqual(
            [result.chunk_id for result in results],
            [
                "code-commerce-tn:article-1:chunk-0",
                "code-commerce-tn:article-2:chunk-0",
            ],
        )
        self.assertEqual([result.rank for result in results], [1, 2])
        self.assertEqual(results[0].article_number, 1)
        self.assertEqual(results[0].pdf_page, 11)
        self.assertEqual(results[0].retrieval_method, "vector")
        self.assertEqual(results[0].heading_path, ("Livre II", "Titre I"))

    def test_search_applies_metadata_filters(self):
        self._upload()
        results = self._retriever().search(
            "vente fonds",
            top_k=3,
            filters={"document_id": "loi-59-129-1959"},
        )
        self.assertEqual(
            [result.chunk_id for result in results],
            ["loi-59-129-1959:article-1:chunk-0"],
        )

    def test_search_accepts_a_list_filter(self):
        self._upload()
        results = self._retriever().search(
            "vente fonds",
            top_k=3,
            filters={"document_id": ["code-commerce-tn"]},
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(
            all(
                result.record_id.startswith("code-commerce-tn:")
                for result in results
            )
        )

    def test_filter_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            build_filter({"unknown": "value"})

    def test_search_requires_positive_top_k(self):
        self._upload()
        with self.assertRaises(ValueError):
            self._retriever().search("vente fonds", top_k=0)

    def test_service_uses_qdrant_for_vector_and_hybrid(self):
        self._upload()
        service = RetrievalService(
            self.chunks,
            semantic_retriever=self._retriever(),
        )
        vector = service.retrieve("vente fonds", method="vector", top_k=1)
        self.assertEqual(vector[0].chunk_id, "code-commerce-tn:article-1:chunk-0")

        hybrid = service.retrieve(
            "fonds de commerce",
            method="hybrid",
            top_k=1,
        )
        self.assertEqual(hybrid[0].chunk_id, "code-commerce-tn:article-1:chunk-0")

    def test_service_pushes_filters_to_qdrant(self):
        self._upload()
        service = RetrievalService(
            self.chunks,
            semantic_retriever=self._retriever(),
        )
        results = service.retrieve(
            "vente fonds",
            method="vector",
            top_k=3,
            filters={"document_id": "loi-59-129-1959"},
        )
        self.assertEqual(
            [result.chunk_id for result in results],
            ["loi-59-129-1959:article-1:chunk-0"],
        )


if __name__ == "__main__":
    unittest.main()
