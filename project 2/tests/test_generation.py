"""Regressions for missing evidence, fabricated citations and truncated replies."""
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import _paths  # noqa: F401
from generation.service import Draft, call_groq, call_ollama, call_openai, generate_answer
from models.retrieval import RetrievalResult


PASSAGE = RetrievalResult(
    chunk_id="code-commerce-tn:article-10:chunk-0", record_id="code-commerce-tn:article-10",
    text="Les livres sont tenus chronologiquement sans blanc ni altération d'aucune sorte. Ils seront conservés pendant dix ans.",
    score=2.0, rank=1, article_number=10, article="Article 10", heading_path=("Livre I",),
    pdf_page=8, source_url="https://example.invalid/code.pdf", retrieval_method="bm25",
)


def draft(**changes):
    body = {"abstain": False, "reason": "", "claims": [{
        "text": "Les livres doivent être conservés pendant dix ans.",
        "chunk_id": PASSAGE.chunk_id, "quote": "Ils seront conservés pendant dix ans.",
    }]}
    body.update(changes)
    return {"done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(body, ensure_ascii=False)},
            "prompt_eval_count": 200, "eval_count": 50}


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"ALLOW_PAID_CALLS": "true"}))

    def test_paid_calls_disabled_even_when_a_key_is_present(self):
        with patch.dict(os.environ, {"ALLOW_PAID_CALLS": "false", "GROQ_API_KEY": "test-only-key"}), patch("generation.service.urllib.request.urlopen") as http:
            with self.assertRaisesRegex(ConnectionError, "désactivés"):
                call_groq({})
        http.assert_not_called()

    def test_openai_paid_calls_disabled_even_when_a_key_is_present(self):
        with patch.dict(os.environ, {"ALLOW_PAID_CALLS": "false", "OPENAI_API_KEY": "test-only-key"}), patch("generation.service.urllib.request.urlopen") as http:
            with self.assertRaises(ConnectionError):
                call_openai("system", "question", Draft.model_json_schema())
        http.assert_not_called()

    def generate(self, response, passages=None):
        with patch("generation.service.call_ollama", return_value=response) as model:
            answer = generate_answer("Combien de temps conserver les livres ?", passages if passages is not None else [PASSAGE])
        return answer, model

    def test_valid_answer_links_each_claim_to_trusted_metadata(self):
        answer, model = self.generate(draft())
        self.assertFalse(answer.abstain)
        self.assertTrue(answer.answer_fr.endswith("[1]"))
        self.assertEqual(answer.citations[0].pdf_page, 8)
        self.assertEqual(answer.citations[0].record_id, PASSAGE.record_id)
        self.assertEqual(answer.usage, {"prompt_tokens": 200, "completion_tokens": 50})
        request = model.call_args.args[0]
        self.assertFalse(request["think"])
        self.assertEqual(request["options"]["num_ctx"], 8192)

    def test_no_evidence_skips_model(self):
        answer, model = self.generate(draft(), passages=[])
        self.assertEqual(answer.reason, "no_evidence")
        model.assert_not_called()

    def test_generation_context_character_budget_is_configurable(self):
        with patch("generation.service.GENERATION_CONTEXT_CHARS", 80), \
                patch("generation.service.call_ollama", return_value=draft()) as model:
            generate_answer("Question", [PASSAGE])
        request = model.call_args.args[0]
        supplied = json.loads(request["prompt"])["PASSAGES"]
        self.assertEqual(sum(len(passage["text"]) for passage in supplied), 80)

    def test_unsupported_question_can_abstain_without_citations(self):
        answer, _ = self.generate(draft(abstain=True, reason="Le délai demandé est absent des passages.", claims=[]))
        self.assertEqual(answer.reason, "insufficient_evidence")
        self.assertEqual(answer.citations, [])

    def test_invalid_or_fabricated_outputs_never_escape_as_answers(self):
        claim = json.loads(draft()["message"]["content"])["claims"][0]
        invalid = [
            draft(claims=[dict(claim, chunk_id="article-9999")]),
            draft(claims=[dict(claim, chunk_id=PASSAGE.record_id)]),
            draft(claims=[dict(claim, quote="Les livres... conservés pendant dix ans.")]),
            draft(claims=[dict(claim, quote="Ils seront conservés pendant vingt ans.")]),
            draft(claims=[dict(claim, quote=" ")]),
            draft(claims=[dict(claim, quote="Ils seront conserves pendant dix ans.")]),
            draft(claims=[dict(claim, article="Article 9999")]),
            draft(claims=[claim, dict(claim, chunk_id="article-9999")]),
            draft(claims=[]), draft(abstain=True), draft(abstain="false"),
            draft(abstain=True, reason="", claims=[]),
            dict(draft(), done_reason="length"), dict(draft(), done=False),
            dict(draft(), message={"role": "assistant", "content": "not JSON"}),
            dict(draft(), message={"role": "assistant", "content": "[]"}),
        ]
        for response in invalid:
            with self.subTest(response=response):
                answer, _ = self.generate(response)
                self.assertTrue(answer.abstain)
                self.assertEqual(answer.reason, "invalid_output")
                self.assertEqual(answer.citations, [])

    def test_whitespace_is_normalized_but_words_are_not_repaired(self):
        passage = replace(PASSAGE, text=PASSAGE.text.replace("pendant dix", "pendant\n dix"))
        answer, _ = self.generate(draft(), [passage])
        self.assertFalse(answer.abstain)

    def test_cannot_cite_text_that_was_not_sent_to_model(self):
        passage = replace(PASSAGE, text="A" * 6500 + " Ils seront conservés pendant dix ans.")
        answer, model = self.generate(draft(), [passage] * 5)
        self.assertTrue(answer.abstain)
        user_message = model.call_args.args[0]["prompt"]
        supplied = json.loads(user_message)["PASSAGES"]
        self.assertLessEqual(sum(len(p["text"]) for p in supplied), 12000)
        self.assertTrue(all(len(p["text"]) <= 6000 for p in supplied))

    def test_transport_failure_and_timeout_are_distinct(self):
        for error, expected in [(URLError("connection refused"), ConnectionError), (URLError(TimeoutError()), TimeoutError)]:
            with self.subTest(error=error), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(expected):
                    call_ollama({})

    def test_ollama_generate_request_uses_expected_configuration_and_schema(self):
        body = draft()
        body["response"] = body.pop("message")["content"]
        response = io.BytesIO(json.dumps(body).encode("utf-8"))
        context = MagicMock()
        context.__enter__.return_value = response
        with (
            patch("generation.service.GENERATION_PROVIDER", "ollama"),
            patch("generation.service.MODEL", "qwen3.5:9b"),
            patch("generation.service.OLLAMA_URL", "http://127.0.0.1:11434"),
            patch("generation.service.urllib.request.urlopen", return_value=context) as http,
        ):
            answer = generate_answer("Combien de temps conserver les livres ?", [PASSAGE])

        request = http.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(payload["model"], "qwen3.5:9b")
        self.assertIn("Réponds exclusivement en français", payload["system"])
        self.assertIn('"QUESTION": "Combien de temps conserver les livres ?"', payload["prompt"])
        self.assertIsInstance(payload["format"], dict)
        self.assertFalse(payload["think"])
        self.assertFalse(payload["stream"])
        self.assertFalse(answer.abstain)

    def test_groq_chat_request_auth_schema_and_successful_response(self):
        groq_response = {
            "choices": [{
                "message": {"role": "assistant", "content": draft()["message"]["content"]},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 321, "completion_tokens": 42},
        }
        context = MagicMock()
        context.__enter__.return_value = io.BytesIO(json.dumps(groq_response).encode("utf-8"))
        with (
            patch("generation.service.GENERATION_PROVIDER", "groq"),
            patch("generation.service.GROQ_MODEL", "openai/gpt-oss-20b"),
            patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}),
            patch("generation.service.urllib.request.urlopen", return_value=context) as http,
        ):
            answer = generate_answer("Combien de temps conserver les livres ?", [PASSAGE])

        request = http.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only-key")
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual([message["role"] for message in payload["messages"]], ["system", "user"])
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        provider_schema = payload["response_format"]["json_schema"]["schema"]

        def schema_keys(value):
            if isinstance(value, dict):
                return set(value).union(*(schema_keys(child) for child in value.values()))
            if isinstance(value, list):
                return set().union(*(schema_keys(child) for child in value))
            return set()

        self.assertTrue({"$defs", "$ref"}.issubset(schema_keys(provider_schema)))
        self.assertTrue({"required", "additionalProperties"}.issubset(schema_keys(provider_schema)))
        self.assertTrue({"minLength", "maxLength", "maxItems"}.isdisjoint(schema_keys(provider_schema)))
        # These limits remain in the local Draft schema and are enforced after
        # parsing the provider's string content.
        local_schema_keys = schema_keys(Draft.model_json_schema())
        self.assertTrue({"minLength", "maxLength", "maxItems"}.issubset(local_schema_keys))
        self.assertFalse(payload["stream"])
        self.assertFalse(answer.abstain)
        self.assertEqual(answer.citations[0].record_id, PASSAGE.record_id)
        self.assertEqual(answer.usage, {"prompt_tokens": 321, "completion_tokens": 42})

    def test_groq_missing_key_fails_without_http_request(self):
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": ""}),
            patch("generation.service.urllib.request.urlopen") as http,
        ):
            with self.assertRaisesRegex(ConnectionError, "GROQ_API_KEY is required"):
                call_groq({"model": "openai/gpt-oss-20b"})
        http.assert_not_called()

    def test_openai_missing_key_fails_without_http_request(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": ""}),
            patch("generation.service.urllib.request.urlopen") as http,
        ):
            with self.assertRaises(ConnectionError):
                call_openai("system", "question", Draft.model_json_schema())
        http.assert_not_called()

    def test_openai_response_auth_schema_and_service_tier(self):
        api_response = {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": draft()["message"]["content"]}]}],
            "usage": {"input_tokens": 234, "output_tokens": 38},
            "service_tier": "flex",
        }
        context = MagicMock()
        context.__enter__.return_value = io.BytesIO(json.dumps(api_response).encode("utf-8"))
        with (
            patch("generation.service.GENERATION_PROVIDER", "openai"),
            patch("generation.service.OPENAI_MODEL", "gpt-6-luna"),
            patch("generation.service.OPENAI_SERVICE_TIER", "flex"),
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-key"}),
            patch("generation.service.urllib.request.urlopen", return_value=context) as http,
        ):
            answer = generate_answer("Combien de temps conserver les livres ?", [PASSAGE])

        request = http.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only-key")
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(payload["reasoning"]["effort"], "none")
        self.assertEqual(payload["service_tier"], "flex")
        self.assertEqual(payload["max_output_tokens"], 640)
        self.assertFalse(payload["store"])
        self.assertFalse(answer.abstain)
        self.assertEqual(answer.citations[0].record_id, PASSAGE.record_id)
        self.assertEqual(answer.usage, {"prompt_tokens": 234, "completion_tokens": 38})
        self.assertEqual(answer.configuration["openai_service_tier_requested"], "flex")
        self.assertEqual(answer.configuration["openai_service_tier_actual"], "flex")

    def test_groq_timeout_and_http_errors_are_sanitized(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}):
            with patch("generation.service.urllib.request.urlopen", side_effect=TimeoutError):
                with self.assertRaisesRegex(TimeoutError, "Groq generation timed out"):
                    call_groq({})

            for status, expected in [(401, ValueError), (429, ConnectionError), (503, ConnectionError)]:
                error = HTTPError(
                    "https://api.groq.com/openai/v1/chat/completions",
                    status,
                    "provider error containing no logged credentials",
                    {},
                    io.BytesIO(b'{"error":"private response detail"}'),
                )
                with self.subTest(status=status), patch(
                    "generation.service.urllib.request.urlopen", side_effect=error
                ):
                    with self.assertRaises(expected) as raised:
                        call_groq({})
                    self.assertNotIn("test-only-key", str(raised.exception))
                    self.assertNotIn("private response detail", str(raised.exception))

    def test_groq_http_rejection_logs_status_and_sanitized_body_only(self):
        sensitive_prompt = "private question content that must not appear in logs"
        error_body = json.dumps({
            "error": {
                "type": "invalid_request_error",
                "code": "invalid_json_schema",
                "message": f"Schema rejected while processing {sensitive_prompt}",
            }
        }).encode("utf-8")
        error = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            400,
            "Bad Request",
            {},
            io.BytesIO(error_body),
        )
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}),
            patch("generation.service.urllib.request.urlopen", side_effect=error),
            self.assertLogs("generation.service", level="ERROR") as captured,
        ):
            with self.assertRaisesRegex(ValueError, "HTTP 400"):
                call_groq({"messages": [{"role": "user", "content": sensitive_prompt}]})

        log_output = "\n".join(captured.output)
        self.assertIn('"status": 400', log_output)
        self.assertIn('"type": "invalid_request_error"', log_output)
        self.assertIn('"code": "invalid_json_schema"', log_output)
        self.assertIn('"category": "structured_output_rejected"', log_output)
        self.assertNotIn("test-only-key", log_output)
        self.assertNotIn(sensitive_prompt, log_output)
        self.assertNotIn("Schema rejected while processing", log_output)

    def test_groq_forbidden_plain_text_error_is_classified_without_logging_body(self):
        raw_error = b"Request Forbidden"
        error = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            403,
            "Forbidden",
            {},
            io.BytesIO(raw_error),
        )
        request_payload = {
            "model": "openai/gpt-oss-20b",
            "messages": [
                {"role": "system", "content": "private system prompt"},
                {"role": "user", "content": "private question"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "strict": True,
                    "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
                },
            },
            "stream": False,
            "temperature": 0,
            "max_completion_tokens": 640,
        }
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}),
            patch("generation.service.urllib.request.urlopen", side_effect=error),
            self.assertLogs("generation.service", level="ERROR") as captured,
        ):
            with self.assertRaisesRegex(ValueError, "HTTP 403"):
                call_groq(request_payload)

        log_output = "\n".join(captured.output)
        self.assertIn('"status": 403', log_output)
        self.assertIn('"body_bytes": 17', log_output)
        self.assertIn('"category": "access_forbidden"', log_output)
        self.assertIn('"body_class": "forbidden"', log_output)
        self.assertIn('"model": "openai/gpt-oss-20b"', log_output)
        self.assertIn('"response_format": "json_schema"', log_output)
        self.assertIn('"strict_schema": true', log_output)
        self.assertIn('"authorization_present": true', log_output)
        self.assertNotIn(raw_error.decode(), log_output)
        self.assertNotIn("test-only-key", log_output)
        self.assertNotIn("private question", log_output)
        self.assertNotIn("private system prompt", log_output)

    def test_groq_draft_parse_failure_logs_type_without_content(self):
        private_response = "private generated text that must not appear in logs"
        normalized = {
            "done": True,
            "done_reason": "stop",
            "message": {"content": private_response},
        }
        with (
            patch("generation.service.GENERATION_PROVIDER", "groq"),
            patch("generation.service.call_groq", return_value=normalized),
            self.assertLogs("generation.service", level="ERROR") as captured,
        ):
            answer = generate_answer("Question", [PASSAGE])

        self.assertTrue(answer.abstain)
        self.assertEqual(answer.reason, "invalid_output")
        log_output = "\n".join(captured.output)
        self.assertIn('"phase": "draft_json"', log_output)
        self.assertIn('"exception_type": "ValidationError"', log_output)
        self.assertNotIn(private_response, log_output)

    def test_groq_malformed_provider_response_fails_safely(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}):
            malformed_payloads = [
                (b"{bad", "malformed JSON"),
                (b'{"choices": []}', "incomplete chat completion"),
                (
                    json.dumps({
                        "choices": [{
                            "message": {"content": "{}"},
                            "finish_reason": "stop",
                        }],
                        "usage": [],
                    }).encode("utf-8"),
                    "incomplete chat completion",
                ),
            ]
            for content, expected in malformed_payloads:
                context = MagicMock()
                context.__enter__.return_value = io.BytesIO(content)
                with self.subTest(content=content), patch(
                    "generation.service.urllib.request.urlopen", return_value=context
                ):
                    with self.assertRaisesRegex(ValueError, expected):
                        call_groq({})

    def test_groq_output_still_requires_valid_citation_and_quote(self):
        malformed_claim = {
            "abstain": False,
            "reason": "",
            "claims": [{
                "text": "Les livres sont conservés pendant vingt ans.",
                "chunk_id": PASSAGE.chunk_id,
                "quote": "Ils seront conservés pendant vingt ans.",
            }],
        }
        normalized = {
            "done": True,
            "done_reason": "stop",
            "message": {"content": json.dumps(malformed_claim, ensure_ascii=False)},
        }
        with (
            patch("generation.service.GENERATION_PROVIDER", "groq"),
            patch("generation.service.call_groq", return_value=normalized),
        ):
            answer = generate_answer("Combien de temps conserver les livres ?", [PASSAGE])
        self.assertTrue(answer.abstain)
        self.assertEqual(answer.reason, "invalid_output")
        self.assertEqual(answer.citations, [])


class OpenAIAdapterTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"ALLOW_PAID_CALLS": "true", "OPENAI_API_KEY": "test-only-key"}))

    def envelope(self, **changes):
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": draft()["message"]["content"]}]}],
            "usage": {"input_tokens": 200, "output_tokens": 50}, **changes}

    def http(self, data):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(data).encode()
        return response

    def test_openai_strict_response_uses_existing_citation_validation(self):
        with patch("generation.service.GENERATION_PROVIDER", "openai"), patch(
                "generation.service.urllib.request.urlopen", return_value=self.http(self.envelope())) as http:
            answer = generate_answer("Conservation ?", [PASSAGE])
        self.assertFalse(answer.abstain)
        self.assertEqual(answer.citations[0].record_id, PASSAGE.record_id)
        self.assertEqual(answer.usage, {"prompt_tokens": 200, "completion_tokens": 50})
        request = http.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertEqual(payload["max_output_tokens"], 640)
        self.assertTrue(payload["text"]["format"]["strict"])

    def test_openai_disabled_or_missing_key_does_not_send_request(self):
        for settings in [{"ALLOW_PAID_CALLS": "false"}, {"OPENAI_API_KEY": ""}]:
            with self.subTest(settings=settings), patch.dict(os.environ, settings), patch(
                    "generation.service.urllib.request.urlopen") as http:
                with self.assertRaises(ConnectionError):
                    call_openai("system", "question", Draft.model_json_schema())
                http.assert_not_called()

    def test_openai_incomplete_refusal_and_bad_citations_abstain(self):
        bad = self.envelope()
        bad["output"][0]["content"][0]["text"] = draft()["message"]["content"].replace("dix ans.", "vingt ans.")
        for result in [self.envelope(status="incomplete"), self.envelope(output=[]), bad]:
            with self.subTest(result=result), patch("generation.service.GENERATION_PROVIDER", "openai"), patch(
                    "generation.service.urllib.request.urlopen", return_value=self.http(result)):
                answer = generate_answer("Conservation ?", [PASSAGE])
                self.assertEqual(answer.reason, "invalid_output")
                self.assertFalse(answer.citations)

    def test_openai_transport_errors_are_safe_and_not_retried(self):
        for status, error_type in [(401, ConnectionError), (429, ConnectionError), (503, ConnectionError), (400, ValueError)]:
            error = HTTPError("https://api.openai.com/v1/responses", status, "secret-provider-body", {}, io.BytesIO(b"secret"))
            with self.subTest(status=status), patch("generation.service.urllib.request.urlopen", side_effect=error) as http:
                with self.assertRaises(error_type) as caught:
                    call_openai("system", "question", Draft.model_json_schema())
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(http.call_count, 1)
        with patch("generation.service.urllib.request.urlopen", side_effect=URLError(TimeoutError())):
            with self.assertRaises(TimeoutError):
                call_openai("system", "question", Draft.model_json_schema())

    def test_openai_malformed_usage_is_rejected(self):
        for usage in [[], {"input_tokens": -1}, {"output_tokens": True}]:
            with self.subTest(usage=usage), patch("generation.service.urllib.request.urlopen", return_value=self.http(self.envelope(usage=usage))):
                with self.assertRaises(ValueError):
                    call_openai("system", "question", Draft.model_json_schema())

    def test_openai_rewrite_schema_requires_defaulted_fields(self):
        from generation.questions import SearchPlan
        with patch("generation.service.urllib.request.urlopen", return_value=self.http(self.envelope())) as http:
            call_openai("system", "question", SearchPlan.model_json_schema(), timeout=20, max_output_tokens=256)
        payload = json.loads(http.call_args.args[0].data)
        schema = payload["text"]["format"]["schema"]
        self.assertEqual(set(schema["required"]), {"queries", "clarification"})
        self.assertNotIn("default", schema["properties"]["clarification"])
        self.assertEqual(payload["max_output_tokens"], 256)
        self.assertEqual(http.call_args.kwargs["timeout"], 20)

    def test_persistent_budget_blocks_before_http_and_settles_usage(self):
        with tempfile.TemporaryDirectory() as folder, patch("generation.service.OPENAI_MODEL", "gpt-6-luna"), patch.dict(
                os.environ, {"OPENAI_BUDGET_FILE": str(Path(folder) / "budget.sqlite"), "OPENAI_BUDGET_USD": "0.001"}), patch(
                "generation.service.urllib.request.urlopen", return_value=self.http(self.envelope())) as http:
            with self.assertRaisesRegex(ConnectionError, "budget"):
                call_openai("system", "question", Draft.model_json_schema())
            http.assert_not_called()
            os.environ["OPENAI_BUDGET_USD"] = "0.1"
            call_openai("system", "question", Draft.model_json_schema())
            with closing(sqlite3.connect(os.environ["OPENAI_BUDGET_FILE"])) as db:
                reserved, charged = db.execute("SELECT reserved,charged FROM calls").fetchone()
            self.assertGreater(reserved, charged)
            self.assertAlmostEqual(charged, (200 * .125 + 50 * .5) / 1e6)

    def test_failed_calls_keep_the_reservation_and_unknown_model_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                "OPENAI_BUDGET_FILE": str(Path(folder) / "budget.sqlite"), "OPENAI_BUDGET_USD": "0.1"}), patch(
                "generation.service.OPENAI_MODEL", "gpt-6-luna"), patch(
                "generation.service.urllib.request.urlopen", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                call_openai("system", "question", Draft.model_json_schema())
            with closing(sqlite3.connect(os.environ["OPENAI_BUDGET_FILE"])) as db:
                self.assertIsNone(db.execute("SELECT charged FROM calls").fetchone()[0])
            with patch("generation.service.OPENAI_MODEL", "unpriced-model"), patch("generation.service.urllib.request.urlopen") as http:
                with self.assertRaises(ConnectionError):
                    call_openai("system", "question", Draft.model_json_schema())
                http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
