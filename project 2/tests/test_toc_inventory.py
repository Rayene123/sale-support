"""Tests for the table-of-contents reconciliation aid."""
from __future__ import annotations

import unittest

import _fixtures
import _paths  # noqa: F401

from ingestion.build import extract_toc_inventory


class ExtractTocInventoryTests(unittest.TestCase):
    def setUp(self):
        self.stream = _fixtures.sample_stream()
        self.toc_lines = self.stream[_fixtures.TOC_START:]
        self.inventory = extract_toc_inventory(self.toc_lines)

    def test_ranges_are_read(self):
        self.assertEqual(
            self.inventory["ranges"],
            [
                {"start": 1, "end": 746},
                {"start": 14, "end": 188},
                {"start": 413, "end": 444},
            ],
        )

    def test_repealed_ranges_are_recognised(self):
        self.assertEqual(
            self.inventory["abrogated_ranges"],
            [{"start": 14, "end": 188}, {"start": 413, "end": 444}],
        )

    def test_numbers_are_expanded(self):
        self.assertIn(188, self.inventory["numbers_abrogated"])
        self.assertNotIn(189, self.inventory["numbers_abrogated"])
        self.assertEqual(len(self.inventory["numbers_covered"]), 746)

    def test_a_range_that_does_not_mention_repeal_is_not_repealed(self):
        self.assertNotIn(400, self.inventory["numbers_abrogated"])


if __name__ == "__main__":
    unittest.main()
