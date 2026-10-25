"""HTTP contract and local-service failure handling, without model inference."""
import unittest
from unittest.mock import Mock, patch

import _paths  # noqa: F401
from fastapi.testclient import TestClient
from api.app import create_app
from generation.service import Answer, MODEL
from test_generation import PASSAGE, draft


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [PASSAGE]
        self.app = create_app(self.retriever)
        self.client = self.enterContext(TestClient(self.app))

    def test_real_generation_validation_is_used_by_endpoint(self):
        with patch("generation.service.call_ollama", return_value=draft()):
            response = self.client.post("/ask", json={"question": "  Conserver les livres ?  "})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["abstain"])
        self.assertEqual(body["citations"][0]["pdf_page"], 8)
        self.assertEqual(set(body["timings_ms"]), {"retrieval", "generation", "total"})
        self.retriever.retrieve.assert_called_once_with("Conserver les livres ?", method="bm25", top_k=10)

    def test_real_retrieval_covers_short_books_question(self):
        with TestClient(create_app(use_qdrant=False)) as client, patch("generation.service.call_ollama", return_value=draft()):
            response = client.post("/ask", json={"question": "Combien de temps faut-il conserver les livres de commerce ?"})
        self.assertFalse(response.json()["abstain"])
        self.assertEqual(response.json()["citations"][0]["chunk_id"], PASSAGE.chunk_id)

    def test_bad_question_is_rejected_before_retrieval(self):
        for body in [{}, {"question": " "}, {"question": "x" * 2001}, {"question": 42}, {"question": "test", "model": "other"}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/ask", json=body).status_code, 422)
        self.retriever.retrieve.assert_not_called()

    def test_invalid_citation_is_returned_as_abstention(self):
        bad = draft(claims=[{"text": "Faux délai.", "chunk_id": "invented", "quote": "invented"}])
        with patch("generation.service.call_ollama", return_value=bad):
            response = self.client.post("/ask", json={"question": "Quel délai ?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reason"], "invalid_output")
        self.assertEqual(response.json()["citations"], [])

    def test_empty_retrieval_abstains_without_calling_model(self):
        self.retriever.retrieve.return_value = []
        with patch("generation.service.call_ollama") as model:
            response = self.client.post("/ask", json={"question": "Hors corpus ?"})
        self.assertEqual(response.json()["reason"], "no_evidence")
        model.assert_not_called()

    def test_configured_retrieval_threshold_removes_weak_matches(self):
        weak = PASSAGE.__class__(**{**PASSAGE.__dict__, "score": 0.2})
        strong = PASSAGE.__class__(**{**PASSAGE.__dict__, "score": 1.2})
        self.retriever.retrieve.return_value = [weak, strong]
        with patch("api.app.MIN_RETRIEVAL_SCORE", 1.0), patch(
            "generation.service.call_ollama", return_value=draft()
        ):
            response = self.client.post("/ask", json={"question": "Test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["citations"][0]["record_id"], strong.record_id)

    def test_failures_release_lock_for_next_question(self):
        for error, status in [(ConnectionError("Ollama indisponible"), 503), (TimeoutError("Délai dépassé"), 504), (ValueError("Bad JSON"), 502)]:
            with self.subTest(status=status), patch("api.app.generate_answer", side_effect=error):
                self.assertEqual(self.client.post("/ask", json={"question": "Test"}).status_code, status)
                self.assertFalse(self.app.state.generation_lock.locked())
        with patch("api.app.generate_answer", return_value=Answer(answer_fr="Sources insuffisantes.", abstain=True)):
            self.assertEqual(self.client.post("/ask", json={"question": "Test"}).status_code, 200)

    def test_busy_model_returns_retry_response(self):
        self.app.state.generation_lock.acquire()
        try:
            response = self.client.post("/ask", json={"question": "Test"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["retry-after"], "5")
        finally:
            self.app.state.generation_lock.release()

    def test_interface_health_and_openapi_are_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="fr"', response.text)
        self.assertEqual(self.client.get("/health").json()["model"], MODEL)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/ask", schema["paths"])
        self.assertIn("Answer", schema["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
