"""End-to-end command tests: artefacts, overwrite safety, resume, and secrets.

Both providers are mocked, so a full run executes in milliseconds without a
model. The tests drive the real command-line entry point, which is the contract
the team uses at demo time.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from harness.cli import main
from harness.config import PROJECT

SCORES = {"factual_correctness": 2, "completeness": 2, "no_hallucination": 2,
          "relevance": 1, "professional_tone": 1, "total": 8}

ITEM = {
    "id": "T-001",
    "split": "dev",
    "category": "order_status",
    "difficulty": "easy",
    "customer_message": "Where is my order?",
    "order_context": {"order_number": "ORD-1", "status": "pending",
                      "items": [{"product_name": "Phone", "quantity": 1, "line_total": 10.0}],
                      "total_amount": 10.0},
    "reference_answer": "Order ORD-1 is pending.",
}
SECRET = "sk-not-a-real-key"


def write_jsonl(path, rows):
    Path(path).write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return Path(path)


def chat_reply(url, content, prompt_tokens, completion_tokens, eval_duration=1_500_000_000):
    """A provider reply in whichever wire format the endpoint expects."""
    if "/chat/completions" in url:
        return io.BytesIO(json.dumps({
            "model": "openai/gpt-oss-20b",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens}}).encode())
    return io.BytesIO(json.dumps({
        "model": "qwen2.5:14b", "done": True, "message": {"content": content},
        "prompt_eval_count": prompt_tokens, "eval_count": completion_tokens,
        "eval_duration": eval_duration}).encode())


def reply_for_url(request, **_kwargs):
    """Answer every call the harness makes, without a model.

    The system and the judge both talk to the same local server, so the
    request body decides who is being answered: the judge asks for JSON output
    (``format``/``response_format``) and sends ``answer_A`` in pairwise mode.
    """
    url = request if isinstance(request, str) else request.full_url
    if url.endswith("/api/tags") or url.endswith("/models"):
        listed = json.dumps({"models": [{"name": "qwen2.5:14b"}], "data": [{"id": "qwen2.5:14b"}]})
        return io.BytesIO(listed.encode())
    sent = json.loads(request.data) if not isinstance(request, str) else {}
    if "format" not in sent and "response_format" not in sent:
        return chat_reply(url, "Order ORD-1 is pending and ships tomorrow.", 120, 30, 3_000_000_000)
    user = json.loads(sent["messages"][-1]["content"])
    if "answer_A" in user:
        return chat_reply(url, json.dumps({"winner": "A", "reason": "more complete"}), 1300, 20)
    scores = json.dumps({**SCORES, "total": 8, "reason": "accurate and complete"})
    return chat_reply(url, scores, 1300, 60)


class CliEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.dataset = write_jsonl(self.root / "dev.jsonl", [ITEM])
        self.output = self.root / "run"
        self.env = {"PATH": "/usr/bin"}
        # Two seeded human labels for the reply this run will produce
        # (response_id defaults to the run id).
        self.labels = write_jsonl(self.root / "labels.jsonl", [
            {"item_id": "T-001", "response_id": "test-run", "response_text": "x",
             "evaluator_id": "1", "scores": dict(SCORES), "explanation": "good"},
            {"item_id": "T-001", "response_id": "test-run", "response_text": "x",
             "evaluator_id": "2", "scores": {**SCORES, "completeness": 1, "total": 7},
             "explanation": "one detail missing"}])

    def run_cli(self, argv, urlopen=None, environment=None):
        """Run the CLI with a clean environment and capture its output."""
        out, err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", dict(environment or self.env), clear=True), \
                patch("urllib.request.urlopen", side_effect=urlopen) as request, \
                redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, request, out.getvalue() + err.getvalue()

    def base(self, *extra):
        return ["run", "--dataset", str(self.dataset), "--output", str(self.output),
                "--run-id", "test-run", "--system-model", "qwen2.5:14b",
                "--judge-model", "qwen2.5:14b", "--labels", str(self.labels), *extra]

    # ------------------------------------------------------------------ run
    def test_full_live_run_writes_every_artifact(self):
        code, request, _ = self.run_cli(self.base(), reply_for_url)
        self.assertEqual(code, 0)
        for name in ("metadata.json", "system.jsonl", "judge.jsonl", "items.jsonl",
                     "errors.jsonl", "metrics.json", "cost.json", "report.md"):
            self.assertTrue((self.output / name).exists(), name)
        self.assertTrue(any(self.output.glob("prompts/system_v*.txt")))
        system_rows = [json.loads(line) for line in (self.output / "system.jsonl").read_text().splitlines()]
        judge_rows = [json.loads(line) for line in (self.output / "judge.jsonl").read_text().splitlines()]
        self.assertEqual(len(system_rows), 1)
        self.assertEqual(len(judge_rows), 1)
        self.assertEqual(system_rows[0]["requests"], 1)
        self.assertEqual(judge_rows[0]["scores"]["total"], 8)
        items = [json.loads(line) for line in (self.output / "items.jsonl").read_text().splitlines()]
        self.assertEqual(items[0]["status"], "ok")
        self.assertEqual((self.output / "errors.jsonl").read_text(), "")
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["system"]["quality"]["average_total_out_of_8"], 8.0)
        self.assertEqual(metrics["performance"]["judge_tokens"]["prompt"], 1300)
        metadata = json.loads((self.output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "complete")
        self.assertEqual(metadata["mode"], "live")
        self.assertIn("python -m harness run", metadata["reproduction"]["command"])
        # Two tag probes (system, judge), one system call, one judge call.
        self.assertEqual(request.call_count, 4)

    def test_report_rebuilds_artifacts_without_calling_a_model(self):
        self.run_cli(self.base(), reply_for_url)
        cost_before = (self.output / "cost.json").read_text(encoding="utf-8")
        code, request, _ = self.run_cli(["report", "--run", str(self.output)])
        self.assertEqual(code, 0)
        request.assert_not_called()
        self.assertEqual((self.output / "cost.json").read_text(encoding="utf-8"), cost_before)
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["run"]["notes"][0],
                         "Metrics rebuilt from the saved rows of this run; no model was called.")
        # The labels file recorded in the metadata is picked up again, so the
        # rebuilt report carries the same agreement statistics.
        self.assertIsNotNone(metrics["reliability"]["human_agreement"])
        self.assertEqual(metrics["reliability"]["human_agreement"]["total"]["comparisons"], 1)
        self.assertIn("# Evaluation run", (self.output / "report.md").read_text(encoding="utf-8"))

    def test_report_says_so_when_the_recorded_labels_are_unreadable(self):
        self.run_cli(self.base(), reply_for_url)
        self.labels.unlink()  # the run's labels file is gone, e.g. another clone
        code, _, _ = self.run_cli(["report", "--run", str(self.output)])
        self.assertEqual(code, 0)
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertIsNone(metrics["reliability"]["human_agreement"])
        self.assertIn("could not be read", " ".join(metrics["run"]["notes"]))

    def test_existing_output_is_never_overwritten_and_resume_continues(self):
        self.run_cli(self.base(), reply_for_url)
        before = (self.output / "system.jsonl").read_text(encoding="utf-8")
        code, request, output = self.run_cli(self.base())
        self.assertEqual(code, 2)  # EXIT_USAGE: refused rather than clobbered
        self.assertIn("already exists", output)
        self.assertEqual((self.output / "system.jsonl").read_text(encoding="utf-8"), before)
        code, request, _ = self.run_cli(self.base("--resume"), reply_for_url)
        self.assertEqual(code, 0)
        # Only the two provider probes: no model call was repeated.
        called = [call.args[0] for call in request.call_args_list]
        self.assertEqual(len(called), 2)
        self.assertTrue(all(str(url).endswith("/api/tags") for url in called), called)
        metadata = json.loads((self.output / "metadata.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["resumed"])
        rows = (self.output / "system.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1)  # resume did not duplicate the row

    def test_resume_after_an_interruption_grades_the_remaining_items(self):
        second = {**ITEM, "id": "T-002"}
        write_jsonl(self.dataset, [ITEM, second])
        self.run_cli(self.base("--skip-judge"), reply_for_url)
        code, _, _ = self.run_cli(self.base("--resume"), reply_for_url)
        self.assertEqual(code, 0)
        judge_rows = (self.output / "judge.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(judge_rows), 2)
        system_rows = (self.output / "system.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(system_rows), 2)

    # -------------------------------------------------------------- secrets
    def test_metadata_and_artifacts_never_contain_a_key(self):
        hosted = self.base("--system-provider", "openai", "--system-api-key-env", "SECRET_KEY",
                           "--system-base-url", "https://api.groq.com/openai/v1",
                           "--judge-provider", "groq", "--judge-model", "openai/gpt-oss-20b")
        code, request, output = self.run_cli(
            hosted, reply_for_url, environment={"PATH": "/usr/bin", "JUDGE_API_KEY": SECRET})
        self.assertEqual(code, 2)  # no key in the environment: a configuration stop
        self.assertIn("SECRET_KEY is not set", output)
        request.assert_not_called()
        self.assertFalse(self.output.exists())  # a refused run leaves nothing behind
        code, _, _ = self.run_cli(hosted, reply_for_url,
                                  environment={"PATH": "/usr/bin", "SECRET_KEY": SECRET,
                                               "JUDGE_API_KEY": SECRET})
        self.assertEqual(code, 0)
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(encoding="utf-8", errors="ignore"),
                                 f"{path.name} leaked the key")
        metadata = json.loads((self.output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["configuration"]["system"]["api_key_env"], "SECRET_KEY")
        self.assertTrue(metadata["configuration"]["judge"]["api_key_configured"])

    # ------------------------------------------------------------- replay
    def test_replay_run_makes_no_call_and_labels_prompt_mismatch(self):
        responses = write_jsonl(self.root / "baseline.jsonl", [{
            "item_id": "T-001", "response_id": "baseline_v1",
            "response_text": "Order ORD-1 is pending.", "system_model": "qwen2.5:14b",
            "system_latency_ms": 3908.4,
            "system_tokens": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            "system_prompt_version": "v1"}])
        code, request, _ = self.run_cli(self.base("--system-source", str(responses),
                                                 "--system-prompt", "v2", "--skip-judge"))
        self.assertEqual(code, 0)
        request.assert_not_called()
        row = json.loads((self.output / "system.jsonl").read_text().splitlines()[0])
        self.assertEqual(row["source"], "replay")
        self.assertIn("prompt_version_mismatch", row["warnings"])
        self.assertEqual(row["latency_ms"], 3908.4)
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertIsNone(metrics["performance"]["wall_clock_seconds"])
        self.assertIsNone(metrics["system"]["quality"]["average_total_out_of_8"])

    # ----------------------------------------------------------- experiments
    def test_bias_experiments_record_calls_tokens_and_deltas(self):
        responses = write_jsonl(self.root / "baseline.jsonl", [{
            "item_id": "T-001", "response_id": "baseline_v1",
            "response_text": "A shorter, vaguer reply.", "system_prompt_version": "v3"}])
        code, _, _ = self.run_cli(self.base("--auto-pairs-from", str(responses),
                                           "--position-limit", "1", "--verbosity-limit", "1",
                                           "--position-repeats", "2"), reply_for_url)
        self.assertEqual(code, 0)
        position = [json.loads(line) for line in (self.output / "position.jsonl").read_text().splitlines()]
        self.assertEqual(len(position), 1)
        self.assertEqual(position[0]["judge_calls"], 4)  # 2 orders x 2 repeats
        self.assertEqual(len(position[0]["trials"]), 2)
        verbosity = [json.loads(line) for line in (self.output / "verbosity.jsonl").read_text().splitlines()]
        self.assertEqual(len(verbosity), 1)
        self.assertTrue(verbosity[0]["original_grade_reused"])
        self.assertEqual(len(verbosity[0]["extra_calls"]), 1)
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["reliability"]["position_bias"]["state"], "measured")
        self.assertEqual(metrics["reliability"]["verbosity_bias"]["state"], "measured")
        self.assertEqual(metrics["performance"]["experiments"]["judge_calls"], 5)
        self.assertGreater(metrics["performance"]["experiments"]["judge_tokens"]["total"], 0)
        cost = json.loads((self.output / "cost.json").read_text(encoding="utf-8"))
        self.assertEqual(cost["basis"]["experiment_judge_calls"], 5)
        # The saved experiment files are enough to rebuild the same figures.
        code, request, _ = self.run_cli(["report", "--run", str(self.output)])
        self.assertEqual(code, 0)
        request.assert_not_called()
        rebuilt = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["performance"]["experiments"]["judge_calls"], 5)
        self.assertEqual(rebuilt["reliability"]["position_bias"]["state"], "measured")
        self.assertEqual(rebuilt["reliability"]["verbosity_bias"]["state"], "measured")

    def test_unrun_experiments_are_null_not_zero(self):
        self.run_cli(self.base(), reply_for_url)
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertIsNone(metrics["performance"]["experiments"])
        self.assertEqual(metrics["reliability"]["position_bias"]["state"], "not_run")
        self.assertIsNone(metrics["reliability"]["position_bias"]["changed_percent"])
        self.assertIsNone(metrics["reliability"]["verbosity_bias"]["changed_percent"])
        cost = json.loads((self.output / "cost.json").read_text(encoding="utf-8"))
        self.assertEqual(cost["experiments"]["status"], "not_run")
        self.assertIsNone(cost["experiments"]["total_usd"])

    # -------------------------------------------------------------- failures
    def test_system_failure_is_recorded_and_the_run_still_finishes(self):
        import urllib.error

        def broken(request, **kwargs):
            if (request if isinstance(request, str) else request.full_url).endswith("/api/tags"):
                return reply_for_url(request, **kwargs)
            raise urllib.error.HTTPError(getattr(request, "full_url", request), 500,
                                         "server error", {}, None)
        code, _, _ = self.run_cli(self.base(), broken)
        self.assertEqual(code, 1)  # item failures are reported through the exit code
        errors = [json.loads(line) for line in (self.output / "errors.jsonl").read_text().splitlines()]
        self.assertEqual([error["phase"] for error in errors], ["system"])
        self.assertEqual(errors[0]["category"], "api_error")
        metrics = json.loads((self.output / "metrics.json").read_text(encoding="utf-8"))
        self.assertIsNone(metrics["system"]["quality"]["average_total_out_of_8"])
        self.assertEqual(metrics["system"]["failures_by_category"]["api_error"], 1)
        self.assertEqual(metrics["system"]["judge_attempted"], 0)  # no reply, no judge call
        report = (self.output / "report.md").read_text(encoding="utf-8")
        self.assertIn("api_error", report)
        self.assertIn("n/a", report)

    def test_preflight_makes_no_model_call(self):
        code, request, _ = self.run_cli(self.base("--preflight"), reply_for_url)
        self.assertEqual(code, 0)
        self.assertEqual(request.call_count, 2)  # one tag probe per provider
        self.assertFalse(self.output.exists())

    # ------------------------------------------------------------- validate
    def test_validate_reports_statistics_and_prompt_hashes(self):
        code, _, output = self.run_cli(["validate", "--dataset", str(self.dataset), "--check-prompts"])
        self.assertEqual(code, 0)
        self.assertIn("system prompts available", output)
        out = self.root / "stats.json"
        code, _, _ = self.run_cli(["validate", "--dataset", str(self.dataset), "--json-out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["statistics"]["items"], 1)
        code, _, _ = self.run_cli(["validate", "--dataset", str(self.dataset), "--json-out", str(out)])
        self.assertEqual(code, 2)  # refuses to overwrite without --force
        code, _, _ = self.run_cli(["validate", "--dataset", str(self.dataset), "--json-out", str(out),
                                   "--force"])
        self.assertEqual(code, 0)

    def test_invalid_dataset_stops_before_any_call(self):
        write_jsonl(self.dataset, [{"id": "T-001", "split": "dev"}])
        code, request, _ = self.run_cli(self.base(), reply_for_url)
        self.assertEqual(code, 2)
        request.assert_not_called()

    def test_bad_flags_are_rejected(self):
        with self.assertRaises(SystemExit):
            with patch.dict("os.environ", self.env, clear=True):
                main(["run", "--limit", "0"])
        with self.assertRaises(SystemExit):
            with patch.dict("os.environ", self.env, clear=True):
                main(["run", "--position-repeats", "0"])


class RepositoryDataTests(unittest.TestCase):
    def test_validate_prints_repository_dataset_statistics(self):
        code = main(["validate", "--dataset", str(PROJECT / "data" / "dev.jsonl"),
                     "--check-prompts"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
