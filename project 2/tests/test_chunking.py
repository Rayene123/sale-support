"""Tests for article-aware corpus chunking."""
from __future__ import annotations

import unittest
from pathlib import Path

import _paths  # noqa: F401

from indexing.chunking import chunk_article, chunk_metadata, chunk_records
from indexing.corpus import load_corpus
from ingestion.schema import ArticleRecord
from retrieval.filters import filter_chunks


def make_record(text: str = " ".join(f"word{i}" for i in range(10))) -> ArticleRecord:
    return ArticleRecord(
        record_id="code-commerce-tn:article-189",
        document_id="code-commerce-tn",
        title="Code de commerce tunisien",
        language="fr",
        book="Livre II — DU FONDS DE COMMERCE",
        titre=None,
        chapitre="Chapitre I — Des éléments du fonds de commerce",
        section=None,
        sous_section=None,
        heading_path=(
            "Livre II — DU FONDS DE COMMERCE",
            "Chapitre I — Des éléments du fonds de commerce",
        ),
        article="Article 189",
        article_number=189,
        article_suffix=None,
        status="published",
        amendment_notes=[],
        amendment_laws=[],
        text=text,
        char_count=len(text),
        source_url="https://example.invalid/source.pdf",
        source_sha256="a" * 64,
        source_date="2024-02-15",
        source_edition="edition",
        pdf_page=11,
        printed_page=11,
    )


class ChunkingTests(unittest.TestCase):
    def test_named_metadata_matches_every_published_corpus_record(self):
        records = load_corpus(Path(__file__).resolve().parents[1] / "data/processed/corpus.jsonl")
        for record in records:
            with self.subTest(record=record.record_id):
                chunk = chunk_article(record)[0]
                metadata = chunk_metadata(chunk)
                self.assertEqual(metadata, {key: getattr(record, key) for key in metadata})
                self.assertEqual(filter_chunks([chunk], metadata), [chunk])

    def test_suffix_filters_distinguish_plain_bis_and_ter_articles(self):
        chunks = []
        for suffix in (None, "bis", "ter"):
            record = make_record()
            record.article_suffix = suffix
            if suffix:
                record.record_id += "-" + suffix
            chunks.extend(chunk_article(record))
        self.assertEqual(filter_chunks(chunks, {"article_suffix": None}), chunks[:1])
        self.assertEqual(filter_chunks(chunks, {"article_suffix": ["bis", "ter"]}), chunks[1:])
        self.assertEqual(filter_chunks(chunks, {"article_suffix": "quater"}), [])

    def test_article_strategy_keeps_an_article_as_one_chunk(self):
        chunks = chunk_article(make_record(), strategy="article")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "code-commerce-tn:article-189:chunk-0")
        self.assertEqual(chunks[0].text, make_record().text)

    def test_window_strategy_splits_long_articles(self):
        record = make_record(" ".join(f"word{i}" for i in range(10)))
        chunks = chunk_article(record, strategy="window", max_words=4, overlap_words=1)
        self.assertEqual([len(chunk.text.split()) for chunk in chunks], [4, 4, 4])
        self.assertEqual(chunks[0].text.split()[-1], chunks[1].text.split()[0])
        self.assertEqual({chunk.chunk_count for chunk in chunks}, {3})

    def test_every_chunk_preserves_citation_and_heading_metadata(self):
        chunks = chunk_article(make_record(" ".join(f"word{i}" for i in range(8))), strategy="window", max_words=3, overlap_words=1)
        for chunk in chunks:
            with self.subTest(chunk=chunk.chunk_id):
                self.assertEqual(chunk.record_id, "code-commerce-tn:article-189")
                self.assertEqual(chunk.article_number, 189)
                self.assertEqual(chunk.pdf_page, 11)
                self.assertEqual(chunk.heading_path[1], "Chapitre I — Des éléments du fonds de commerce")
                self.assertEqual(chunk.source_url, "https://example.invalid/source.pdf")

    def test_repealed_records_produce_no_chunks(self):
        record = make_record(text="")
        record.status = "repealed"
        record.char_count = 0
        self.assertEqual(chunk_article(record), [])

    def test_empty_published_records_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "published article has empty text"):
            chunk_article(make_record(text=""))

    def test_invalid_window_options_are_rejected(self):
        with self.assertRaises(ValueError):
            chunk_article(make_record(), strategy="unknown")
        with self.assertRaises(ValueError):
            chunk_article(make_record(), max_words=2, overlap_words=2)

    def test_chunk_records_preserves_record_order(self):
        first = make_record()
        second = make_record()
        second.record_id = "code-commerce-tn:article-190"
        second.article = "Article 190"
        second.article_number = 190
        chunks = chunk_records([first, second])
        self.assertEqual([chunk.record_id for chunk in chunks], [
            "code-commerce-tn:article-189",
            "code-commerce-tn:article-190",
        ])


if __name__ == "__main__":
    unittest.main()
