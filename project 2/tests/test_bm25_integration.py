"""BM25 integration tests against the committed processed corpus."""
from __future__ import annotations

import unittest

import _paths

from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from retrieval.bm25 import BM25Retriever


class RealCorpusBM25Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        records = load_corpus(_paths.PROCESSED_DIR / "corpus.jsonl")
        cls.records = records
        cls.chunks = chunk_records(records, strategy="article")
        cls.retriever = BM25Retriever(cls.chunks)

    def test_all_searchable_articles_are_indexed_once(self):
        self.assertEqual(len(self.records), 582)
        self.assertEqual(self.retriever.chunk_count, 582)
        self.assertEqual(
            {chunk.record_id for chunk in self.chunks},
            {record.record_id for record in self.records},
        )

    def test_fonds_de_commerce_query_finds_article_189(self):
        results = self.retriever.search("fonds de commerce", top_k=5)
        self.assertIn("code-commerce-tn:article-189", {result.record_id for result in results})

    def test_distinctive_article_terms_find_the_relevant_article(self):
        results = self.retriever.search("clientèle achalandage", top_k=5)
        self.assertIn("code-commerce-tn:article-189", {result.record_id for result in results})

    def test_results_have_consistent_ranking_and_citation_metadata(self):
        results = self.retriever.search("lettre de change bénéficiaire", top_k=5)
        self.assertTrue(results)
        self.assertEqual([result.rank for result in results], list(range(1, len(results) + 1)))
        self.assertEqual(
            [result.score for result in results],
            sorted((result.score for result in results), reverse=True),
        )
        for result in results:
            with self.subTest(result=result.record_id):
                self.assertTrue(result.chunk_id.endswith(":chunk-0"))
                self.assertTrue(result.record_id.startswith("code-commerce-tn:article-"))
                self.assertGreaterEqual(result.article_number, 1)
                self.assertGreaterEqual(result.pdf_page, 1)
                self.assertTrue(result.source_url.startswith("https://"))
                self.assertEqual(result.retrieval_method, "bm25")

    def test_top_k_limits_real_corpus_results(self):
        self.assertLessEqual(len(self.retriever.search("commerce", top_k=3)), 3)

    def test_unknown_question_terms_return_no_results(self):
        self.assertEqual(self.retriever.search("zzzztermexxxxxxxxx"), [])


if __name__ == "__main__":
    unittest.main()
