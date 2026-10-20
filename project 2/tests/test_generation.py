"""Regressions for missing evidence, fabricated citations and truncated replies."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch
from urllib.error import URLError

import _paths  # noqa: F401
from generation.service import call_ollama, generate_answer
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
    return {"done": True, "done_reason": "stop", "response": json.dumps(body, ensure_ascii=False),
            "prompt_eval_count": 200, "eval_count": 50}


class GenerationTests(unittest.TestCase):
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

    def test_unsupported_question_can_abstain_without_citations(self):
        answer, _ = self.generate(draft(abstain=True, reason="Le délai demandé est absent des passages.", claims=[]))
        self.assertEqual(answer.reason, "insufficient_evidence")
        self.assertEqual(answer.citations, [])

    def test_invalid_or_fabricated_outputs_never_escape_as_answers(self):
        claim = json.loads(draft()["response"])["claims"][0]
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
            dict(draft(), response="not JSON"), dict(draft(), response="[]"),
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
        supplied = json.loads(model.call_args.args[0]["prompt"])["PASSAGES"]
        self.assertLessEqual(sum(len(p["text"]) for p in supplied), 12000)
        self.assertTrue(all(len(p["text"]) <= 6000 for p in supplied))

    def test_transport_failure_and_timeout_are_distinct(self):
        for error, expected in [(URLError("connection refused"), ConnectionError), (URLError(TimeoutError()), TimeoutError)]:
            with self.subTest(error=error), patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(expected):
                    call_ollama({})


if __name__ == "__main__":
    unittest.main()
