"""Tests for loading processed corpus records for indexing."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import _paths  # noqa: F401

from indexing.corpus import CorpusLoadError, load_corpus
from ingestion.schema import ArticleRecord


def record_payload(**overrides) -> dict:
    text = "Font partie du fonds de commerce les biens mobiliers."
    payload = {
        "record_id": "code-commerce-tn:article-189",
        "document_id": "code-commerce-tn",
        "title": "Code de commerce tunisien",
        "language": "fr",
        "book": "Livre II — DU FONDS DE COMMERCE",
        "titre": None,
        "chapitre": "Chapitre I — Des éléments du fonds de commerce",
        "section": None,
        "sous_section": None,
        "heading_path": [
            "Livre II — DU FONDS DE COMMERCE",
            "Chapitre I — Des éléments du fonds de commerce",
        ],
        "article": "Article 189",
        "article_number": 189,
        "article_suffix": None,
        "status": "published",
        "amendment_notes": [],
        "amendment_laws": [],
        "text": text,
        "char_count": len(text),
        "source_url": "https://example.invalid/source.pdf",
        "source_sha256": "a" * 64,
        "source_date": "2024-02-15",
        "source_edition": "edition",
        "pdf_page": 11,
        "printed_page": 11,
    }
    payload.update(overrides)
    return payload


class CorpusLoaderTests(unittest.TestCase):
    def write_corpus(self, lines: list[object]) -> Path:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "corpus.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for line in lines:
                if isinstance(line, str):
                    handle.write(line + "\n")
                else:
                    handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.addCleanup(self.temp_dir.cleanup)
        return path

    def test_loads_valid_records_and_preserves_metadata(self):
        path = self.write_corpus([record_payload()])
        records = load_corpus(path)
        self.assertEqual(len(records), 1)
        self.assertIsInstance(records[0], ArticleRecord)
        self.assertEqual(records[0].heading_path[1], "Chapitre I — Des éléments du fonds de commerce")

    def test_repealed_records_are_excluded_by_default(self):
        repealed = record_payload(
            record_id="code-commerce-tn:article-6",
            article="Article 6",
            article_number=6,
            book="Livre I — DU COMMERCE EN GENERAL",
            chapitre=None,
            heading_path=["Livre I — DU COMMERCE EN GENERAL"],
            status="repealed",
            text="",
            char_count=0,
            amendment_laws=["2010-39"],
            pdf_page=8,
            printed_page=8,
        )
        path = self.write_corpus([repealed])
        self.assertEqual(load_corpus(path), [])
        self.assertEqual(len(load_corpus(path, include_repealed=True)), 1)

    def test_invalid_json_reports_line_number(self):
        path = self.write_corpus(["not json"])
        with self.assertRaisesRegex(CorpusLoadError, r":1: invalid JSON"):
            load_corpus(path)

    def test_invalid_record_is_rejected(self):
        path = self.write_corpus([record_payload(char_count=1)])
        with self.assertRaisesRegex(CorpusLoadError, "char_count"):
            load_corpus(path)

    def test_duplicate_record_ids_are_rejected(self):
        path = self.write_corpus([record_payload(), record_payload()])
        with self.assertRaisesRegex(CorpusLoadError, "duplicate record_id"):
            load_corpus(path)

    def test_missing_file_is_rejected(self):
        with self.assertRaisesRegex(CorpusLoadError, "corpus file not found"):
            load_corpus("does-not-exist.jsonl")


if __name__ == "__main__":
    unittest.main()
