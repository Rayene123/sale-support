"""Cost analysis and volume projection.

Prices are operator-supplied (USD per 1,000,000 tokens) and read from
configuration, never guessed. When a price is missing the report says
``not_configured`` and returns ``null``: a missing price is not a zero cost.

Reported figures:

* total, per-item, and per-1,000-request cost for the system and the judge,
* the combined cost of one full evaluation pass,
* a 100x volume projection, which the specification requires,
* an explicitly optional local-inference estimate for Ollama runs.
"""
from .config import PricingConfig

DEFAULT_MULTIPLIER = 100


def token_cost(input_tokens, output_tokens, input_price, output_price):
    """USD for a token count, or ``None`` when a price or a count is missing.

    A provider that reported no token usage means "not measured", which is
    ``None``: reporting 0.0 would read as "this call was free".
    """
    if input_price is None or output_price is None:
        return None
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) / 1_000_000 * input_price + (output_tokens or 0) / 1_000_000 * output_price


def _unit_costs(total_cost, items):
    """Per-item and per-1,000-request figures, or ``None`` when cost is unknown."""
    if total_cost is None or not items:
        return {"total_usd": None, "per_item_usd": None, "per_1000_requests_usd": None}
    return {
        "total_usd": total_cost,
        "per_item_usd": total_cost / items,
        "per_1000_requests_usd": total_cost / items * 1000,
    }


def _phase_report(tokens, prices_configured, prices, items, status_if_missing, reason_if_missing):
    if not tokens or not tokens.get("items_with_usage"):
        return {"status": "no_token_usage", "items": items,
                "note": "The provider returned no token usage; no cost is computed.",
                **_unit_costs(None, items)}
    if not prices_configured:
        return {"status": status_if_missing, "items": items, "reason": reason_if_missing,
                "tokens": tokens, **_unit_costs(None, items)}
    total = token_cost(tokens.get("prompt"), tokens.get("completion"),
                       prices["input"], prices["output"])
    return {"status": "priced", "items": items, "tokens": tokens,
            "prices": prices, **_unit_costs(total, items)}


def local_inference_report(wall_clock_seconds, pricing, providers):
    """Optional, assumption-based estimate for runs that use a local model."""
    if not wall_clock_seconds:
        return {"status": "not_measured", "note": "No wall-clock time recorded for this run."}
    hours = wall_clock_seconds / 3600
    if pricing.local_cost_per_hour is None:
        return {
            "status": "not_priced",
            "wall_clock_seconds": wall_clock_seconds,
            "providers": providers,
            "estimated_compute_cost_usd": None,
            "note": ("Local inference has no API price. Set HARNESS_LOCAL_COST_PER_HOUR to an "
                     "electricity-and-depreciation estimate to obtain a local compute figure; "
                     "break-even analysis also needs hardware, capacity, and labour assumptions."),
        }
    return {
        "status": "estimated_from_assumption",
        "wall_clock_seconds": wall_clock_seconds,
        "providers": providers,
        "cost_per_hour_assumption_usd": pricing.local_cost_per_hour,
        "estimated_compute_cost_usd": hours * pricing.local_cost_per_hour,
        "note": "Assumption-based estimate, not a provider invoice.",
    }


