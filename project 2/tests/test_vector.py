"""Tests for local TF-IDF vector retrieval."""
from __future__ import annotations

import unittest

import _paths  # noqa: F401

from indexing.chunking import ArticleChunk
from retrieval.vector import VectorRetriever


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


class VectorRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            make_chunk("article-189:chunk-0", 189, "clientèle achalandage fonds"),
            make_chunk("article-190:chunk-0", 190, "vente fonds commerce écrit"),
            make_chunk("article-277:chunk-0", 277, "lettre change bénéficiaire"),
        ]
        self.retriever = VectorRetriever(self.chunks)

    def test_search_returns_the_matching_vector_first(self):
        results = self.retriever.search("clientèle achalandage", top_k=2)
        self.assertEqual(results[0].record_id, "code-commerce-tn:article-189")
        self.assertEqual(results[0].retrieval_method, "vector")
        self.assertGreater(results[0].score, 0)

    def test_result_preserves_citation_metadata(self):
        result = self.retriever.search("bénéficiaire", top_k=1)[0]
        self.assertEqual(result.article_number, 277)
        self.assertEqual(result.pdf_page, 11)
        self.assertEqual(result.source_url, "https://example.invalid/source.pdf")

    def test_unknown_terms_return_no_results(self):
        self.assertEqual(self.retriever.search("zzzztermexxxxxxxxx"), [])

    def test_top_k_and_ranking_are_respected(self):
        results = self.retriever.search("fonds", top_k=2)
        self.assertLessEqual(len(results), 2)
        self.assertEqual([result.rank for result in results], [1, 2])
        self.assertEqual(
            [result.score for result in results],
            sorted((result.score for result in results), reverse=True),
        )

    def test_duplicate_chunk_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            VectorRetriever([self.chunks[0], self.chunks[0]])

    def test_invalid_top_k_is_rejected(self):
        with self.assertRaises(ValueError):
            self.retriever.search("fonds", top_k=0)


if __name__ == "__main__":
    unittest.main()
