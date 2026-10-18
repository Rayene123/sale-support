"""Tests for filters, hybrid fusion, reranking, and the retrieval facade."""
from __future__ import annotations

import unittest

import numpy as np

import _paths  # noqa: F401

from indexing.chunking import ArticleChunk
from retrieval.filters import filter_chunks
from retrieval.hybrid import HybridRetriever
from retrieval.rerank import rerank
from retrieval.service import RetrievalService


class FakeEmbedder:
    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        return np.asarray(
            [[1.0, 0.0] if "fonds" in text else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )


def make_chunk(number: int, text: str, book: str) -> ArticleChunk:
    return ArticleChunk(
        chunk_id=f"article-{number}:chunk-0",
        record_id=f"code-commerce-tn:article-{number}",
        text=text,
        chunk_index=0,
        chunk_count=1,
        article=f"Article {number}",
        article_number=number,
        heading_path=(book,),
        document_id="code-commerce-tn",
        language="fr",
        pdf_page=11,
        printed_page=11,
        source_url="https://example.invalid/source.pdf",
        source_sha256="a" * 64,
        source_date="2024-02-15",
        source_edition="edition",
    )


class RetrievalPipelineTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            make_chunk(189, "fonds clientèle", "Livre II"),
            make_chunk(277, "lettre bénéficiaire", "Livre III"),
        ]

    def test_metadata_filter_restricts_candidates(self):
        filtered = filter_chunks(self.chunks, {"article_number": 189})
        self.assertEqual([chunk.article_number for chunk in filtered], [189])

    def test_unknown_filter_is_rejected(self):
        with self.assertRaises(ValueError):
            filter_chunks(self.chunks, {"unknown": "value"})

    def test_hybrid_returns_citation_result(self):
        results = HybridRetriever(self.chunks, embedder=FakeEmbedder()).search(
            "fonds", top_k=1
        )
        self.assertEqual(results[0].record_id, "code-commerce-tn:article-189")
        self.assertEqual(results[0].retrieval_method, "hybrid")

    def test_reranker_returns_reranked_method(self):
        candidates = RetrievalService(
            self.chunks, embedder=FakeEmbedder()
        ).retrieve("fonds", method="bm25", top_k=2)
        results = rerank("fonds", candidates, top_k=1)
        self.assertEqual(results[0].retrieval_method, "reranked")
        self.assertEqual(results[0].rank, 1)

    def test_service_supports_filtered_vector_search(self):
        results = RetrievalService(
            self.chunks, embedder=FakeEmbedder()
        ).retrieve(
            "fonds",
            method="vector",
            filters={"article_number": 189},
            top_k=5,
        )
        self.assertEqual([result.article_number for result in results], [189])


if __name__ == "__main__":
    unittest.main()
