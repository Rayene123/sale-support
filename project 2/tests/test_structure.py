"""Tests for structure detection, article splitting and record assembly."""
from __future__ import annotations

import unittest

import _fixtures
import _paths  # noqa: F401

from ingestion.sources import CODE_COMMERCE_FR, DOCUMENTS
from ingestion.structure import (
    StructureError,
    build_stream,
    detect_regions,
    extract_law_references,
    is_continuation_candidate,
    match_heading,
    normalize_numeral,
    note_is_complete,
    parse_article_header,
    parse_region,
    record_id_for,
    status_from_note,
)

CODE_SPEC = DOCUMENTS[0]
LAW_SPEC = DOCUMENTS[1]


class NumeralTests(unittest.TestCase):
    def test_word_numerals_become_roman(self):
        self.assertEqual(normalize_numeral("PREMIER"), "I")
        self.assertEqual(normalize_numeral("1er"), "I")
        self.assertEqual(normalize_numeral("ii"), "II")

    def test_unknown_numeral_is_preserved_upper_case(self):
        self.assertEqual(normalize_numeral("xiv"), "XIV")


class HeadingTests(unittest.TestCase):
    def test_book_heading(self):
        self.assertEqual(match_heading("LIVRE PREMIER"), ("book", "PREMIER", ""))
        self.assertEqual(match_heading("LIVRE III(1)"), ("book", "III", ""))

    def test_chapter_heading_is_not_matched_as_section(self):
        self.assertEqual(match_heading("CHAPITRE PREMIER"), ("chapitre", "PREMIER", ""))

    def test_section_titles_on_the_same_line(self):
        level, numeral, title = match_heading("Section I. - De la vente et de la promesse de vente")
        self.assertEqual((level, numeral), ("section", "I"))
        self.assertEqual(title, "De la vente et de la promesse de vente")

    def test_subsection_is_detected_before_section(self):
        level, numeral, title = match_heading("Sous-section I.- De la publicité de la vente")
        self.assertEqual((level, numeral), ("sous_section", "I"))
        self.assertEqual(title, "De la publicité de la vente")

    def test_body_text_is_not_a_heading(self):
        self.assertIsNone(match_heading("Toute personne capable de s'obliger peut exercer le"))
        self.assertIsNone(match_heading("Section 5 du registre du commerce"))


class ArticleHeaderTests(unittest.TestCase):
    def test_plain_article(self):
        self.assertEqual(parse_article_header("Article 277"), (277, None, None))

    def test_premier_maps_to_one(self):
        self.assertEqual(parse_article_header("Article premier"), (1, None, None))

    def test_suffix(self):
        self.assertEqual(parse_article_header("Article 189 bis"), (189, "bis", None))

    def test_trailing_period(self):
        self.assertEqual(parse_article_header("Article 372. (Paragraphe 2 modifié)"), (372, None, "(Paragraphe 2 modifié)"))

    def test_article_references_in_body_text_are_not_headers(self):
        self.assertIsNone(parse_article_header("Article 411 et suivants du présent code."))
        self.assertIsNone(parse_article_header("conformément aux articles 411 et suivants"))
        self.assertIsNone(parse_article_header("Est commerçant, quiconque, à titre professionnel"))


class NoteTests(unittest.TestCase):
    def test_note_is_complete_when_parentheses_balance(self):
        self.assertTrue(note_is_complete("(Abrogé par la loi n° 95-35 du 17 avril 1995)."))
        self.assertFalse(note_is_complete("(Le deuxième paragraphe a été modifié par la"))

    def test_law_references_are_normalised(self):
        self.assertEqual(extract_law_references("(Modifié par la loi n° 96-28 du 3 avril 1996)"), ["96-28"])
        self.assertEqual(extract_law_references("(Ajouté par la loi n° 2000 - 61 du 20 juin 2000)"), ["2000-61"])
        self.assertEqual(extract_law_references("no reference here"), [])

    def test_repeal_status_comes_from_the_note(self):
        self.assertEqual(status_from_note("(Abrogé par la loi n° 95-35)"), "repealed")
        self.assertEqual(status_from_note("(Modifié par la loi n° 96-28)"), "published")
        self.assertEqual(status_from_note(None), "published")


