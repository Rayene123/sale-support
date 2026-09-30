"""Judge-runner tests: the Person 3 judge as a library, and saved-grade replay.

The judge client is faked, so no model is contacted. The assertions cover one
grade per reply, the error taxonomy, and the promise that a replayed grade is
only reused when it belongs to the same reply text.
"""
import json
import tempfile
import unittest
from pathlib import Path

from harness.errors import HarnessError
from harness.judge_runner import judge_usage, replay_judge, run_judge
from judge.client import JudgeError

SCORES = {"factual_correctness": 2, "completeness": 2, "no_hallucination": 2,
          "relevance": 1, "professional_tone": 1, "total": 8}


def item(item_id="T-001"):
    return {"id": item_id, "split": "test", "category": "refund", "difficulty": "easy",
            "customer_message": "Where is my order?",
            "order_context": {"order_number": "ORD-1", "status": "pending"}}


def system_row(item_id="T-001", text="Order ORD-1 is pending."):
    return {"item_id": item_id, "response_id": "run-1", "status": "ok", "response_text": text,
            "prompt_version": "v3"}


class FakeJudge:
    """Stands in for ``judge.Judge``; records every grade request."""

    def __init__(self, fail=(), total=8, model="qwen2.5:14b"):
        self.model = model
        self.prompt_version = "judge_v2"
        self.prompt = "judge prompt"
        self.prompt_hash = "sha-judge"
        self.fail = set(fail)
        self.total = total
        self.calls = []

    def grade(self, customer_message, order_context, response_text):
        self.calls.append((customer_message, order_context, response_text))
        if len(self.calls) in self.fail:
            raise JudgeError("api", "Provider returned HTTP 500.", {"latency_ms": 12.5,
                                                                  "usage": {"prompt_tokens": 100,
                                                                            "completion_tokens": 5}})
        return {"scores": {**SCORES, "total": self.total}, "reason": "all good",
                "prompt_version": self.prompt_version, "prompt_sha256": self.prompt_hash,
                "latency_ms": 1234.5, "response_model": self.model,
                "usage": {"prompt_tokens": 100, "completion_tokens": 5},
                "declared_total": 7, "total_corrected": True}

    def prefer(self, pair_item, answer_a, answer_b):
        self.calls.append(("prefer", answer_a, answer_b))
        return {"winner": "A", "reason": "A has every fact.", "latency_ms": 900.0,
                "usage": {"prompt_tokens": 20, "completion_tokens": 2}, "response_model": self.model}


class JudgeUsageTests(unittest.TestCase):
    def test_usage_shape_is_normalised_and_keeps_nulls(self):
        self.assertEqual(judge_usage({"prompt_tokens": 10, "completion_tokens": 4}),
                         {"prompt": 10, "completion": 4, "total": 14})
        self.assertEqual(judge_usage({"prompt": 3, "completion": 1, "total": 9}),
                         {"prompt": 3, "completion": 1, "total": 9})
        self.assertEqual(judge_usage(None), {"prompt": None, "completion": None, "total": None})
        self.assertEqual(judge_usage({}), {"prompt": None, "completion": None, "total": None})


