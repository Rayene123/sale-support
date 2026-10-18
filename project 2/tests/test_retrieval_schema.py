"""Tests for the shared retrieval-result contract."""
from __future__ import annotations

import json
import unittest

import _paths  # noqa: F401

from models.retrieval import RetrievalResult


def make_result(**overrides) -> RetrievalResult:
    payload = {
        "chunk_id": "code-commerce-tn:article-189:chunk-0",
        "record_id": "code-commerce-tn:article-189",
        "text": "Font partie du fonds de commerce les biens mobiliers.",
        "score": 1.25,
        "rank": 1,
        "article_number": 189,
        "article": "Article 189",
        "heading_path": (
            "Livre II — DU FONDS DE COMMERCE",
            "Chapitre I — Des éléments du fonds de commerce",
        ),
        "pdf_page": 11,
        "source_url": "https://example.invalid/source.pdf",
        "retrieval_method": "bm25",
    }
    payload.update(overrides)
    return RetrievalResult(**payload)


class RetrievalResultTests(unittest.TestCase):
    def test_complete_result_is_valid(self):
        result = make_result()
        self.assertEqual(result.rank, 1)
        self.assertEqual(result.heading_path[1], "Chapitre I — Des éléments du fonds de commerce")

    def test_serialization_is_json_compatible_and_stable(self):
        result = make_result()
        payload = json.loads(result.to_json())
        self.assertEqual(payload["heading_path"][0], "Livre II — DU FONDS DE COMMERCE")
        self.assertEqual(result.to_json(), result.to_json())

    def test_citation_metadata_is_required(self):
        for field, value in (
            ("chunk_id", ""),
            ("record_id", ""),
            ("text", ""),
            ("article", ""),
            ("source_url", "not-a-url"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    make_result(**{field: value})

    def test_rank_and_page_must_be_positive(self):
        with self.assertRaises(ValueError):
            make_result(rank=0)
        with self.assertRaises(ValueError):
            make_result(pdf_page=0)

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(ValueError):
            make_result(retrieval_method="unknown")


if __name__ == "__main__":
    unittest.main()
