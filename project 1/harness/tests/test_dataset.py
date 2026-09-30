"""Dataset loader and validation tests.

They cover the failure modes the specification calls out: malformed records,
missing fields, duplicate ids, split selection, UTF-16 input, and the promise
that nothing is ever dropped silently.
"""
import json
import tempfile
import unittest
from pathlib import Path

from harness.dataset import (RecordError, dataset_statistics, detect_encoding, load_dataset,
                             load_labels, load_responses, read_jsonl, text_warnings,
                             validate_item)
from harness.errors import DatasetError
from harness.config import PROJECT

ITEM = {
    "id": "T-001",
    "split": "dev",
    "category": "order_status",
    "difficulty": "easy",
    "customer_message": "Where is my order?",
    "order_context": {
        "order_number": "ORD-1",
        "status": "pending",
        "items": [{"product_name": "Phone", "quantity": 1, "line_total": 10.0}],
        "total_amount": 10.0,
    },
    "reference_answer": "Order ORD-1 is pending.",
}


def write_jsonl(path, rows, encoding="utf-8"):
    text = "\n".join(json.dumps(row) for row in rows) + "\n"
    Path(path).write_text(text, encoding=encoding)
    return Path(path)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_valid_dataset_loads_with_statistics_and_hash(self):
        path = write_jsonl(self.directory / "dev.jsonl", [ITEM, {**ITEM, "id": "T-002", "split": "test"}])
        dataset = load_dataset(path, split="dev")
        self.assertEqual(dataset.ids, ["T-001"])
        self.assertEqual(dataset.errors, [])
        self.assertEqual(len(dataset.sha256), 64)
        statistics = dataset_statistics(dataset)
        self.assertEqual(statistics["items"], 1)
        self.assertEqual(statistics["by_split"], {"dev": 1})
        self.assertEqual(statistics["order_context_lines"], 1)
        self.assertEqual(statistics["invalid_records"], 0)

    def test_category_and_id_filters(self):
        rows = [ITEM, {**ITEM, "id": "T-002", "category": "quantities"}, {**ITEM, "id": "T-003"}]
        path = write_jsonl(self.directory / "all.jsonl", rows)
        self.assertEqual(load_dataset(path, categories=["quantities"]).ids, ["T-002"])
        self.assertEqual(load_dataset(path, ids=["T-001", "T-003"]).ids, ["T-001", "T-003"])
        self.assertEqual(load_dataset(path, limit=2).ids, ["T-001", "T-002"])

    def test_malformed_json_is_recorded_not_ignored(self):
        path = self.directory / "broken.jsonl"
        path.write_text(json.dumps(ITEM) + "\nnot json\n[1,2]\n", encoding="utf-8")
        rows, errors = read_jsonl(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(error.line in (2, 3) for error in errors))
        with self.assertRaises(DatasetError):
            load_dataset(path)
        dataset = load_dataset(path, allow_invalid=True)
        self.assertEqual(len(dataset), 1)
        self.assertEqual(len(dataset.errors), 2)

    def test_missing_and_wrong_typed_fields_are_rejected(self):
        broken = [
            {key: value for key, value in ITEM.items() if key != "customer_message"},
            {**ITEM, "id": ""},
            {**ITEM, "order_context": "not an object"},
            {**ITEM, "order_context": {"order_number": "ORD-1", "status": "pending", "items": []}},
            {**ITEM, "split": "validation"},
        ]
        path = write_jsonl(self.directory / "invalid.jsonl", [ITEM, *broken])
        with self.assertRaises(DatasetError):
            load_dataset(path)
        dataset = load_dataset(path, allow_invalid=True)
        self.assertEqual(len(dataset.errors), 5)
        self.assertEqual(dataset.ids, ["T-001"])
        messages = " ".join(str(error) for error in dataset.errors)
        self.assertIn("customer_message", messages)
        self.assertIn("id must be a nonempty string", messages)
        self.assertIn("order_context must be a nonempty object", messages)
        self.assertIn("items must be a nonempty list", messages)
        self.assertIn("split must be one of", messages)

    def test_duplicate_ids_are_rejected(self):
        path = write_jsonl(self.directory / "dupes.jsonl", [ITEM, ITEM])
        with self.assertRaisesRegex(DatasetError, "duplicate id"):
            load_dataset(path)

    def test_missing_file_and_empty_selection_raise(self):
        with self.assertRaises(DatasetError):
            load_dataset(self.directory / "absent.jsonl")
        path = write_jsonl(self.directory / "dev.jsonl", [ITEM])
        with self.assertRaises(DatasetError):
            load_dataset(path, split="test")

    def test_utf16_input_is_detected(self):
        path = self.directory / "utf16.jsonl"
        path.write_text(json.dumps({**ITEM, "customer_message": "Où est ma commande ?"}) + "\n",
                        encoding="utf-16")
        self.assertEqual(detect_encoding(path), "utf-16")
        self.assertEqual(load_dataset(path).items[0]["customer_message"], "Où est ma commande ?")

    def test_validate_item_reports_line_problems(self):
        problems = validate_item({"id": "X", "customer_message": "hi", "order_context": {}}, "f.jsonl", 4)
        self.assertTrue(all(problem.startswith("f.jsonl:4: ") for problem in problems))
        self.assertIn("order_context must be a nonempty object", problems[0])
        partial = {"status": "pending", "items": [{"product_name": "Phone", "quantity": 1}]}
        problems = validate_item({"id": "X", "customer_message": "hi", "order_context": partial})
        self.assertIn("order_context is missing 'order_number'", problems)
        self.assertIn("order_context.items[0] is missing 'line_total'", problems)

    def test_labels_are_grouped_and_validated(self):
        scores = {"factual_correctness": 2, "completeness": 2, "no_hallucination": 2,
                  "relevance": 1, "professional_tone": 1, "total": 8}
        path = write_jsonl(self.directory / "labels.jsonl", [
            {"item_id": "T-001", "response_id": "v3", "response_text": "Pending.",
             "evaluator_id": "1", "scores": scores},
            {"item_id": "T-001", "response_id": "v3", "response_text": "Pending.",
             "evaluator_id": "2", "scores": {**scores, "total": 7, "completeness": 1}},
        ])
        labels = load_labels(path)
        self.assertEqual(len(labels[("T-001", "v3")]), 2)
        bad = write_jsonl(self.directory / "bad.jsonl", [
            {"item_id": "T-001", "response_id": "v3", "response_text": "x", "evaluator_id": "1",
             "scores": {**scores, "total": 3}}])
        with self.assertRaisesRegex(DatasetError, "total does not match"):
            load_labels(bad)

    def test_duplicate_evaluator_label_is_rejected(self):
        scores = {"factual_correctness": 2, "completeness": 2, "no_hallucination": 2,
                  "relevance": 1, "professional_tone": 1, "total": 8}
        row = {"item_id": "T-001", "response_id": "v3", "response_text": "Pending.",
               "evaluator_id": "1", "scores": scores}
        path = write_jsonl(self.directory / "dupes.jsonl", [row, row])
        with self.assertRaisesRegex(DatasetError, "duplicate evaluator label"):
            load_labels(path)

    def test_responses_accept_both_saved_schemas(self):
        path = write_jsonl(self.directory / "responses.jsonl", [
            {"id": "T-001", "response": "Pending.", "model": "m", "latency_ms": 12.5,
             "prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13, "prompt_version": "v3"},
            {"item_id": "T-002", "response_text": "Shipped.", "response_id": "baseline_v1"},
        ])
        responses = load_responses(path)
        self.assertEqual(responses[0]["response_id"], "responses")
        self.assertEqual(responses[0]["system_latency_ms"], 12.5)
        self.assertEqual(responses[0]["system_prompt_version"], "v3")
        self.assertEqual(responses[0]["system_tokens"]["total"], 13)
        self.assertEqual(responses[1]["response_id"], "baseline_v1")
        self.assertIsNone(responses[1]["system_latency_ms"])

    def test_responses_reject_duplicates_and_missing_fields(self):
        path = write_jsonl(self.directory / "dupes.jsonl", [
            {"item_id": "T-001", "response_text": "a"}, {"item_id": "T-001", "response_text": "b"}])
        with self.assertRaisesRegex(DatasetError, "duplicate response"):
            load_responses(path)
        path = write_jsonl(self.directory / "bad.jsonl", [{"response_text": "a"}])
        with self.assertRaisesRegex(DatasetError, "item_id"):
            load_responses(path)

    def test_text_warnings_detect_encoding_damage(self):
        self.assertEqual(text_warnings("Clean reply."), [])
        self.assertIn("replacement_characters", text_warnings("we\ufffdll ship it"))
        # "café" mis-decoded as UTF-8 bytes read as Latin-1: "Ã©".
        self.assertIn("mojibake", text_warnings("Order shipped caf\u00c3\u00a9 today"))

    def test_record_error_is_serialisable(self):
        error = RecordError("dev.jsonl", 3, "dataset_error", "invalid JSON", "T-001")
        self.assertEqual(error.to_record()["line"], 3)
        self.assertIn("dev.jsonl:3", str(error))

    def test_repository_datasets_are_valid(self):
        for name, expected in (("golden.jsonl", 160), ("dev.jsonl", 40), ("test.jsonl", 120)):
            with self.subTest(name):
                dataset = load_dataset(PROJECT / "data" / name)
                self.assertEqual(len(dataset), expected)
                self.assertEqual(dataset.errors, [])


if __name__ == "__main__":
    unittest.main()
