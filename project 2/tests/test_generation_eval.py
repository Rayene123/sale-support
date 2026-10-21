"""Deterministic tests for generation evaluation scoring, without model calls."""
from __future__ import annotations

import importlib.util
import contextlib
from hashlib import sha256
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _paths  # noqa: F401

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generation_eval", PROJECT / "eval" / "generation.py")
generation_eval = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generation_eval)


class GenerationEvalTests(unittest.TestCase):
    def setUp(self):
        self.question = {
            "question_id": "q1", "question": "Quel délai ?", "answerability": "answerable",
            "expected_answer": "Dix jours.", "gold_evidence": [{"record_id": "law:article-1", "required": True}],
        }
        self.corpus = {"law:article-1": {"record_id": "law:article-1", "status": "published", "text": "Le délai est de dix jours."}}

    def test_lexical_answer_proxy_and_gold_citation_and_exact_quote(self):
        result = generation_eval.score_response(self.question, {
            "answer_fr": "Le délai est de dix jours.", "abstain": False,
            "citations": [{"record_id": "law:article-1", "quote": "Le délai est de dix jours."}],
            "timings_ms": {"total": 50, "retrieval": 3, "generation": 46},
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }, self.corpus)
        self.assertEqual(result["citation_precision_against_gold"], 1)
        self.assertEqual(result["citation_recall_against_gold"], 1)
        self.assertEqual(result["quote_checks_passed"], 1)
        self.assertEqual(result["answer_lexical_f1_proxy"], .5)

    def test_unanswerable_abstention_metrics_and_cost_are_denominated(self):
        rows = [
            {"question_id": "a", "answerability": "answerable", "abstain": False, "answer_lexical_f1_proxy": .5, "citation_record_ids": ["g"], "citation_precision_against_gold": 1, "citation_recall_against_gold": 1, "quote_checks_passed": 1, "quote_checks_total": 1, "timings_ms": {"total": 20, "retrieval": 2, "generation": 17}, "usage": {"prompt_tokens": 100, "completion_tokens": 20}},
            {"question_id": "u", "answerability": "unanswerable", "abstain": True, "answer_lexical_f1_proxy": None, "citation_record_ids": [], "citation_precision_against_gold": None, "citation_recall_against_gold": None, "quote_checks_passed": 0, "quote_checks_total": 0, "timings_ms": {"total": 30, "retrieval": 3, "generation": 26}, "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
        ]
        summary = generation_eval.summarize(rows, 2, 1, 1.0, 2.0)
        self.assertEqual(summary["question_counts"]["excluded_duplicates"], 1)
        self.assertEqual(summary["abstention"]["abstention_recall"], 1)
        self.assertEqual(summary["token_usage"]["prompt_tokens"], 200)
        self.assertEqual(summary["estimated_cost"]["amount"], .00026)
        self.assertIsNone(summary["faithfulness"]["score"])

    def test_loader_uses_approved_rows_and_excludes_duplicate(self):
        rows = [dict(self.question, review={"status": "approved"}),
                dict(self.question, question_id="old", review={"status": "excluded_duplicate"})]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "q.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            approved, counts = generation_eval.load_canonical_questions(path)
        self.assertEqual([row["question_id"] for row in approved], ["q1"])
        self.assertEqual(counts["excluded_duplicate"], 1)

    def test_blank_or_malformed_quotes_never_count_as_exact_matches(self):
        for citation in [{"record_id": "law:article-1", "quote": quote} for quote in ["", " \n\t ", None]] + [{"record_id": [], "quote": "Dix jours."}, None]:
            with self.subTest(citation=citation):
                result = generation_eval.score_response(self.question, {
                    "answer_fr": "Dix jours.", "abstain": False, "citations": [citation],
                }, self.corpus)
                self.assertEqual(result["quote_checks_passed"], 0)
                self.assertEqual(result["quote_checks_total"], 1)

    def test_malformed_references_are_rejected_before_any_api_call(self):
        valid = dict(self.question, review={"status": "approved"})
        malformed = [
            dict(valid, expected_answer=None), dict(valid, expected_answer=" "),
            dict(valid, gold_evidence=[]), dict(valid, gold_evidence={}),
            dict(valid, gold_evidence=[{"record_id": " ", "required": True}]),
            dict(valid, gold_evidence=[{"record_id": "law:article-1", "required": "true"}]),
            dict(valid, gold_evidence=[{"record_id": "law:article-1", "required": False}]),
            dict(valid, question=" "), dict(valid, question_id=" "),
            dict(valid, review="approved"), dict(valid, answerability="unanswerable"),
            dict(valid, answerability=[]), dict(valid, answerability={}),
            {k: v for k, v in valid.items() if k != "expected_answer"},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "questions.jsonl"
            for row in malformed:
                with self.subTest(row=row):
                    path.write_text(json.dumps(row), encoding="utf-8")
                    with patch.object(generation_eval.urllib.request, "urlopen") as http, contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:
                            generation_eval.main(["--questions", str(path), "--output", str(Path(temp) / "out.json")])
                    self.assertEqual(error.exception.code, 2)
                    http.assert_not_called()

    def test_report_preserves_responses_and_input_fingerprints(self):
        row = dict(self.question, review={"status": "approved"})
        response = {"answer_fr": "Dix jours.", "abstain": False, "model": "qwen3.5:9b",
                    "citations": [{"record_id": "law:article-1", "quote": "Le délai est de dix jours."}]}

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(response).encode()

        with tempfile.TemporaryDirectory() as temp:
            questions, corpus, output = [Path(temp) / name for name in ["questions.jsonl", "corpus.jsonl", "report.json"]]
            questions.write_text(json.dumps(row), encoding="utf-8")
            corpus.write_text(json.dumps(self.corpus["law:article-1"]), encoding="utf-8")
            with patch.object(generation_eval.urllib.request, "urlopen", return_value=FakeResponse()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(generation_eval.main(["--questions", str(questions), "--corpus", str(corpus), "--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["per_question"][0]["response"], response)
            self.assertEqual(report["provenance"]["observed_models"], ["qwen3.5:9b"])
            self.assertEqual(report["provenance"]["questions_sha256"], sha256(questions.read_bytes()).hexdigest())
            self.assertEqual(report["provenance"]["corpus_sha256"], sha256(corpus.read_bytes()).hexdigest())
            self.assertIn("src/generation/service.py", report["provenance"]["source_sha256"])

    def test_invalid_api_response_is_retained_for_diagnosis(self):
        response = {"answer_fr": " ", "abstain": False, "citations": []}

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(response).encode()

        with patch.object(generation_eval.urllib.request, "urlopen", return_value=FakeResponse()):
            rows = generation_eval.run("http://localhost:8002", [self.question], self.corpus, 10)
        self.assertEqual(rows[0]["error"], "ValueError")
        self.assertEqual(rows[0]["response"], response)

    def test_http_failure_records_status_and_does_not_abort_remaining_questions(self):
        error = generation_eval.urllib.error.HTTPError("http://localhost:8002/ask", 503, "Unavailable", {}, None)
        with patch.object(generation_eval.urllib.request, "urlopen", side_effect=error):
            rows = generation_eval.run("http://localhost:8002", [self.question, self.question], self.corpus, 10)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["http_status"] == 503 for row in rows))

    def test_api_runner_posts_question_and_scores_json_response(self):
        response = {"answer_fr": "Dix jours.", "abstain": False, "citations": [{"record_id": "law:article-1", "quote": "Le délai est de dix jours."}], "timings_ms": {}, "usage": {}}

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(response).encode()

        with patch.object(generation_eval.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
            rows = generation_eval.run("http://localhost:8002", [self.question], self.corpus, 10)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:8002/ask")
        self.assertEqual(json.loads(request.data), {"question": "Quel délai ?"})
        self.assertEqual(rows[0]["question_id"], "q1")
        self.assertNotIn("error", rows[0])
        self.assertEqual(rows[0]["response"], response)


if __name__ == "__main__":
    unittest.main()
