"""Tests for BM25 keyword retrieval."""
from __future__ import annotations

import unittest

import _paths  # noqa: F401

from indexing.chunking import ArticleChunk
from retrieval.bm25 import BM25Retriever, tokenize


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


class BM25Tests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            make_chunk(
                "article-189:chunk-0",
                189,
                "Le fonds de commerce comprend la clientèle et l'achalandage.",
            ),
            make_chunk(
                "article-190:chunk-0",
                190,
                "La vente du fonds de commerce doit être constatée par écrit.",
            ),
            make_chunk(
                "article-277:chunk-0",
                277,
                "La lettre de change désigne le tiré et le bénéficiaire.",
            ),
        ]
        self.retriever = BM25Retriever(self.chunks)

    def test_tokenizer_is_case_insensitive_and_keeps_french_words(self):
        self.assertEqual(tokenize("Éléments du FONDS"), ["éléments", "du", "fonds"])

    def test_search_returns_relevant_article_first(self):
        results = self.retriever.search("clientèle achalandage", top_k=2)
        self.assertEqual(results[0].record_id, "code-commerce-tn:article-189")
        self.assertEqual(results[0].retrieval_method, "bm25")
        self.assertEqual(results[0].rank, 1)

    def test_result_preserves_citation_metadata(self):
        result = self.retriever.search("clientèle", top_k=1)[0]
        self.assertEqual(result.article_number, 189)
        self.assertEqual(result.pdf_page, 11)
        self.assertEqual(result.source_url, "https://example.invalid/source.pdf")

    def test_unknown_terms_return_no_results(self):
        self.assertEqual(self.retriever.search("terme-inexistant"), [])

    def test_top_k_is_respected(self):
        self.assertEqual(len(self.retriever.search("fonds commerce", top_k=1)), 1)

    def test_invalid_options_are_rejected(self):
        with self.assertRaises(ValueError):
            BM25Retriever(self.chunks, k1=-1)
        with self.assertRaises(ValueError):
            BM25Retriever(self.chunks, b=2)
        with self.assertRaises(ValueError):
            self.retriever.search("fonds", top_k=0)

    def test_duplicate_chunk_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            BM25Retriever([self.chunks[0], self.chunks[0]])


if __name__ == "__main__":
    unittest.main()