class ContinuationTests(unittest.TestCase):
    def test_upper_case_title_continues_a_book(self):
        self.assertTrue(is_continuation_candidate("book", "DU COMMERCE EN GENERAL"))
        self.assertTrue(is_continuation_candidate("book", "A ORDRE ET DU CHEQUE"))

    def test_sentence_after_a_title_does_not_continue_it(self):
        self.assertFalse(
            is_continuation_candidate(
                "titre", "Les dispositions du titre III du livre premier (les articles"
            )
        )

    def test_parenthetical_notice_never_continues_a_heading(self):
        self.assertFalse(is_continuation_candidate("titre", "(Les Articles 413 à 444 sont abrogés"))

    def test_numbered_sub_item_never_continues_a_heading(self):
        self.assertFalse(is_continuation_candidate("section", "1. - Des recours faute de payement"))

    def test_chapter_title_on_its_own_line_is_accepted(self):
        self.assertTrue(is_continuation_candidate("chapitre", "Des éléments du fonds de commerce"))
        self.assertTrue(is_continuation_candidate("chapitre", "De la déclaration de faillite"))

    def test_chapter_wrap_in_lower_case_is_accepted(self):
        self.assertTrue(is_continuation_candidate("chapitre", "et au nantissement du fonds de commerce"))

    def test_headings_and_articles_stop_the_title(self):
        self.assertFalse(is_continuation_candidate("chapitre", "CHAPITRE III"))
        self.assertFalse(is_continuation_candidate("chapitre", "Article 189 bis"))


class RegionTests(unittest.TestCase):
    def test_regions_are_located(self):
        regions = detect_regions(_fixtures.sample_stream())
        self.assertEqual(regions.law_start, _fixtures.LAW_START)
        self.assertEqual(regions.code_start, _fixtures.CODE_START)
        self.assertEqual(regions.toc_start, _fixtures.TOC_START)
        self.assertEqual(regions.bounds("law"), (_fixtures.LAW_START, _fixtures.CODE_START))
        self.assertEqual(regions.bounds("code"), (_fixtures.CODE_START, _fixtures.TOC_START))

    def test_missing_toc_fails_loudly(self):
        stream = [line for line in _fixtures.sample_stream() if "TABLE DES MATIERES" not in line.text]
        with self.assertRaises(StructureError):
            detect_regions(stream)

    def test_missing_livre_fails_loudly(self):
        stream = [line for line in _fixtures.sample_stream() if not line.text.startswith("LIVRE")]
        with self.assertRaises(StructureError):
            detect_regions(stream)

    def test_stream_keeps_page_numbers(self):
        stream = build_stream(_pages())
        self.assertEqual(stream[0].pdf_page, 7)

    def test_unknown_region_is_rejected(self):
        with self.assertRaises(StructureError):
            detect_regions(_fixtures.sample_stream()).bounds("appendix")


class ParseRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stream = _fixtures.sample_stream()
        cls.regions = detect_regions(cls.stream)
        cls.code = parse_region(cls.stream, cls.regions.bounds("code"), CODE_SPEC, CODE_COMMERCE_FR)
        cls.law = parse_region(cls.stream, cls.regions.bounds("law"), LAW_SPEC, CODE_COMMERCE_FR)
        cls.by_id = {record.record_id: record for record in cls.code.records}

    def test_every_article_is_found(self):
        self.assertEqual(
            sorted(self.by_id),
            [
                "code-commerce-tn:article-1",
                "code-commerce-tn:article-189-bis",
                "code-commerce-tn:article-2",
                "code-commerce-tn:article-231",
                "code-commerce-tn:article-6",
                "code-commerce-tn:article-7",
            ],
        )

    def test_wrapped_body_is_rejoined(self):
        article = self.by_id["code-commerce-tn:article-1"]
        self.assertEqual(
            article.text,
            "Le présent code s'applique aux commerçants et aux actes de commerce.",
        )

    def test_bullets_keep_their_own_lines(self):
        self.assertIn("\n- à l'achat et à la vente des biens;", self.by_id["code-commerce-tn:article-2"].text)

    def test_repealed_article_is_kept_without_text(self):
        article = self.by_id["code-commerce-tn:article-6"]
        self.assertEqual(article.status, "repealed")
        self.assertEqual(article.text, "")
        self.assertEqual(article.amendment_laws, ["95-35"])

    def test_wrapped_amendment_note_is_joined(self):
        article = self.by_id["code-commerce-tn:article-231"]
        self.assertEqual(len(article.amendment_notes), 1)
        self.assertIn("2000 - 61", article.amendment_notes[0])
        self.assertEqual(article.amendment_laws, ["2000-61"])
        self.assertEqual(article.text, "Le premier paragraphe reste inchangé.")

    def test_suffix_article_keeps_its_number_and_suffix(self):
        article = self.by_id["code-commerce-tn:article-189-bis"]
        self.assertEqual(article.article_number, 189)
        self.assertEqual(article.article_suffix, "bis")
        self.assertEqual(article.status, "published")

    def test_heading_path_is_complete_and_ordered(self):
        article = self.by_id["code-commerce-tn:article-189-bis"]
        self.assertEqual(
            article.heading_path,
            [
                "Livre II — DU FONDS DE COMMERCE",
                "Chapitre II — Des contrats relatifs au fonds de commerce",
                "Section I — De la vente et de la promesse de vente",
                "Sous-section I — De la publicité de la vente du fonds de commerce",
            ],
        )
        self.assertIsNone(article.titre)

    def test_a_new_book_clears_deeper_levels(self):
        article = self.by_id["code-commerce-tn:article-7"]
        self.assertEqual(article.book, "Livre I — DU COMMERCE EN GENERAL")
        self.assertEqual(article.titre, "Titre II — DES LIVRES DE COMMERCE")
        self.assertIsNone(article.chapitre)

    def test_page_numbers_are_recorded(self):
        self.assertEqual(self.by_id["code-commerce-tn:article-7"].pdf_page, 9)
        self.assertEqual(self.by_id["code-commerce-tn:article-7"].printed_page, 9)

    def test_source_provenance_is_attached(self):
        article = self.by_id["code-commerce-tn:article-1"]
        self.assertEqual(article.source_url, CODE_COMMERCE_FR.url)
        self.assertEqual(article.source_sha256, CODE_COMMERCE_FR.sha256)
        self.assertEqual(article.source_date, CODE_COMMERCE_FR.edition_date)

    def test_article_text_does_not_contain_the_next_header(self):
        for record in self.code.records:
            self.assertNotIn("Article 189 bis", record.text)
            self.assertNotIn("TABLE DES MATIERES", record.text)

    def test_parenthetical_repeal_notice_is_unattached_not_a_title(self):
        self.assertIn("(Les Articles 14 à 188 sont abrogés", self.code.unattached)
        self.assertNotIn("abrogés", str([r.titre for r in self.code.records]))

    def test_code_front_matter_is_the_printed_title(self):
        self.assertIn("CODE DE COMMERCE", self.code.front_matter)

    def test_law_region_holds_its_own_articles(self):
        self.assertEqual([r.article_number for r in self.law.records], [1])
        self.assertEqual(self.law.records[0].document_id, "loi-59-129-1959")
        self.assertIn("Au nom du Peuple", self.law.front_matter)

    def test_record_ids_are_stable(self):
        self.assertEqual(record_id_for("code-commerce-tn", 231, None), "code-commerce-tn:article-231")
        self.assertEqual(
            record_id_for("code-commerce-tn", 231, "bis"), "code-commerce-tn:article-231-bis"
        )


def _pages():
    from ingestion.pdf_text import Page

    return [Page(index=6, printed_page=7, printed_number_seen=7, body_lines=["Article 1"])]


if __name__ == "__main__":
    unittest.main()
