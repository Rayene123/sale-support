"""HTTP contract and local-service failure handling, without model inference."""
import asyncio
import json
import unittest
from threading import Event
from unittest.mock import Mock, patch

import _paths  # noqa: F401
from fastapi.testclient import TestClient
from fastapi import Request
from api.app import Question, create_app
from generation.questions import SearchPlan
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
        self.assertEqual(body["citations"][0]["heading_path"], ["Livre I"])
        self.assertEqual(set(body["timings_ms"]), {"rewrite", "retrieval", "generation", "total"})
        self.retriever.retrieve.assert_called_once_with("Pendant combien de temps faut-il conserver les livres de commerce ?", method="bm25", top_k=10)

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
            response = self.client.post("/ask", json={"question": "Quel délai de conservation des livres ?"})
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
        with patch.object(self.app.state, "threshold", 1.0), patch(
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
            for path in ("/ask", "/ask/stream"):
                response = self.client.post(path, json={"question": "Test"})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers["retry-after"], "5")
        finally:
            self.app.state.generation_lock.release()

    def test_interface_health_and_openapi_are_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="fr"', response.text)
        self.assertIn('id="library"', response.text)
        self.assertIn('id="reset"', response.text)
        self.assertEqual(self.client.get("/health").json()["model"], MODEL)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/ask", schema["paths"])
        self.assertIn("Answer", schema["components"]["schemas"])

    def test_pixel_assets_are_served_with_their_media_types(self):
        for path, media in [("/library.js", "javascript"), ("/pixel.ttf", "font/ttf"),
                            ("/assets/midnight-library.png", "image/png")]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(media, response.headers["content-type"])
        self.assertEqual(self.client.get("/library.js").headers["cache-control"], "no-cache")
        self.assertTrue(self.client.get("/assets/midnight-library.png").content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_book_reader_returns_trusted_corpus_text(self):
        response = self.client.get("/articles/code-commerce-tn:article-10")
        self.assertEqual(response.status_code, 200)
        article = response.json()
        self.assertEqual(article["record_id"], "code-commerce-tn:article-10")
        self.assertEqual(article["article"], "Article 10")
        self.assertIn("Ils seront conservés pendant dix ans.", article["text"])
        self.assertEqual(article["pdf_page"], 9)
        self.assertTrue(article["heading_path"])
        self.assertEqual(self.client.get("/articles/unknown").status_code, 404)

    def test_stream_progress_and_result_share_the_validated_answer_contract(self):
        with patch("generation.service.call_ollama", return_value=draft()):
            response = self.client.post("/ask/stream", json={"question": "Conserver les livres ?"})
            ordinary = self.client.post("/ask", json={"question": "Conserver les livres ?"}).json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([event["type"] for event in events],
                         ["rewrite", "retrieval", "evidence", "generation", "validation", "result"])
        self.assertEqual(events[1]["method"], "bm25")
        self.assertEqual(events[2]["passages"][0]["chunk_id"], PASSAGE.chunk_id)
        self.assertNotIn("text", events[2]["passages"][0])
        self.assertEqual(events[-1]["answer"]["answer_fr"], ordinary["answer_fr"])
        self.assertEqual(events[-1]["answer"]["citations"], ordinary["citations"])
        self.assertFalse(self.app.state.generation_lock.locked())

    def test_progress_is_available_before_the_model_returns(self):
        entered, release = Event(), Event()
        def model(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test model was not released")
            return draft()
        endpoint = next(route.endpoint for route in self.app.routes if route.path == "/ask/stream")
        async def consume(response):
            types = []
            async for line in response.body_iterator:
                event = json.loads(line)
                types.append(event["type"])
                if event["type"] == "generation":
                    self.assertTrue(entered.wait(1))
                    self.assertFalse(release.is_set())
                    self.assertTrue(self.app.state.generation_lock.locked())
                    self.assertNotIn("validation", types)
                    release.set()
            self.assertEqual(types[-2:], ["validation", "result"])
        try:
            with patch("generation.service.call_ollama", side_effect=model):
                response = endpoint(Question(question="Conserver les livres ?"), Request({"type": "http", "app": self.app}))
                asyncio.run(consume(response))
        finally:
            release.set()

    def test_clarification_does_not_invent_retrieval_or_generation_stages(self):
        with patch("api.app.prepare_question", return_value=(SearchPlan(queries=[], clarification="Quel délai ?"), {})), patch("api.app.generate_answer") as model:
            response = self.client.post("/ask/stream", json={"question": "Et ce délai ?"})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([event["type"] for event in events], ["rewrite", "result"])
        self.assertEqual(events[-1]["answer"]["reason"], "clarification")
        model.assert_not_called()

    def test_empty_evidence_and_invalid_citations_cannot_be_delivered(self):
        self.retriever.retrieve.return_value = []
        with patch("generation.service.call_ollama") as model:
            empty = self.client.post("/ask/stream", json={"question": "Une question précise"})
        events = [json.loads(line) for line in empty.text.splitlines()]
        self.assertEqual([event["type"] for event in events], ["rewrite", "retrieval", "evidence", "result"])
        self.assertEqual(events[2]["passages"], [])
        model.assert_not_called()
        self.retriever.retrieve.return_value = [PASSAGE]
        with patch("generation.service.call_ollama", return_value=draft(claims=[{"text": "Faux", "chunk_id": "invented", "quote": "invented"}])):
            bad = self.client.post("/ask/stream", json={"question": "Une question précise"})
        answer = json.loads(bad.text.splitlines()[-1])["answer"]
        self.assertEqual(answer["reason"], "invalid_output")
        self.assertEqual(answer["citations"], [])

    def test_stream_errors_are_terminal_safe_and_release_the_lock(self):
        for error, status in [(ConnectionError("Private details"), 503), (TimeoutError("Timeout"), 504), (RuntimeError("Private details"), 500)]:
            with self.subTest(status=status), patch("api.app.generate_answer", side_effect=error):
                response = self.client.post("/ask/stream", json={"question": "Une question précise"})
            final = json.loads(response.text.splitlines()[-1])
            self.assertEqual(final["type"], "error")
            self.assertEqual(final["status"], status)
            if status == 500:
                self.assertNotIn("Private details", response.text)
            self.assertFalse(self.app.state.generation_lock.locked())
        with patch("api.app.Thread") as worker:
            worker.return_value.start.side_effect = RuntimeError("Cannot create worker")
            self.assertEqual(self.client.post("/ask/stream", json={"question": "Test"}).status_code, 503)
        self.assertFalse(self.app.state.generation_lock.locked())


if __name__ == "__main__":
    unittest.main()
