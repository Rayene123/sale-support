"""Cost tests: an unpriced run must say so, never report zero.

Cost is only computed from tokens the provider actually reported and prices the
operator configured. Everything else is ``null`` with a reason attached.
"""
import unittest

from harness.config import JudgeConfig, PricingConfig, SystemConfig
from harness.cost import build_cost_report, local_inference_report, token_cost

GROQ_JUDGE = JudgeConfig(provider="groq", model="openai/gpt-oss-20b", api_key="not-a-real-key")
OLLAMA_SYSTEM = SystemConfig(provider="ollama", model="qwen2.5:14b")
GROQ_SYSTEM = SystemConfig(provider="openai", model="openai/gpt-oss-20b", api_key_env="KEY")


def metrics(system_tokens=None, judge_tokens=None, wall_clock=60.0, experiments=None):
    return {"performance": {"system_tokens": system_tokens, "judge_tokens": judge_tokens,
                            "wall_clock_seconds": wall_clock, "experiments": experiments}}


def tokens(prompt, completion):
    return {"prompt": prompt, "completion": completion, "total": prompt + completion,
            "items_with_usage": 1}


class TokenCostTests(unittest.TestCase):
    def test_price_must_be_known_for_both_directions(self):
        self.assertAlmostEqual(token_cost(1_000_000, 0, 2.0, 3.0), 2.0)
        self.assertAlmostEqual(token_cost(0, 1_000_000, 2.0, 3.0), 3.0)
        self.assertIsNone(token_cost(1_000_000, 0, None, 3.0))
        self.assertIsNone(token_cost(1_000_000, 0, 2.0, None))
        self.assertIsNone(token_cost(None, None, 2.0, 3.0))


class BuildCostReportTests(unittest.TestCase):
    def test_priced_run_reports_per_item_and_projection(self):
        report = build_cost_report(
            metrics(tokens(1000, 500), tokens(2000, 1000), wall_clock=100.0),
            PricingConfig(system_input_per_m=1.0, system_output_per_m=2.0,
                          judge_input_per_m=3.0, judge_output_per_m=4.0),
            10, GROQ_SYSTEM, GROQ_JUDGE)
        self.assertEqual(report["system"]["status"], "priced")
        self.assertAlmostEqual(report["system"]["total_usd"], 0.001 * 1 + 0.0005 * 2)
        self.assertEqual(report["judge"]["status"], "priced")
        self.assertAlmostEqual(report["judge"]["per_item_usd"], (0.002 * 3 + 0.001 * 4) / 10)
        self.assertAlmostEqual(report["combined"]["total_usd"],
                               report["system"]["total_usd"] + report["judge"]["total_usd"])
        self.assertAlmostEqual(report["volume_projection"]["combined_usd"],
                               report["combined"]["total_usd"] * 100)
        self.assertEqual(report["volume_projection"]["items"], 1000)
        self.assertEqual(report["currency"], "USD")

    def test_missing_prices_are_null_with_a_reason(self):
        report = build_cost_report(metrics(tokens(1000, 500), tokens(2000, 1000)),
                                   PricingConfig(), 10, GROQ_SYSTEM, GROQ_JUDGE)
        self.assertEqual(report["system"]["status"], "not_configured")
        self.assertIsNone(report["system"]["total_usd"])
        self.assertIsNone(report["system"]["per_item_usd"])
        self.assertIsNone(report["system"]["per_1000_requests_usd"])
        self.assertIn("SYSTEM_INPUT_PRICE_PER_M", report["system"]["reason"])
        self.assertIsNone(report["combined"]["total_usd"])
        self.assertIsNone(report["volume_projection"]["combined_usd"])
        self.assertEqual(report["experiments"]["status"], "not_run")

    def test_local_provider_is_reported_as_priceless_not_as_zero(self):
        report = build_cost_report(metrics(tokens(1000, 500), tokens(2000, 1000)),
                                   PricingConfig(), 10, OLLAMA_SYSTEM, GROQ_JUDGE)
        self.assertEqual(report["system"]["status"], "local_provider")
        self.assertIsNone(report["system"]["total_usd"])
        self.assertEqual(report["judge"]["status"], "not_configured")

    def test_no_usage_means_no_cost_even_with_prices(self):
        report = build_cost_report(
            metrics({"prompt": 0, "completion": 0, "total": 0, "items_with_usage": 0}, None),
            PricingConfig(judge_input_per_m=1.0, judge_output_per_m=1.0),
            5, GROQ_SYSTEM, GROQ_JUDGE)
        self.assertEqual(report["system"]["status"], "no_token_usage")
        self.assertIsNone(report["system"]["total_usd"])
        self.assertEqual(report["judge"]["status"], "no_token_usage")

    def test_experiment_calls_are_priced_separately_from_the_pass(self):
        experiments = {"judge_calls": 4, "judge_tokens": tokens(400, 200)}
        report = build_cost_report(
            metrics(tokens(1000, 500), tokens(2000, 1000), experiments=experiments),
            PricingConfig(judge_input_per_m=3.0, judge_output_per_m=4.0), 1, GROQ_SYSTEM, GROQ_JUDGE)
        self.assertEqual(report["basis"]["experiment_judge_calls"], 4)
        self.assertEqual(report["experiments"]["status"], "priced")
        self.assertAlmostEqual(report["experiments"]["per_item_usd"],
                               (0.0004 * 3 + 0.0002 * 4) / 4)
        self.assertAlmostEqual(report["run_total"]["total_usd"],
                               report["judge"]["total_usd"] + report["experiments"]["total_usd"])
        self.assertAlmostEqual(report["volume_projection"]["experiment_usd"],
                               report["experiments"]["total_usd"] * 100)
        self.assertTrue(any("run_total" in caveat for caveat in report["caveats"]))

    def test_replayed_run_reports_no_wall_clock_and_no_throughput(self):
        report = build_cost_report(
            metrics(tokens(1000, 500), tokens(2000, 1000), wall_clock=None),
            PricingConfig(), 10, OLLAMA_SYSTEM, GROQ_JUDGE)
        self.assertIsNone(report["basis"]["wall_clock_seconds"])
        self.assertEqual(report["local_inference"]["status"], "not_measured")


class LocalInferenceTests(unittest.TestCase):
    def test_estimate_needs_an_explicit_hourly_assumption(self):
        pricing = PricingConfig()
        self.assertEqual(local_inference_report(None, pricing, ["ollama"])["status"], "not_measured")
        unpriced = local_inference_report(3600.0, pricing, ["ollama"])
        self.assertEqual(unpriced["status"], "not_priced")
        self.assertIsNone(unpriced["estimated_compute_cost_usd"])
        priced = local_inference_report(3600.0, PricingConfig(local_cost_per_hour=0.5), ["ollama"])
        self.assertEqual(priced["status"], "estimated_from_assumption")
        self.assertAlmostEqual(priced["estimated_compute_cost_usd"], 0.5)
        self.assertIn("not a provider invoice", priced["note"])


if __name__ == "__main__":
    unittest.main()