class RunJudgeTests(unittest.TestCase):
    def test_one_grade_per_successful_reply(self):
        judge = FakeJudge()
        rows = run_judge(judge, [item("T-001"), item("T-002")],
                         [system_row("T-001"), system_row("T-002")])
        self.assertEqual(len(judge.calls), 2)
        self.assertEqual([row["status"] for row in rows], ["ok", "ok"])
        self.assertEqual(rows[0]["scores"]["total"], 8)
        self.assertEqual(rows[0]["judge_usage"], {"prompt": 100, "completion": 5, "total": 105})
        self.assertEqual(rows[0]["judge_latency_ms"], 1234.5)
        self.assertEqual(rows[0]["judge_prompt_version"], "judge_v2")
        self.assertTrue(rows[0]["judged"])
        self.assertTrue(rows[0]["judge_total_corrected"])
        self.assertEqual(rows[0]["judge_declared_total"], 7)
        self.assertEqual(rows[0]["source"], "live")

    def test_failed_system_replies_are_not_graded(self):
        judge = FakeJudge()
        broken = {**system_row("T-002"), "status": "error", "response_text": None}
        rows = run_judge(judge, [item("T-001"), item("T-002")], [system_row("T-001"), broken])
        self.assertEqual([row["item_id"] for row in rows], ["T-001"])
        self.assertEqual(len(judge.calls), 1)

    def test_judge_failure_is_categorised_and_does_not_stop_the_run(self):
        judge = FakeJudge(fail={1})
        rows = run_judge(judge, [item("T-001"), item("T-002")],
                         [system_row("T-001"), system_row("T-002")])
        self.assertEqual([row["status"] for row in rows], ["error", "ok"])
        self.assertEqual(rows[0]["error"]["category"], "api_error")
        self.assertEqual(rows[0]["error"]["type"], "api")
        self.assertEqual(rows[0]["judge_usage"], {"prompt": 100, "completion": 5, "total": 105})
        self.assertIsNone(rows[0]["scores"])
        self.assertFalse(rows[0]["judged"])

    def test_missing_dataset_item_is_a_missing_field_row(self):
        rows = run_judge(FakeJudge(), [item("T-002")], [system_row("T-001")])
        self.assertEqual(rows[0]["error"]["category"], "missing_field")
        self.assertEqual(rows[0]["error"]["type"], "DatasetError")

    def test_limit_and_skip_ids_support_resume(self):
        judge = FakeJudge()
        rows = run_judge(judge, [item("T-001"), item("T-002"), item("T-003")],
                         [system_row("T-001"), system_row("T-002"), system_row("T-003")],
                         skip_ids={"T-001"}, limit=1)
        self.assertEqual([row["item_id"] for row in rows], ["T-002"])
        self.assertEqual(len(judge.calls), 1)


class ReplayJudgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "results.jsonl"
        self.addCleanup(self.temp.cleanup)

    def write(self, rows):
        self.path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        return self.path

    def saved(self, item_id="T-001", text="Order ORD-1 is pending.", **overrides):
        return {"item_id": item_id, "status": "ok", "response_text": text,
                "result": {"scores": {**SCORES, "total": 7}, "reason": "missing one fact",
                           "prompt_version": "judge_v2", "latency_ms": 900.0,
                           "response_model": "qwen2.5:14b",
                           "usage": {"prompt_tokens": 80, "completion_tokens": 3},
                           "declared_total": 7, "total_corrected": False},
                **overrides}

    def test_replay_reuses_saved_grades_without_calling_a_model(self):
        judge = FakeJudge()
        path = self.write([self.saved()])
        rows = replay_judge(path, [system_row()])
        self.assertEqual(len(judge.calls), 0)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["source"], "replay")
        self.assertEqual(rows[0]["replayed_from"], str(path))
        self.assertEqual(rows[0]["scores"]["total"], 7)
        self.assertEqual(rows[0]["judge_latency_ms"], 900.0)
        self.assertEqual(rows[0]["judge_usage"], {"prompt": 80, "completion": 3, "total": 83})

    def test_text_mismatch_is_an_error_not_a_silent_reuse(self):
        path = self.write([self.saved(text="a different reply")])
        rows = replay_judge(path, [system_row()])
        self.assertEqual(rows[0]["status"], "error")
        self.assertEqual(rows[0]["error"]["category"], "dataset_error")
        self.assertIsNone(rows[0]["scores"])

    def test_saved_failure_and_unknown_items(self):
        path = self.write([self.saved(status="error", result=None, error_type="timeout")])
        rows = replay_judge(path, [system_row()])
        self.assertEqual(rows[0]["error"]["category"], "judge_error")
        path = self.write([self.saved(item_id="OTHER")])
        with self.assertRaises(HarnessError) as caught:
            replay_judge(path, [system_row()])
        self.assertIn("no grades for the replies", str(caught.exception))

    def test_empty_saved_file_is_a_configuration_error(self):
        self.path.write_text("", encoding="utf-8")
        with self.assertRaises(HarnessError) as caught:
            replay_judge(self.path, [system_row()])
        self.assertEqual(caught.exception.kind, "configuration")


if __name__ == "__main__":
    unittest.main()
