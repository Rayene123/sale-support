"""Metric tests: score maths, reliability statistics, and null-for-unrun.

The theme is honesty about missing data: a failed call, an unrun experiment, or
a label set that was never independently reviewed must read as ``null`` or as
reduced coverage, never as a good or zero result.
"""
import unittest

from harness.metrics import (agreement_stats, assemble, bias_summary, cohen_kappa, describe,
                             experiment_spend, human_agreement, judge_human_agreement,
                             labelled_coverage, performance_metrics, percentile, system_metrics)

SCORES_8 = {"factual_correctness": 2, "completeness": 2, "no_hallucination": 2,
            "relevance": 1, "professional_tone": 1, "total": 8}
SCORES_6 = {**SCORES_8, "completeness": 1, "total": 7}
SCORES_5 = {**SCORES_8, "factual_correctness": 1, "completeness": 0, "total": 5}


def item(item_id, category="refund", difficulty="easy"):
    return {"id": item_id, "split": "test", "category": category, "difficulty": difficulty}


def system_row(item_id, text="ok", status="ok", latency=100.0, tokens=(10, 5)):
    return {"item_id": item_id, "response_id": "run-1", "status": status, "response_text": text,
            "prompt_version": "v3", "latency_ms": latency,
            "tokens": {"prompt": tokens[0], "completion": tokens[1], "total": sum(tokens)},
            "warnings": [], "error": None}


def judge_row(item_id, scores=SCORES_8, response_id="run-1", latency=500.0):
    return {"item_id": item_id, "response_id": response_id, "status": "ok", "judged": True,
            "scores": scores, "reason": "fine", "judge_latency_ms": latency,
            "judge_usage": {"prompt": 100, "completion": 5, "total": 105}, "error": None}


def error_row(item_id, category="timeout", phase="system"):
    row = system_row(item_id, text=None, status="error", latency=None)
    row["error"] = {"category": category, "type": "SystemError", "message": "boom", "metadata": {}}
    return row


