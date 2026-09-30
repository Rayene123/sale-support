"""Provider adapter tests: request shape, one call per item, and error mapping.

The network is mocked, so these tests verify the contract the harness relies on
without calling any provider.
"""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from harness.config import SystemConfig
from harness.errors import SystemError
from harness.providers import SystemClient
from harness.prompts import available_versions, build_user_message, load_prompt

ITEM = {
    "id": "T-001",
    "customer_message": "Where is my order?",
    "order_context": {"order_number": "ORD-1", "status": "pending",
                      "items": [{"product_name": "Phone", "quantity": 1, "line_total": 10.0}]},
}
OLLAMA_CONFIG = SystemConfig(provider="ollama", model="qwen2.5:14b", max_tokens=128)
OPENAI_CONFIG = SystemConfig(provider="openai", model="openai/gpt-oss-20b", api_key_env="TEST_KEY",
                             max_tokens=128)


def hosted_key():
    """A dummy key in the environment the hosted provider reads from."""
    return patch.dict("os.environ", {"TEST_KEY": "secret-value"}, clear=False)


def ollama_payload(**overrides):
    payload = {"model": "qwen2.5:14b", "done": True,
               "message": {"content": "Order ORD-1 is pending."},
               "prompt_eval_count": 120, "eval_count": 30, "eval_duration": 3_000_000_000}
    payload.update(overrides)
    return io.BytesIO(json.dumps(payload).encode())


def openai_payload(finish="stop", content="Order ORD-1 is pending."):
    return io.BytesIO(json.dumps({
        "model": "openai/gpt-oss-20b",
        "choices": [{"finish_reason": finish, "message": {"content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }).encode())


class ProviderTests(unittest.TestCase):
    def test_ollama_request_has_one_message_pair_and_no_tools(self):
        with patch("urllib.request.urlopen", return_value=ollama_payload()) as request:
            result = SystemClient(OLLAMA_CONFIG, "SYSTEM").generate("user text")
        sent = request.call_args.args[0]
        body = json.loads(sent.data)
        self.assertEqual(sent.full_url, "http://localhost:11434/api/chat")
        self.assertEqual([message["role"] for message in body["messages"]], ["system", "user"])
        self.assertEqual(body["messages"][1]["content"], "user text")
        self.assertNotIn("tools", body)
        self.assertNotIn("functions", body)
        self.assertFalse(body["stream"])
        self.assertFalse(body["think"])
        self.assertEqual(body["options"], {"temperature": 0.0, "num_predict": 128})
        self.assertEqual(result["usage"], {"prompt": 120, "completion": 30, "total": 150})
        self.assertEqual(result["decode_tokens_per_second"], 10.0)

    def test_openai_request_uses_chat_completions_and_bearer_key(self):
        with hosted_key(), patch("urllib.request.urlopen", return_value=openai_payload()) as request:
            result = SystemClient(OPENAI_CONFIG, "SYSTEM").generate("user text")
        sent = request.call_args.args[0]
        body = json.loads(sent.data)
        self.assertEqual(sent.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(sent.headers["Authorization"], "Bearer secret-value")
        self.assertEqual(body["max_tokens"], 128)
        self.assertEqual(body["temperature"], 0.0)
        self.assertNotIn("tools", body)
        self.assertEqual(result["usage"]["total"], 150)
        self.assertNotIn("secret-value", json.dumps(result["usage"]))

    def test_missing_key_is_a_configuration_error_before_any_request(self):
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.urlopen") as request:
            with self.assertRaises(SystemError) as caught:
                SystemClient(OPENAI_CONFIG, "SYSTEM").generate("user text")
            request.assert_not_called()
        self.assertEqual(caught.exception.kind, "configuration")

    def test_http_errors_are_mapped_and_the_body_is_never_echoed(self):
        # A 404 only means "model missing" for the local provider; on a hosted
        # gateway the same status is a URL or access problem.
        cases = [(urllib.error.HTTPError("https://x", 401, "secret-value", {}, None), "api_error"),
                 (urllib.error.HTTPError("https://x", 404, "secret-value", {}, None), "api_error"),
                 (urllib.error.HTTPError("https://x", 429, "secret-value", {}, None), "api_error"),
                 (urllib.error.HTTPError("https://x", 500, "secret-value", {}, None), "api_error")]
        for error, kind in cases:
            with self.subTest(kind=kind, code=error.code):
                with hosted_key(), patch("urllib.request.urlopen", side_effect=error):
                    with self.assertRaises(SystemError) as caught:
                        SystemClient(OPENAI_CONFIG, "SYSTEM").generate("user text")
                self.assertEqual(caught.exception.kind, kind)
                self.assertNotIn("secret-value", str(caught.exception))
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("http://x", 404, "", {}, None)):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OLLAMA_CONFIG, "SYSTEM").generate("user text")
        self.assertIn("ollama pull", str(caught.exception))

    def test_timeout_and_network_failures_are_distinct(self):
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OLLAMA_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "timeout")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OLLAMA_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "network")

    def test_truncated_and_empty_answers_are_reported(self):
        with hosted_key(), patch("urllib.request.urlopen", return_value=openai_payload(finish="length")):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OPENAI_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "incomplete_output")
        with hosted_key(), patch("urllib.request.urlopen", return_value=openai_payload(content="   ")):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OPENAI_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "system_error")
        with hosted_key(), patch("urllib.request.urlopen", return_value=io.BytesIO(b"not json")):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OPENAI_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "api_error")

    def test_refusal_is_its_own_category(self):
        payload = json.dumps({"model": "m", "choices": [{"finish_reason": "stop",
                                                         "message": {"content": None, "refusal": "no"}}]})
        with hosted_key(), patch("urllib.request.urlopen", return_value=io.BytesIO(payload.encode())):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OPENAI_CONFIG, "SYSTEM").generate("x")
        self.assertEqual(caught.exception.kind, "refusal")

    def test_preflight_detects_missing_local_model(self):
        tags = io.BytesIO(json.dumps({"models": [{"name": "llama3.1:8b"}]}).encode())
        with patch("urllib.request.urlopen", return_value=tags):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OLLAMA_CONFIG, "SYSTEM").preflight()
        self.assertEqual(caught.exception.kind, "model_missing")
        tags = io.BytesIO(json.dumps({"models": [{"name": "qwen2.5:14b"}]}).encode())
        with patch("urllib.request.urlopen", return_value=tags):
            self.assertTrue(SystemClient(OLLAMA_CONFIG, "SYSTEM").preflight()["checks"][0]["ok"])
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaises(SystemError) as caught:
                SystemClient(OLLAMA_CONFIG, "SYSTEM").preflight()
        self.assertEqual(caught.exception.kind, "network")

    def test_preflight_requires_a_prompt(self):
        with self.assertRaises(SystemError):
            SystemClient(OLLAMA_CONFIG, None).preflight()

    def test_prompt_registry_and_user_message(self):
        versions = available_versions()
        self.assertEqual(set(versions), {"v1", "v2", "v3"})
        text, sha, path = load_prompt("v3")
        self.assertEqual(sha, versions["v3"]["sha256"])
        self.assertTrue(text.strip())
        self.assertTrue(path.endswith("system_v3.txt"))
        with self.assertRaises(Exception):
            load_prompt("v9")
        message = build_user_message(ITEM)
        self.assertTrue(message.startswith("Customer message:\nWhere is my order?"))
        self.assertIn('"order_number": "ORD-1"', message)


if __name__ == "__main__":
    unittest.main()
