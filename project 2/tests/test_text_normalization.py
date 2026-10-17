"""Tests for PDF page cleaning and text normalisation."""
from __future__ import annotations

import unittest

import _fixtures  # noqa: F401  (adds project 2/src to sys.path)

from ingestion.pdf_text import (
    clean_page_lines,
    collapse,
    dehyphenate,
    normalize_body,
    reflow,
    split_footnotes,
)


class CollapseTests(unittest.TestCase):
    def test_normalises_non_breaking_space_and_runs(self):
        self.assertEqual(collapse("a\u00a0\u00a0b   c\t d "), "a b c d")

    def test_keeps_accented_text(self):
        self.assertEqual(collapse("  société  anonyme "), "société anonyme")


class DehyphenateTests(unittest.TestCase):
    def test_joins_word_split_across_lines(self):
        self.assertEqual(dehyphenate("com-\nmerce"), "commerce")

    def test_joins_repeated_wraps(self):
        self.assertEqual(dehyphenate("a-\nb-\nc"), "abc")

    def test_leaves_digits_alone(self):
        self.assertEqual(dehyphenate("1-\n2"), "1-\n2")

    def test_keeps_real_hyphen_inside_a_line(self):
        # "sous-section" is a real compound, not a wrap: dehyphenate must leave
        # it intact. Joining the following line onto it is reflow's job, so the
        # full normalisation is what produces one line.
        self.assertEqual(dehyphenate("sous-section\nsuivante"), "sous-section\nsuivante")
        self.assertEqual(normalize_body("sous-section\nsuivante"), "sous-section suivante")

    def test_joins_across_a_page_break(self):
        # Article bodies are assembled across pages, so the join must not care.
        self.assertEqual(dehyphenate("com-\nmerce\n—"), "commerce\n—")


class ReflowTests(unittest.TestCase):
    def test_joins_wrapped_lines_into_one_paragraph(self):
        text = "Toute personne physique ou morale ayant la qualité de\ncommerçant est assujettie."
        self.assertEqual(
            reflow(text),
            "Toute personne physique ou morale ayant la qualité de commerçant est assujettie.",
        )

    def test_keeps_enumerated_items_on_their_own_lines(self):
        text = "Le porteur peut :\n1) remplir le blanc ;\n2) endosser de nouveau."
        self.assertEqual(
            reflow(text),
            "Le porteur peut :\n1) remplir le blanc ;\n2) endosser de nouveau.",
        )

    def test_keeps_bullets_on_their_own_lines(self):
        text = "Notamment :\n- à l'achat ;\n- à la vente."
        self.assertEqual(reflow(text), "Notamment :\n- à l'achat ;\n- à la vente.")

    def test_keeps_blank_lines_as_paragraph_separators(self):
        self.assertEqual(reflow("un\n\ndeux"), "un\n\ndeux")


class NormalizeBodyTests(unittest.TestCase):
    def test_end_to_end(self):
        text = "socié-\nté anonyme dont le\ncapital est fixé."
        self.assertEqual(normalize_body(text), "société anonyme dont le capital est fixé.")


class CleanPageLinesTests(unittest.TestCase):
    def test_removes_header_page_number_and_footnote(self):
        body, printed, footnotes = clean_page_lines(_fixtures.page_sample())
        self.assertEqual(printed, 51)
        self.assertNotIn("Imprimerie Officielle", "\n".join(body))
        self.assertNotIn("51", body)
        self.assertNotIn("Rectificatif", "\n".join(body))
        self.assertEqual(len(footnotes), 1)
        self.assertEqual(footnotes[0].label, "(1)")
        self.assertIn("JORT n° 3", footnotes[0].text)

    def test_keeps_a_body_number_that_is_not_the_page_number(self):
        raw = "Imprimerie Officielle de la République Tuinsienne\n7\nArticle 2\n1) premier alinéa"
        body, printed, _ = clean_page_lines(raw)
        self.assertEqual(printed, 7)
        self.assertIn("1) premier alinéa", body)

    def test_page_without_a_number(self):
        raw = "Imprimerie Officielle de la République Tuinsienne\n"
        body, printed, footnotes = clean_page_lines(raw)
        self.assertIsNone(printed)
        self.assertEqual([line for line in body if line.strip()], [])
        self.assertEqual(footnotes, [])


class SplitFootnoteTests(unittest.TestCase):
    def test_joins_a_footnote_that_wraps(self):
        lines = [
            "Article 1",
            "Texte.",
            "__________",
            "(1) Voir l'article 4 de la loi n° 2007-37",
            "du 4 juin 2007.",
        ]
        body, footnotes = split_footnotes(lines)
        self.assertEqual(body, ["Article 1", "Texte."])
        self.assertEqual(len(footnotes), 1)
        self.assertEqual(footnotes[0].text, "Voir l'article 4 de la loi n° 2007-37 du 4 juin 2007.")

    def test_page_without_footnotes_is_untouched(self):
        lines = ["Article 1", "Texte."]
        body, footnotes = split_footnotes(lines)
        self.assertEqual(body, lines)
        self.assertEqual(footnotes, [])


if __name__ == "__main__":
    unittest.main()