class BasicsTests(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(percentile([], 0.5), None)
        self.assertEqual(percentile([7.0], 0.95), 7.0)
        self.assertEqual(percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 0.95), 3.85)

    def test_describe_is_all_null_without_data(self):
        empty = describe([])
        self.assertEqual(empty["count"], 0)
        self.assertIsNone(empty["mean"])
        self.assertIsNone(empty["p95"])
        stats = describe([100.0, 200.0, 300.0])
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["mean"], 200.0)
        self.assertEqual(stats["median"], 200.0)
        self.assertEqual(stats["max"], 300.0)

    def test_kappa_is_none_when_there_is_nothing_to_measure(self):
        self.assertIsNone(cohen_kappa([], []))
        # One distinct rating: chance agreement is undefined, so kappa is null.
        self.assertIsNone(cohen_kappa([8, 8, 8], [8, 8, 8]))
        self.assertAlmostEqual(cohen_kappa([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertLess(cohen_kappa([8, 8, 8, 7, 7, 7], [7, 7, 7, 8, 8, 8]), 0.0)
        # Weighting changes the answer: unweighted counts only exact agreement,
        # so a 4-point miss costs the same as a 1-point miss, while the weighted
        # forms scale with distance and read as worse.
        wide_a = [4, 4, 6, 6, 8, 8]
        wide_b = [8, 8, 6, 6, 4, 4]
        self.assertAlmostEqual(cohen_kappa(wide_a, wide_b), 0.0)
        self.assertAlmostEqual(cohen_kappa(wide_a, wide_b, "linear"), -0.5)
        self.assertAlmostEqual(cohen_kappa(wide_a, wide_b, "quadratic"), -1.0)


class SystemMetricTests(unittest.TestCase):
    def test_average_ignores_failed_items_and_reports_coverage(self):
        items = [item("T-001"), item("T-002"), item("T-003")]
        rows = [system_row("T-001"), system_row("T-002"), error_row("T-003")]
        judged = [judge_row("T-001"), judge_row("T-002", SCORES_6)]
        metrics = system_metrics(items, rows, judged)
        self.assertEqual(metrics["system_successful"], 2)
        self.assertEqual(metrics["system_failed"], 1)
        self.assertEqual(metrics["judge_successful"], 2)
        self.assertAlmostEqual(metrics["quality"]["average_total_out_of_8"], 7.5)
        self.assertAlmostEqual(metrics["coverage_percent"], 200 / 3)
        self.assertEqual(metrics["failures_by_category"]["timeout"], 1)
        self.assertEqual(metrics["failed_items"][0]["item_id"], "T-003")
        self.assertEqual(metrics["quality"]["full_marks_items"], 1)
        self.assertEqual(metrics["quality"]["score_distribution"]["7"], 1)
        self.assertEqual(metrics["quality"]["score_distribution"]["6"], 0)

    def test_no_grades_means_null_average_and_zero_coverage(self):
        metrics = system_metrics([item("T-001")], [system_row("T-001")], [])
        self.assertIsNone(metrics["quality"]["average_total_out_of_8"])
        # Coverage is a measured ratio, so 0 graded of 1 selected is 0.0, not null.
        self.assertEqual(metrics["coverage_percent"], 0.0)
        self.assertEqual(metrics["judge_successful"], 0)
        self.assertEqual(metrics["quality"]["score_distribution"]["8"], 0)

    def test_breaks_down_by_category_and_difficulty(self):
        items = [item("T-001", "refund", "easy"), item("T-002", "refund", "hard"),
                 item("T-003", "shipping", "easy")]
        rows = [system_row(name) for name in ("T-001", "T-002", "T-003")]
        judged = [judge_row("T-001"), judge_row("T-002", SCORES_6), judge_row("T-003")]
        metrics = system_metrics(items, rows, judged)
        self.assertEqual(metrics["by_category"]["refund"]["items"], 2)
        self.assertAlmostEqual(metrics["by_category"]["refund"]["average_total_out_of_8"], 7.5)
        self.assertEqual(metrics["by_difficulty"]["hard"]["items"], 1)
        self.assertEqual(metrics["lowest_scored_items"][0]["item_id"], "T-002")

    def test_response_warnings_are_counted(self):
        rows = [system_row("T-001"), {**system_row("T-002"), "warnings": ["mojibake"]}]
        metrics = system_metrics([item("T-001"), item("T-002")], rows, [])
        self.assertEqual(metrics["response_warnings"], {"mojibake": 1})


class ReliabilityTests(unittest.TestCase):
    def labels(self):
        return {("T-001", "reference_answer"): [
            {"evaluator_id": "1", "scores": SCORES_8, "explanation": "ok"},
            {"evaluator_id": "2", "scores": SCORES_8, "explanation": "ok"}],
            ("T-002", "reference_answer"): [
                {"evaluator_id": "1", "scores": SCORES_6, "explanation": "thin"},
                {"evaluator_id": "2", "scores": SCORES_8, "explanation": "fine"}]}

    def test_human_agreement_reports_rate_and_kappa(self):
        stats = human_agreement(self.labels())["total"]
        self.assertEqual(stats["comparisons"], 2)
        self.assertEqual(stats["agreement_percent"], 50.0)
        self.assertEqual(stats["within_one_percent"], 100.0)
        self.assertEqual(stats["mean_absolute_difference"], 0.5)
        self.assertIsNotNone(stats["cohens_kappa_linear"])

    def test_judge_versus_human_lists_major_disagreements(self):
        judged = [judge_row("T-001", SCORES_8, response_id="reference_answer"),
                  judge_row("T-002", SCORES_5, response_id="reference_answer")]
        report = judge_human_agreement(judged, self.labels(), "reference_answer")
        self.assertEqual(report["comparisons"], 4)
        self.assertEqual(report["major_disagreement_threshold"], 2)
        self.assertEqual(report["major_disagreement_count"], 2)
        self.assertEqual(report["major_disagreement_percent"], 50.0)
        self.assertEqual(report["major_disagreements"][0]["item_id"], "T-002")
        self.assertEqual({row["evaluator_id"] for row in report["major_disagreements"]}, {"1", "2"})
        self.assertEqual(set(report["by_evaluator"]), {"1", "2"})

    def test_judge_versus_human_is_null_when_nothing_overlaps(self):
        report = judge_human_agreement([judge_row("T-001")], self.labels(), "reference_answer")
        self.assertEqual(report["comparisons"], 0)
        self.assertIsNone(report["major_disagreement_percent"])

    def test_seeded_labels_are_marked_unverified(self):
        judged = [judge_row("T-001", response_id="reference_answer")]
        coverage = labelled_coverage(judged, self.labels(), "reference_answer")
        self.assertEqual(coverage["label_status"], "seeded_unverified")
        self.assertEqual(coverage["replies_with_human_labels"], 1)
        self.assertEqual(coverage["unlabelled_replies"], 0)
        attested = labelled_coverage(judged, self.labels(), "reference_answer", labels_reviewed=True)
        self.assertEqual(attested["label_status"], "independently_reviewed_attested")

    def test_bias_summary_states_when_it_did_not_run(self):
        unrun = bias_summary(0, 0, 0)
        self.assertEqual(unrun["state"], "not_run")
        self.assertIsNone(unrun["changed"])
        self.assertIsNone(unrun["changed_percent"])
        self.assertNotIn("average_score_change", unrun)
        self.assertEqual(bias_summary(5, 0, 0)["state"], "no_valid_comparisons")
        measured = bias_summary(4, 4, 1)
        self.assertEqual(measured["state"], "measured")
        self.assertEqual(measured["changed_percent"], 25.0)
        deltas = bias_summary(2, 2, 1, [1, -1])
        self.assertEqual(deltas["average_score_change"], 0.0)
        self.assertEqual(deltas["max_score_change"], 1)
        self.assertIsNone(bias_summary(2, 0, 0, [])["average_score_change"])


class PerformanceTests(unittest.TestCase):
    def test_latency_and_tokens_only_count_successful_rows(self):
        rows = [system_row("T-001", latency=100.0), system_row("T-002", latency=300.0),
                error_row("T-003")]
        judged = [judge_row("T-001", latency=500.0), {**judge_row("T-002"), "status": "error"}]
        metrics = performance_metrics(rows, judged, wall_clock_seconds=60.0)
        self.assertEqual(metrics["system_latency_ms"]["count"], 2)
        self.assertEqual(metrics["system_latency_ms"]["mean"], 200.0)
        self.assertEqual(metrics["judge_latency_ms"]["count"], 1)
        self.assertEqual(metrics["system_tokens"]["total"], 30)
        self.assertEqual(metrics["system_tokens"]["items_with_usage"], 2)
        self.assertEqual(metrics["requests"], {"system": 3, "judge": 2,
                                               "experiment_judge_calls": None})
        self.assertEqual(metrics["throughput_items_per_minute"], 3.0)
        self.assertEqual(metrics["sequential_model_calls"], 5)

    def test_missing_latency_and_throughput_stay_null(self):
        metrics = performance_metrics([error_row("T-001")], [], wall_clock_seconds=None)
        self.assertIsNone(metrics["system_latency_ms"]["mean"])
        self.assertIsNone(metrics["judge_latency_ms"]["mean"])
        self.assertIsNone(metrics["throughput_items_per_minute"])
        self.assertIsNone(metrics["wall_clock_seconds"])
        self.assertIsNone(metrics["experiments"])

    def test_experiment_spend_is_separate_and_null_when_unrun(self):
        calls = [{"usage": {"prompt": 10, "completion": 2, "total": 12}, "latency_ms": 100.0},
                 {"usage": {"prompt": 20, "completion": 3, "total": 23}, "latency_ms": 200.0},
                 {"usage": None, "latency_ms": 300.0}]
        spend = experiment_spend(calls)
        self.assertEqual(spend["judge_calls"], 3)
        self.assertEqual(spend["judge_tokens"]["total"], 35)
        self.assertEqual(spend["judge_tokens"]["items_with_usage"], 2)
        self.assertEqual(spend["judge_latency_ms"]["mean"], 200.0)
        self.assertIsNone(experiment_spend([]))
        self.assertIsNone(experiment_spend(None))
        metrics = performance_metrics([], [], 10.0, experiment_spend(calls))
        self.assertEqual(metrics["requests"]["experiment_judge_calls"], 3)
        self.assertEqual(metrics["sequential_model_calls"], 3)


class AssembleTests(unittest.TestCase):
    def test_document_shape_is_stable_when_nothing_ran(self):
        document = assemble([item("T-001")], [], [])
        self.assertEqual(sorted(document), ["errors", "performance", "reliability", "system"])
        self.assertIsNone(document["system"]["quality"]["average_total_out_of_8"])
        self.assertEqual(document["reliability"]["position_bias"]["state"], "not_run")
        self.assertEqual(document["reliability"]["verbosity_bias"]["state"], "not_run")
        self.assertIsNone(document["reliability"]["human_agreement"])
        self.assertIsNone(document["reliability"]["judge_vs_human"])
        self.assertEqual(document["reliability"]["label_status"], "seeded_unverified")
        self.assertEqual(document["errors"]["categories"][0], "configuration")
        self.assertEqual(set(document["errors"]["system"]["counts"]),
                         set(document["errors"]["categories"]))
        self.assertEqual(sum(document["errors"]["system"]["counts"].values()), 0)

    def test_agreement_with_no_pairs_is_null(self):
        stats = agreement_stats([])
        self.assertEqual(stats["total"]["comparisons"], 0)
        self.assertIsNone(stats["total"]["agreement_percent"])
        self.assertIsNone(stats["total"]["cohens_kappa"])


if __name__ == "__main__":
    unittest.main()
