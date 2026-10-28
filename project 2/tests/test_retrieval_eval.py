"""Focused tests for the evaluation adapter and deterministic retrieval metrics."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import _paths  # noqa: F401

PROJECT_DIR = Path(__file__).resolve().parents[1]
EVALUATOR_SPEC = importlib.util.spec_from_file_location(
    "retrieval_eval", PROJECT_DIR / "eval" / "retrieval.py"
)
retrieval = importlib.util.module_from_spec(EVALUATOR_SPEC)
assert EVALUATOR_SPEC.loader is not None
EVALUATOR_SPEC.loader.exec_module(retrieval)


class FakeRetriever:
    def __init__(self, record_ids):
        self.record_ids = record_ids

    def search(self, question, *, top_k):
        return [SimpleNamespace(record_id=rid) for rid in self.record_ids[:top_k]]


def normalized(question_id, gold, *, answerability="answerable", status="approved"):
    return {
        "question_id": question_id,
        "question": f"Question {question_id}?",
        "answerability": answerability,
        "review_status": status,
        "required_gold_record_ids": list(gold),
        "source_format": "canonical",
    }


class RetrievalEvaluationTests(unittest.TestCase):
    def test_distinct_article_recall_expands_past_duplicate_chunks(self):
        result = retrieval.evaluate(FakeRetriever(["A", "A", "B"]),
                                    [normalized("windows", ["B"])], "window", (2,))
        self.assertEqual(result["metrics_by_k"]["2"]["recall_macro_average"], 1.)
        self.assertEqual(result["per_question"][0]["retrieved_unique_record_ids"], ["A", "B"])

    def test_distinct_article_search_stops_when_candidates_are_exhausted(self):
        result = retrieval.evaluate(FakeRetriever(["A", "A"]),
                                    [normalized("windows", ["B"])], "window", (2,))
        self.assertEqual(result["metrics_by_k"]["2"]["recall_macro_average"], 0.)

    def test_reranking_keeps_enough_candidates_for_distinct_article_metrics(self):
        candidates = [SimpleNamespace(record_id=rid) for rid in ("A", "A", "B")]
        with patch("retrieval.rerank.rerank", side_effect=lambda q, r, top_k: r[:top_k]) as reranker:
            result = retrieval.evaluate(FakeRetriever([r.record_id for r in candidates]),
                                        [normalized("windows", ["B"])], "window", (2,), rerank_results=True)
        self.assertEqual(result["metrics_by_k"]["2"]["recall_macro_average"], 1.)
        self.assertEqual(reranker.call_args.kwargs["top_k"], 3)

    def test_builder_selects_only_requested_method(self):
        with (
            patch("indexing.corpus.load_corpus", return_value=["corpus"]),
            patch("indexing.chunking.chunk_records", return_value=["chunks"]),
            patch("retrieval.bm25.BM25Retriever") as bm25_class,
            patch("retrieval.semantic.SentenceTransformerEmbedder") as embedder_class,
        ):
            built = retrieval._build_retrievers("unused-model", Path("unused-corpus"), "bm25")

        self.assertEqual(len(built), 1)
        self.assertEqual(built[0][0], "bm25")
        self.assertFalse(built[0][2])
        bm25_class.assert_called_once_with(["chunks"])
        embedder_class.assert_not_called()

    def test_builder_maps_hybrid_reranker_method(self):
        with (
            patch("indexing.corpus.load_corpus", return_value=["corpus"]),
            patch("indexing.chunking.chunk_records", return_value=["chunks"]),
            patch("retrieval.semantic.SentenceTransformerEmbedder") as embedder_class,
            patch("retrieval.hybrid.HybridRetriever") as hybrid_class,
            patch("retrieval.rerank.rerank"),
        ):
            built = retrieval._build_retrievers(
                "configured-model", Path("unused-corpus"), "hybrid_reranker"
            )

        self.assertEqual(len(built), 1)
        self.assertEqual(built[0][0], "hybrid_reranker")
        self.assertTrue(built[0][2])
        embedder_class.assert_called_once_with("configured-model")
        hybrid_class.assert_called_once()

    def test_selected_method_is_recorded_in_output(self):
        raw = {
            "question_id": "approved",
            "question": "Question?",
            "answerability": "answerable",
            "gold_evidence": [{"record_id": "article-1", "required": True}],
            "expected_answer": "Answer",
            "review": {"status": "approved"},
        }
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "questions.jsonl"
            output = Path(directory) / "results.json"
            dataset.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            with patch.object(
                retrieval,
                "_build_retrievers",
                return_value=[("bm25", FakeRetriever(["article-1"]), False)],
            ) as build:
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = retrieval.main(
                        [
                            "--questions", str(dataset),
                            "--output", str(output),
                            "--method", "bm25",
                            "--k", "1",
                        ]
                    )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["selected_method"], "bm25")
        self.assertEqual(payload["results"][0]["method"], "bm25")
        self.assertEqual(build.call_args.args[2], "bm25")

    def test_single_required_gold_id(self):
        result = retrieval.evaluate(
            FakeRetriever(["article-1"]),
            [normalized("one", ["article-1"])],
            "fake",
            (1,),
        )
        metric = result["metrics_by_k"]["1"]
        self.assertEqual(metric["recall_macro_average"], 1.0)
        self.assertEqual(metric["any_gold_hit"], 1.0)
        self.assertIsNone(metric["strict_multi_evidence_success"])
        self.assertEqual(result["per_question"][0]["metrics"]["@1"]["recall"], 1.0)

    def test_partial_multiple_gold_retrieval(self):
        result = retrieval.evaluate(
            FakeRetriever(["article-1"]),
            [normalized("multi", ["article-1", "article-2"])],
            "fake",
            (1,),
        )
        metric = result["metrics_by_k"]["1"]
        self.assertEqual(metric["recall_macro_average"], 0.5)
        self.assertEqual(metric["strict_multi_evidence_success"], 0.0)
        self.assertEqual(metric["any_gold_hit"], 1.0)

    def test_complete_multiple_gold_retrieval(self):
        result = retrieval.evaluate(
            FakeRetriever(["article-1", "article-2"]),
            [normalized("multi", ["article-1", "article-2"])],
            "fake",
            (2,),
        )
        metric = result["metrics_by_k"]["2"]
        self.assertEqual(metric["recall_macro_average"], 1.0)
        self.assertEqual(metric["strict_multi_evidence_success"], 1.0)

    def test_duplicate_retrieved_records_count_once(self):
        result = retrieval.evaluate(
            FakeRetriever(["article-1", "article-1", "article-2"]),
            [normalized("multi", ["article-1", "article-2"])],
            "fake",
            (2, 3),
        )
        self.assertEqual(result["per_question"][0]["retrieved_unique_record_ids"], ["article-1", "article-2"])
        self.assertEqual(result["metrics_by_k"]["2"]["strict_multi_evidence_success"], 1.0)

    def test_unanswerable_is_counted_but_excluded_from_recall(self):
        class MustNotSearch:
            def search(self, *args, **kwargs):
                raise AssertionError("unanswerable question was sent to retrieval")

        result = retrieval.evaluate(
            MustNotSearch(),
            [normalized("unanswerable", [], answerability="unanswerable")],
            "fake",
            (1,),
        )
        self.assertEqual(result["question_counts"]["unanswerable_excluded_from_recall"], 1)
        metric = result["metrics_by_k"]["1"]
        self.assertIsNone(metric["recall_macro_average"])
        self.assertEqual(metric["recall_denominator_questions"], 0)

    def test_zero_approved_questions_reports_no_official_score(self):
        raw = {
            "question_id": "pending",
            "question": "Question?",
            "answerability": "answerable",
            "gold_evidence": [{"record_id": "article-1", "required": True}],
            "expected_answer": "Answer",
            "review": {"status": "awaiting_legal_review"},
        }
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "questions.jsonl"
            output = Path(directory) / "results.json"
            dataset.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = retrieval.main(["--questions", str(dataset), "--output", str(output)])
            payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(payload["official_score_available"])
        self.assertIsNone(payload["metrics"])
        self.assertFalse(output.exists())

    def test_malformed_input_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "bad.jsonl"
            dataset.write_text('{"question":\n', encoding="utf-8")
            with self.assertRaisesRegex(retrieval.DatasetError, "invalid JSON"):
                retrieval.load_questions(dataset)

            dataset.write_text(
                json.dumps(
                    {
                        "question_id": "bad",
                        "question": "Question?",
                        "answerability": "answerable",
                        "expected_answer": "Answer",
                        "gold_evidence": [],
                        "review": {"status": "approved"},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(retrieval.DatasetError, "no required gold evidence"):
                retrieval.load_questions(dataset)


if __name__ == "__main__":
    unittest.main()
