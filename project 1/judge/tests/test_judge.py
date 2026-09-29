import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from judge.client import Judge, JudgeError, validate_scores
from judge.run import PROJECT, agreement, canonical_winner, load_inputs, main, summarize

SCORES = dict(factual_correctness=2, completeness=2, no_hallucination=2,
              relevance=1, professional_tone=1, total=8)
CONFIG = {"JUDGE_PROVIDER": "groq", "JUDGE_API_KEY": "test-key", "JUDGE_MODEL": "test-model"}


def http_response(value=None, finish="stop"):
    value = {**SCORES, "reason": "Matches supplied order status."} if value is None else value
    return io.BytesIO(json.dumps({"model": "test-model", "choices": [{
        "finish_reason": finish, "message": {"content": json.dumps(value)}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 20}}).encode())


class JudgeTests(unittest.TestCase):
    def test_empty_key_is_fine_for_local_but_required_for_groq(self):
        with patch("urllib.request.urlopen") as request:
            self.assertEqual(Judge({"JUDGE_PROVIDER": "ollama", "JUDGE_API_KEY": ""}).model, "qwen3:14b")
            with self.assertRaisesRegex(JudgeError, "JUDGE_API_KEY"):
                Judge({"JUDGE_PROVIDER": "groq", "JUDGE_API_KEY": ""})
            request.assert_not_called()

    def test_request_and_response_contract(self):
        with patch("urllib.request.urlopen", return_value=http_response()) as request:
            result = Judge(CONFIG).grade("Where is my order?", {"status": "pending"}, "It is pending.")
        sent = request.call_args.args[0]
        body = json.loads(sent.data)
        inputs = json.loads(body["messages"][1]["content"])
        self.assertEqual(set(inputs), {"customer_message", "order_context", "response_text"})
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(result["scores"], SCORES)
        self.assertEqual(result["usage"]["prompt_tokens"], 30)
        self.assertNotIn("test-key", json.dumps(result))

    def test_ollama_local_request_without_key(self):
        config = {"JUDGE_PROVIDER": "ollama", "JUDGE_API_KEY": "", "JUDGE_MODEL": "qwen3:14b"}
        response = io.BytesIO(json.dumps({"model": "qwen3:14b", "done": True,
            "message": {"content": json.dumps({**SCORES, "reason": "Order is pending."})},
            "prompt_eval_count": 12, "eval_count": 20}).encode())
        with patch("urllib.request.urlopen", return_value=response) as request:
            result = Judge(config).grade("Where is my order?", {"status": "pending"}, "Pending")
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, "http://localhost:11434/api/chat")
        self.assertNotIn("Authorization", sent.headers)
        self.assertEqual(json.loads(sent.data)["model"], "qwen3:14b")
        self.assertFalse(json.loads(sent.data)["think"])
        self.assertEqual(result["scores"], SCORES)
        self.assertEqual(result["usage"]["completion_tokens"], 20)

    def test_invalid_scores(self):
        for changed in ({"total": 7}, {"relevance": True}, {"completeness": 3}, {"reason": ""}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_scores({**SCORES, "reason": "Reason", **changed})

    def test_invalid_and_truncated_outputs(self):
        for value, finish, kind in (({"total": 8}, "stop", "invalid_output"),
                                     (None, "length", "incomplete")):
            with patch("urllib.request.urlopen", return_value=http_response(value, finish)):
                with self.assertRaises(JudgeError) as caught:
                    Judge(CONFIG).grade("Question", {}, "Reply")
                self.assertEqual(caught.exception.kind, kind)

    def test_http_error_redacted_and_timeout(self):
        errors = [(urllib.error.HTTPError("https://example.com", 401, "test-key", {}, None), "api"),
                  (TimeoutError("test-key"), "timeout")]
        for error, kind in errors:
            with patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(JudgeError) as caught:
                    Judge(CONFIG).grade("Question", {}, "Reply")
                self.assertEqual(caught.exception.kind, kind)
                self.assertNotIn("test-key", str(caught.exception))

    def test_missing_local_model_explains_free_install(self):
        error = urllib.error.HTTPError("http://localhost:11434/api/chat", 404, "missing", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(JudgeError) as caught:
                Judge({"JUDGE_PROVIDER": "ollama", "JUDGE_MODEL": "qwen3:14b"}).grade("Question", {}, "Reply")
        self.assertEqual(caught.exception.kind, "model_missing")
        self.assertIn("ollama pull qwen3:14b", str(caught.exception))

    def test_pairwise_identity_not_slot(self):
        self.assertEqual(canonical_winner("A"), canonical_winner("B", True))
        self.assertNotEqual(canonical_winner("A"), canonical_winner("A", True))
        self.assertEqual(canonical_winner("tie", True), "tie")

    def test_agreement_and_failure_denominators(self):
        lower = {**SCORES, "completeness": 0, "total": 6}
        labels = {("x", "r"): [{"evaluator_id": "1", "scores": lower},
                                 {"evaluator_id": "2", "scores": SCORES}]}
        records = [{"item_id": "x", "response_id": "r", "status": "ok",
                    "result": {"scores": SCORES, "reason": "example"}},
                   {"item_id": "y", "response_id": "r", "status": "error"}]
        report = summarize(records, labels)
        self.assertEqual(report["failed_responses"], 1)
        self.assertEqual(report["judge_agreement_by_evaluator"]["1"]["total"]["agreement_percent"], 0)
        self.assertEqual(report["major_disagreement_percent"], 50)
        self.assertEqual(report["label_status"], "seeded_unverified")
        self.assertIsNone(agreement([])["total"]["agreement_percent"])

    def test_repository_dataset_alignment(self):
        items, labels, responses = load_inputs(PROJECT / "data/dev.jsonl", PROJECT / "data/human_labels.jsonl")
        self.assertEqual(len(items), 40)
        self.assertEqual(len(responses), 40)
        self.assertEqual(len(labels), 160)

    def test_person4_utf16_runs_load_directly(self):
        items, labels, responses = load_inputs(PROJECT / "data/dev.jsonl", PROJECT / "data/human_labels.jsonl",
                                                PROJECT / "results/baseline_v1.jsonl")
        self.assertEqual(len(responses), 40)
        self.assertEqual(responses[0]["item_id"], "P1-001")
        self.assertEqual(responses[0]["response_id"], "baseline_v1")
        self.assertTrue(responses[0]["response_text"])
        self.assertIn(responses[0]["item_id"], items)
        self.assertEqual(labels.get(("P1-001", "baseline_v1")), None)

    def test_mismatched_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "responses.jsonl"
            path.write_text(json.dumps({"item_id": "P1-001", "response_id": "reference_answer",
                                         "response_text": "Different reply"}) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different text"):
                load_inputs(PROJECT / "data/dev.jsonl", PROJECT / "data/human_labels.jsonl", path)

    def test_full_runner_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            pairs = Path(temp) / "pairs.jsonl"
            pairs.write_text(json.dumps({"item_id": "P1-001", "answer_a": "Pending", "answer_b": "Delivered"}) + "\n", encoding="utf-8")
            argv = ["--limit", "1", "--verbosity-limit", "1", "--pairs", str(pairs), "--output", str(output)]
            responses = [http_response(), http_response(), http_response({"winner": "A", "reason": "Correct"}),
                         http_response({"winner": "B", "reason": "Correct"})]
            with patch("judge.client.settings", return_value=CONFIG), patch("urllib.request.urlopen", side_effect=responses) as request:
                self.assertEqual(main(argv), 0)
                self.assertEqual(request.call_count, 4)
            report = json.loads((output / "reliability.json").read_text())
            self.assertEqual(report["position_bias"]["changed_percent"], 0)
            self.assertEqual(report["verbosity_bias"]["average_score_change"], 0)
            self.assertNotIn("test-key", (output / "metadata.json").read_text())
            with patch("judge.client.settings", return_value=CONFIG), patch("urllib.request.urlopen") as request:
                with self.assertRaises(SystemExit):
                    main(argv)
                request.assert_not_called()

    def test_runner_preserves_failure_and_continues(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            with patch("judge.client.settings", return_value=CONFIG), patch("urllib.request.urlopen", side_effect=[http_response({"total": 8}), http_response()]):
                self.assertEqual(main(["--limit", "2", "--output", str(output)]), 1)
            rows = [json.loads(line) for line in (output / "results.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["error_type"], "invalid_output")
            self.assertIn("raw_response", rows[0])
            self.assertEqual(rows[1]["status"], "ok")
            report = json.loads((output / "reliability.json").read_text())
            self.assertEqual(report["failed_responses"], 1)
            self.assertIsNone(report["position_bias"]["changed_percent"])


if __name__ == "__main__":
    unittest.main()
