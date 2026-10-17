"""Tests for the record schema and its validation rules."""
from __future__ import annotations

import unittest

import _paths  # noqa: F401

from ingestion.schema import ArticleRecord, validate_record


def make_record(**overrides) -> ArticleRecord:
    payload = {
        "record_id": "code-commerce-tn:article-277",
        "document_id": "code-commerce-tn",
        "title": "Code de commerce tunisien",
        "language": "fr",
        "book": "Livre III — DE LA LETTRE DE CHANGE",
        "titre": None,
        "chapitre": "Chapitre I — De la lettre de change",
        "section": None,
        "sous_section": None,
        "heading_path": [
            "Livre III — DE LA LETTRE DE CHANGE",
            "Chapitre I — De la lettre de change",
        ],
        "article": "Article 277",
        "article_number": 277,
        "article_suffix": None,
        "status": "published",
        "amendment_notes": [],
        "amendment_laws": [],
        "text": "L'endossement transmet tous les droits résultant de la lettre de change.",
        "char_count": len("L'endossement transmet tous les droits résultant de la lettre de change."),
        "source_url": "https://example.invalid/source.pdf",
        "source_sha256": "a" * 64,
        "source_date": "2014-02-15",
        "source_edition": "edition",
        "pdf_page": 51,
        "printed_page": 51,
    }
    payload.update(overrides)
    return ArticleRecord(**payload)


class ValidRecordTests(unittest.TestCase):
    def test_a_complete_record_is_valid(self):
        self.assertEqual(validate_record(make_record()), [])

    def test_optional_headings_may_be_absent(self):
        record = make_record(
            book=None, titre=None, chapitre=None, section=None, sous_section=None, heading_path=[]
        )
        self.assertEqual(validate_record(record), [])


class InvalidRecordTests(unittest.TestCase):
    def test_record_id_must_follow_the_stable_pattern(self):
        self.assertTrue(validate_record(make_record(record_id="article 277")))

    def test_suffix_must_be_a_known_one(self):
        problems = validate_record(make_record(article_suffix="octies"))
        self.assertEqual(problems, [])
        self.assertTrue(validate_record(make_record(article_suffix="whatever")))

    def test_published_article_needs_text(self):
        record = make_record(text="", char_count=0)
        self.assertTrue(any("shorter than" in problem for problem in validate_record(record)))

    def test_repealed_article_may_be_empty(self):
        record = make_record(status="repealed", text="", char_count=0)
        self.assertEqual(validate_record(record), [])

    def test_repealed_article_must_not_carry_text(self):
        record = make_record(status="repealed")
        self.assertTrue(any("must not carry" in problem for problem in validate_record(record)))

    def test_unknown_status_is_rejected(self):
        self.assertTrue(validate_record(make_record(status="maybe")))

    def test_char_count_must_match(self):
        self.assertTrue(validate_record(make_record(char_count=1)))

    def test_heading_path_must_match_the_heading_fields(self):
        record = make_record(heading_path=["Livre III — DE LA LETTRE DE CHANGE"])
        self.assertTrue(any("heading_path" in problem for problem in validate_record(record)))

    def test_source_url_and_hash_are_required(self):
        self.assertTrue(validate_record(make_record(source_url="ftp://example.invalid/x")))
        self.assertTrue(validate_record(make_record(source_sha256="not-a-hash")))

    def test_page_numbers_must_be_positive(self):
        self.assertTrue(validate_record(make_record(pdf_page=0)))
        self.assertTrue(validate_record(make_record(printed_page=0)))

    def test_amendment_law_references_are_checked(self):
        self.assertEqual(validate_record(make_record(amendment_laws=["96-28"])), [])
        self.assertTrue(validate_record(make_record(amendment_laws=["loi 96-28"])))


class SerialisationTests(unittest.TestCase):
    def test_json_is_stable_and_keeps_accents(self):
        record = make_record()
        first = record.to_json()
        self.assertEqual(first, record.to_json())
        self.assertIn("L'endossement", first)
        self.assertIn('"article_suffix": null', first)

    def test_sort_key_orders_suffixes_after_the_base_article(self):
        base = make_record()
        bis = make_record(article_suffix="bis", record_id="code-commerce-tn:article-277-bis")
        ter = make_record(article_suffix="ter", record_id="code-commerce-tn:article-277-ter")
        self.assertLess(base.sort_key, bis.sort_key)
        self.assertLess(bis.sort_key, ter.sort_key)


if __name__ == "__main__":
    unittest.main()
