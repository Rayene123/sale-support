"""Tests for semantic retrieval without downloading a model."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

import _paths  # noqa: F401

from indexing.chunking import ArticleChunk
from retrieval.semantic import SemanticRetriever


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        return np.asarray([self.vectors[text] for text in texts], dtype=np.float32)


def make_chunk(chunk_id: str, article_number: int, text: str) -> ArticleChunk:
    return ArticleChunk(
        chunk_id=chunk_id,
        record_id=f"code-commerce-tn:article-{article_number}",
        text=text,
        chunk_index=0,
        chunk_count=1,
        article=f"Article {article_number}",
        article_number=article_number,
        heading_path=("Livre II — DU FONDS DE COMMERCE",),
        document_id="code-commerce-tn",
        language="fr",
        pdf_page=11,
        printed_page=11,
        source_url="https://example.invalid/source.pdf",
        source_sha256="a" * 64,
        source_date="2024-02-15",
        source_edition="edition",
    )


class SemanticRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            make_chunk("article-189:chunk-0", 189, "fonds"),
            make_chunk("article-277:chunk-0", 277, "lettre"),
        ]
        self.embedder = FakeEmbedder({
            "fonds": [1, 0],
            "lettre": [0, 1],
            "query fonds": [1, 0],
        })
        self.retriever = SemanticRetriever(self.chunks, embedder=self.embedder)

    def test_semantic_query_ranks_closest_chunk(self):
        results = self.retriever.search("query fonds", top_k=1)
        self.assertEqual(results[0].record_id, "code-commerce-tn:article-189")
        self.assertEqual(results[0].retrieval_method, "vector")

    def test_result_has_citation_metadata(self):
        result = self.retriever.search("query fonds", top_k=1)[0]
        self.assertEqual(result.article_number, 189)
        self.assertEqual(result.pdf_page, 11)

    def test_search_applies_metadata_filters(self):
        matching = self.retriever.search(
            "query fonds",
            top_k=2,
            filters={"document_id": "code-commerce-tn"},
        )
        self.assertEqual(matching[0].record_id, "code-commerce-tn:article-189")
        self.assertEqual(
            self.retriever.search(
                "query fonds",
                top_k=2,
                filters={"document_id": "other-document"},
            ),
            [],
        )

    def test_embeddings_can_be_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            self.retriever.save(directory)
            self.assertTrue((Path(directory) / "embeddings.npy").is_file())
            self.assertTrue((Path(directory) / "chunk_ids.txt").is_file())

    def test_invalid_embeddings_are_rejected(self):
        with self.assertRaises(ValueError):
            SemanticRetriever(self.chunks, embedder=self.embedder, embeddings=np.ones((1, 2)))
        with self.assertRaises(ValueError):
            SemanticRetriever(self.chunks, embedder=self.embedder, embeddings=np.zeros((2, 2)))


if __name__ == "__main__":
    unittest.main()
