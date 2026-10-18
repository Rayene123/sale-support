"""Vector retrieval integration tests against the processed corpus."""
from __future__ import annotations

import unittest

import _paths

from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from retrieval.vector import VectorRetriever


class RealCorpusVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        records = load_corpus(_paths.PROCESSED_DIR / "corpus.jsonl")
        cls.retriever = VectorRetriever(chunk_records(records))

    def test_all_searchable_chunks_are_indexed(self):
        self.assertEqual(self.retriever.chunk_count, 582)

    def test_fonds_query_finds_article_189(self):
        results = self.retriever.search("fonds de commerce", top_k=5)
        self.assertIn("code-commerce-tn:article-189", {r.record_id for r in results})

    def test_results_have_vector_method_and_citations(self):
        results = self.retriever.search("lettre de change", top_k=3)
        self.assertTrue(results)
        for result in results:
            self.assertEqual(result.retrieval_method, "vector")
            self.assertGreaterEqual(result.pdf_page, 1)
            self.assertTrue(result.source_url.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