def build_cost_report(metrics, pricing, items, system_config, judge_config,
                      wall_clock_seconds=None, multiplier=DEFAULT_MULTIPLIER):
    """Assemble ``cost.json`` for one run."""
    performance = metrics.get("performance", {})
    system_tokens = performance.get("system_tokens") or {}
    judge_tokens = performance.get("judge_tokens") or {}
    items = items or 1

    system_report = _phase_report(
        system_tokens, pricing.system_configured() and system_config.priced,
        {"input": pricing.system_input_per_m, "output": pricing.system_output_per_m},
        items,
        status_if_missing="not_configured",
        reason_if_missing=("Set SYSTEM_INPUT_PRICE_PER_M and SYSTEM_OUTPUT_PRICE_PER_M to the "
                           "provider's current USD-per-million-token prices."))
    if system_config.provider == "ollama" and system_report["status"] == "not_configured":
        system_report["status"] = "local_provider"
        system_report["reason"] = "The evaluated system runs on a local provider; there is no API price."

    judge_report = _phase_report(
        judge_tokens, pricing.judge_configured() and judge_config.provider == "groq",
        {"input": pricing.judge_input_per_m, "output": pricing.judge_output_per_m},
        items,
        status_if_missing="not_configured",
        reason_if_missing=("Set JUDGE_INPUT_PRICE_PER_M and JUDGE_OUTPUT_PRICE_PER_M when the judge "
                           "runs on a hosted provider."))
    if judge_config.provider == "ollama" and judge_report["status"] == "not_configured":
        judge_report["status"] = "local_provider"
        judge_report["reason"] = "The judge runs on local Ollama; there is no API price."

    experiments = performance.get("experiments") or {}
    experiment_tokens = experiments.get("judge_tokens") or {}
    experiment_calls = experiments.get("judge_calls")
    experiment_report = _phase_report(
        experiment_tokens, pricing.judge_configured() and judge_config.provider == "groq",
        {"input": pricing.judge_input_per_m, "output": pricing.judge_output_per_m},
        experiment_calls or 0,
        status_if_missing="not_configured",
        reason_if_missing=("Set JUDGE_INPUT_PRICE_PER_M and JUDGE_OUTPUT_PRICE_PER_M to price the "
                           "experiment calls on a hosted judge."))
    if experiment_report["status"] == "no_token_usage":
        experiment_report["status"] = "not_run"
        experiment_report["note"] = ("No bias experiment ran in this run, so there were no extra "
                                    "judge calls to price.")

    combined_total = None
    if system_report.get("total_usd") is not None or judge_report.get("total_usd") is not None:
        combined_total = (system_report.get("total_usd") or 0) + (judge_report.get("total_usd") or 0)
    run_total = combined_total
    if experiment_report.get("total_usd") is not None:
        run_total = (run_total or 0) + experiment_report["total_usd"]

    providers = sorted({name for name, present in
                        (("system", system_config.provider), ("judge", judge_config.provider)) if present})
    return {
        "currency": pricing.currency,
        "prices": pricing.to_record(),
        "basis": {
            "items_evaluated": items,
            "system_tokens": system_tokens,
            "judge_tokens": judge_tokens,
            "experiment_judge_calls": experiment_calls,
            "experiment_judge_tokens": experiment_tokens,
            "wall_clock_seconds": wall_clock_seconds,
            "tokens_are_provider_reported": True,
        },
        "system": system_report,
        "judge": judge_report,
        "experiments": experiment_report,
        "combined": {
            "status": "priced" if combined_total is not None else "not_configured",
            "note": "One full evaluation pass: the system call and the judge call per item, "
                    "without the optional bias experiments.",
            **_unit_costs(combined_total, items),
        },
        "run_total": {
            "status": "priced" if run_total is not None else "not_configured",
            "note": "Everything this run actually called, including bias-experiment judge calls.",
            **_unit_costs(run_total, items),
        },
        "local_inference": local_inference_report(wall_clock_seconds, pricing, providers),
        "volume_projection": {
            "multiplier": multiplier,
            "items": items * multiplier,
            "system_usd": (system_report.get("total_usd") or 0) * multiplier
            if system_report.get("total_usd") is not None else None,
            "judge_usd": (judge_report.get("total_usd") or 0) * multiplier
            if judge_report.get("total_usd") is not None else None,
            "combined_usd": combined_total * multiplier if combined_total is not None else None,
            "experiment_usd": experiment_report.get("total_usd") * multiplier
            if experiment_report.get("total_usd") is not None else None,
            "note": ("Linear projection at %dx the measured volume, assuming the same item mix, "
                     "the same token usage, and unchanged prices. It excludes engineering "
                     "time, storage, and any provider tier or caching rules." % multiplier),
        },
        "caveats": [
            "Prices are operator estimates in USD per million tokens; verify them.",
            "Token usage is what the provider reported; missing usage is reported, not estimated.",
            "Replayed runs reuse the original run's latency and usage, so their cost is the "
            "cost of that original run, not of the report.",
            "Bias experiments are optional extras; read run_total, not combined, for what a run "
            "with experiments actually cost.",
        ],
    }


__all__ = ["build_cost_report", "token_cost", "DEFAULT_MULTIPLIER", "PricingConfig"]
