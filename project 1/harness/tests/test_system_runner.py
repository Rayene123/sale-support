"""System-runner tests: one call per item, resume, replay, and row schema.

The client is a fake, so no provider is contacted. The assertions cover the
project constraints (one model call per item, no agents, structured rows) and
the honesty rules around replayed data.
"""
import unittest

from harness.errors import SystemError
from harness.system_runner import replay_system, run_system


def item(item_id="T-001", split="test", category="refund", difficulty="medium"):
    return {"id": item_id, "split": split, "category": category, "difficulty": difficulty,
            "customer_message": "Where is my order?",
            "order_context": {"order_number": "ORD-1", "status": "pending"}}


class FakeClient:
    """Records every call so the test can prove the one-call-per-item rule."""

    def __init__(self, replies=None, fail=()):
        self.config = type("Config", (), {"model": "qwen2.5:14b"})()
        self.replies = replies or {}
        self.fail = set(fail)
        self.calls = []

    def generate(self, message):
        self.calls.append(message)
        if len(self.calls) in self.fail:
            raise SystemError("timeout", "Request timed out", {"latency_ms": 500.0})
        text = self.replies.get(len(self.calls), f"Order ORD-1 is {len(self.calls)}.")
        return {"text": text, "latency_ms": 1000.0 * len(self.calls), "usage": {"prompt": 10, "completion": 5, "total": 15},
                "response_model": "qwen2.5:14b", "decode_tokens_per_second": 20.0}


class RunSystemTests(unittest.TestCase):
    def test_one_call_per_item_and_row_schema(self):
        client = FakeClient(replies={1: "Order ORD-1 is pending."})
        items = [item("T-001"), item("T-002"), item("T-003")]
        rows = run_system(client, items, "v3", "sha-v3", response_id="run-1")
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["requests"] for row in rows], [1, 1, 1])
        for row in rows:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["prompt_version"], "v3")
            self.assertEqual(row["system_prompt_sha256"], "sha-v3")
            self.assertEqual(row["response_id"], "run-1")
            self.assertIsNone(row["error"])
            self.assertEqual(set(row["tokens"]), {"prompt", "completion", "total"})
            self.assertEqual(row["tokens"]["total"], 15)
        self.assertEqual([row["item_id"] for row in rows], ["T-001", "T-002", "T-003"])
        self.assertIn("Customer message:", client.calls[0])

    def test_one_failure_does_not_stop_the_run_and_is_categorised(self):
        client = FakeClient(fail={2})
        rows = run_system(client, [item("T-001"), item("T-002"), item("T-003")], "v3", "sha")
        self.assertEqual([row["status"] for row in rows], ["ok", "error", "ok"])
        failure = rows[1]
        self.assertEqual(failure["error"]["category"], "timeout")
        self.assertEqual(failure["error"]["type"], "SystemError")
        self.assertIsNone(failure["response_text"])
        self.assertEqual(failure["latency_ms"], 500.0)
        self.assertEqual(rows[2]["status"], "ok")

    def test_limit_and_skip_ids_support_partial_resume(self):
        client = FakeClient()
        rows = run_system(client, [item("T-001"), item("T-002"), item("T-003")], "v3", "sha", limit=2)
        self.assertEqual([row["item_id"] for row in rows], ["T-001", "T-002"])
        resumed = FakeClient()
        rows = run_system(resumed, [item("T-001"), item("T-002"), item("T-003")], "v3", "sha",
                          skip_ids={"T-001", "T-002"})
        self.assertEqual([row["item_id"] for row in rows], ["T-003"])
        self.assertEqual(len(resumed.calls), 1)

    def test_sink_receives_every_row_in_order(self):
        client = FakeClient(fail={1})
        saved = []
        run_system(client, [item("T-001"), item("T-002")], "v3", "sha", sink=saved.append)
        self.assertEqual([row["item_id"] for row in saved], ["T-001", "T-002"])

    def test_mojibake_in_a_reply_becomes_a_warning_not_a_failure(self):
        client = FakeClient(replies={1: "Order ORD-1 is pending \ufffd\ufffd"})
        rows = run_system(client, [item("T-001")], "v3", "sha")
        self.assertEqual(rows[0]["status"], "ok")
        self.assertTrue(rows[0]["warnings"])


class ReplaySystemTests(unittest.TestCase):
    def test_replay_keeps_saved_latency_and_usage_and_makes_no_call(self):
        client = FakeClient()
        saved = [{"item_id": "T-001", "response_id": "baseline_v1", "response_text": "Shipped yesterday.",
                  "system_model": "qwen2.5:14b", "system_latency_ms": 3908.4,
                  "system_tokens": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
                  "system_prompt_version": "v1"}]
        rows = replay_system(saved, [item("T-001")], "v1", "sha-v1")
        self.assertEqual(len(client.calls), 0)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["source"], "replay")
        self.assertEqual(rows[0]["requests"], 0)
        self.assertEqual(rows[0]["latency_ms"], 3908.4)
        self.assertEqual(rows[0]["tokens"]["prompt_tokens"], 120)
        self.assertEqual(rows[0]["response_id"], "baseline_v1")
        self.assertNotIn("prompt_version_mismatch", rows[0]["warnings"])

    def test_prompt_version_mismatch_is_flagged(self):
        saved = [{"item_id": "T-001", "response_text": "x", "system_prompt_version": "v1"}]
        rows = replay_system(saved, [item("T-001")], "v2", "sha-v2")
        self.assertIn("prompt_version_mismatch", rows[0]["warnings"])
        self.assertEqual(rows[0]["replayed_prompt_version"], "v1")

    def test_empty_or_unknown_saved_responses_are_errors(self):
        saved = [{"item_id": "T-001", "response_text": "   "}]
        rows = replay_system(saved, [item("T-001")], "v1", "sha")
        self.assertEqual(rows[0]["status"], "error")
        self.assertEqual(rows[0]["error"]["category"], "system_error")
        with self.assertRaises(SystemError) as caught:
            replay_system([{"item_id": "NOPE", "response_text": "x"}], [item("T-001")], "v1", "sha")
        self.assertEqual(caught.exception.kind, "dataset_error")

    def test_replay_without_recorded_latency_reports_null_not_zero(self):
        saved = [{"item_id": "T-001", "response_text": "ok"}]
        rows = replay_system(saved, [item("T-001")], "v1", "sha")
        self.assertIsNone(rows[0]["latency_ms"])
        self.assertEqual(rows[0]["tokens"], {"prompt": None, "completion": None, "total": None})


if __name__ == "__main__":
    unittest.main()
