"""End-to-end build test against the real, hash-verified source PDF.

Skipped when the source PDF is absent, which is normal on a fresh clone: the
raw PDFs are intentionally not committed. Run the build first, or just run this
test after ``python "project 2/scripts/build_corpus.py"``::

    python -m unittest discover -s "project 2/tests" -p "test_*.py" -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import _paths
from ingestion.build import build_corpus
from ingestion.pdf_text import extract_pages
from ingestion.sources import REJECTED_SOURCES, SOURCES, source_by_id
from ingestion.structure import StructureError

SOURCE = SOURCES[0]
SOURCE_PDF = _paths.RAW_DIR / f"{SOURCE.source_id}.pdf"

# The 2014 consolidated edition: 746 numbered articles of which 207 were
# repealed at that date, plus 8 lettered variants (bis/ter/septies) and the
# 5 articles of the promulgating law.
EXPECTED_CODE_RECORDS = 547
EXPECTED_LAW_RECORDS = 5
EXPECTED_MISSING_AS_REPEALED = 207
EXPECTED_REPEALED_RANGES = [{"start": 14, "end": 188}, {"start": 413, "end": 444}]


@unittest.skipUnless(SOURCE_PDF.is_file(), f"source PDF not present at {SOURCE_PDF}")
class RealCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out_dir = Path(cls._tmp.name) / "processed"
        cls.result = build_corpus(raw_dir=_paths.RAW_DIR, out_dir=cls.out_dir, allow_download=False)
        cls.by_id = {record.record_id: record for record in cls.result.records}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- counts ------------------------------------------------------------
    def test_record_counts(self):
        code = sum(1 for r in self.result.records if r.document_id == "code-commerce-tn")
        law = sum(1 for r in self.result.records if r.document_id == "loi-59-129-1959")
        self.assertEqual(code, EXPECTED_CODE_RECORDS)
        self.assertEqual(law, EXPECTED_LAW_RECORDS)
        self.assertEqual(len(self.result.records), EXPECTED_CODE_RECORDS + EXPECTED_LAW_RECORDS)

    def test_every_record_passes_validation(self):
        # build_corpus already enforces this; re-check through the public helper.
        from ingestion.schema import validate_record

        problems = {r.record_id: validate_record(r) for r in self.result.records}
        self.assertEqual({k: v for k, v in problems.items() if v}, {})

    # -- coverage ----------------------------------------------------------
    def test_missing_articles_are_all_explained_by_repeal(self):
        coverage = self.result.manifest["coverage"]["code-commerce-tn"]
        self.assertEqual(coverage["number_min"], 1)
        self.assertEqual(coverage["number_max"], 746)
        self.assertEqual(len(coverage["missing_explained_as_abrogated"]), EXPECTED_MISSING_AS_REPEALED)
        self.assertEqual(coverage["missing_unexplained"], [])

    def test_repealed_ranges_match_the_table_of_contents(self):
        self.assertEqual(
            self.result.toc_inventory["abrogated_ranges"], EXPECTED_REPEALED_RANGES
        )

    def test_build_reports_no_warnings(self):
        self.assertEqual(self.result.warnings, [])

    # -- known articles ----------------------------------------------------
    def test_first_article_of_the_code(self):
        article = self.by_id["code-commerce-tn:article-1"]
        self.assertTrue(article.text.startswith("Le présent code s'applique aux commerçants"))
        self.assertEqual(article.book, "Livre I — DU COMMERCE EN GENERAL")
        self.assertEqual(article.status, "published")
        self.assertIsNone(article.article_suffix)

    def test_last_article_of_the_code(self):
        self.assertIn("code-commerce-tn:article-746", self.by_id)
        self.assertNotIn("code-commerce-tn:article-747", self.by_id)

    def test_repealed_article_is_present_but_empty(self):
        article = self.by_id["code-commerce-tn:article-6"]
        self.assertEqual(article.status, "repealed")
        self.assertEqual(article.text, "")
        self.assertEqual(article.amendment_laws, ["2010-39"])

    def test_lettered_article_variants_exist(self):
        for record_id in (
            "code-commerce-tn:article-189-bis",
            "code-commerce-tn:article-411-septies",
            "code-commerce-tn:article-412-ter",
        ):
            self.assertIn(record_id, self.by_id)

    def test_an_article_with_a_wrapped_amendment_note(self):
        article = self.by_id["code-commerce-tn:article-231"]
        self.assertEqual(article.amendment_laws, ["2000-61"])
        self.assertIn("modifié", article.amendment_notes[0])

    def test_deep_heading_hierarchy_is_preserved(self):
        article = self.by_id["code-commerce-tn:article-277"]
        self.assertEqual(
            article.heading_path,
            [
                "Livre III — DE LA LETTRE DE CHANGE, DU BILLET A ORDRE ET DU CHEQUE",
                "Chapitre I — De la lettre de change",
                "Section III — De l'endossement",
            ],
        )

    def test_every_heading_level_is_titled(self):
        for level in ("book", "titre", "chapitre", "section", "sous_section"):
            untitled = {getattr(r, level) for r in self.result.records if getattr(r, level)}
            for label in untitled:
                self.assertIn(" — ", label, f"{level} without a title: {label}")

    def test_promulgating_law_is_a_separate_document(self):
        article = self.by_id["loi-59-129-1959:article-1"]
        self.assertEqual(article.article_number, 1)
        self.assertTrue(article.text.startswith("Les textes publiés ci-après"))
        # The promulgation formula ("Au nom du Peuple, ...") is printed above the
        # law's first article, so it is kept as front matter, not article text.
        self.assertIn("Au nom du Peuple", self._law_front_matter())

    def _law_front_matter(self) -> str:
        for annotation in self.result.annotations:
            if annotation["annotation_id"] == "loi-59-129-1959:front-matter":
                return annotation["text"]
        return ""

    # -- annotations -------------------------------------------------------
    def test_footnotes_are_kept_out_of_article_text(self):
        footnotes = [a for a in self.result.annotations if a["record_type"] == "footnote"]
        self.assertEqual(len(footnotes), 17)
        for footnote in footnotes:
            self.assertTrue(footnote["text"])
        self.assertIn(
            "loi n°2007-37",
            " ".join(a["text"] for a in footnotes),
        )
        for record in self.result.records:
            self.assertNotIn("Rectificatif paru au JORT", record.text)

    def test_a_shared_page_footnote_is_attributed_to_one_document_only(self):
        # The law region ends with blank lines that spill onto the code's first
        # page ("CODE DE COMMERCE(1)"). The footnote printed at the bottom of
        # that page belongs to the code, so it must not also be counted for the
        # law.
        law_notes = [
            a
            for a in self.result.annotations
            if a["record_type"] == "footnote" and a["document_id"] == "loi-59-129-1959"
        ]
        code_notes = [
            a
            for a in self.result.annotations
            if a["record_type"] == "footnote" and a["document_id"] == "code-commerce-tn"
        ]
        self.assertEqual([a["pdf_page"] for a in law_notes], [3])
        self.assertEqual(len(law_notes) + len(code_notes), 17)

    def test_repeal_notice_between_articles_is_kept_as_unattached_text(self):
        unattached = [a for a in self.result.annotations if a["record_type"] == "unattached_text"]
        self.assertEqual(len(unattached), 1)
        self.assertIn("14 à 188", unattached[0]["text"])

    # -- artefacts and determinism ----------------------------------------
    def test_artefacts_are_written_with_recorded_digests(self):
        import hashlib

        for name in ("corpus.jsonl", "annotations.jsonl", "toc_inventory.json"):
            path = self.out_dir / name
            self.assertTrue(path.is_file(), name)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(self.result.manifest["outputs"][name], digest)

    def test_corpus_jsonl_matches_the_records(self):
        lines = (self.out_dir / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), len(self.result.records))
        first = json.loads(lines[0])
        self.assertEqual(first["record_id"], "code-commerce-tn:article-1")

    def test_rebuild_is_byte_identical(self):
        import hashlib

        def digest_of(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        first = {
            name: digest_of(self.out_dir / name)
            for name in ("corpus.jsonl", "annotations.jsonl", "toc_inventory.json")
        }
        with tempfile.TemporaryDirectory() as tmp:
            second_dir = Path(tmp) / "processed"
            build_corpus(raw_dir=_paths.RAW_DIR, out_dir=second_dir, allow_download=False)
            second = {
                name: digest_of(second_dir / name)
                for name in ("corpus.jsonl", "annotations.jsonl", "toc_inventory.json")
            }
        self.assertEqual(first, second)


@unittest.skipUnless(SOURCE_PDF.is_file(), f"source PDF not present at {SOURCE_PDF}")
class SourceIntegrityTests(unittest.TestCase):
    def test_the_rejected_arabic_source_is_documented_with_evidence(self):
        arabic = REJECTED_SOURCES[0]
        self.assertEqual(arabic.language, "ar")
        self.assertEqual(arabic.reason, "no-extractable-text-layer")
        self.assertIn("ToUnicode", arabic.evidence)

    def test_document_specs_point_at_a_registered_source(self):
        for document in SOURCES:
            source_by_id(document.source_id)

    def test_page_numbers_printed_match_the_pdf_position(self):
        pages = extract_pages(SOURCE_PDF)
        self.assertEqual(len(pages), 219)
        self.assertEqual(pages[6].printed_number_seen, 7)

    def test_no_region_marker_is_missing(self):
        # A missing marker must raise rather than silently mis-split the file.
        from ingestion.structure import build_stream, detect_regions

        regions = detect_regions(build_stream(extract_pages(SOURCE_PDF)))
        law_start, code_start = regions.bounds("law")
        self.assertLess(law_start, code_start)
        self.assertLess(code_start, regions.toc_start)
        with self.assertRaises(StructureError):
            regions.bounds("appendix")


if __name__ == "__main__":
    unittest.main()
