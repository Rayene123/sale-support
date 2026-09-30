"""Metrics for the evaluation harness.

Three groups are produced, matching the harness specification:

* **system** – average score, distribution, per-criterion averages, per-category
  and per-difficulty breakdowns, and the list of failed items,
* **reliability** – human-vs-human agreement, judge-vs-human agreement, major
  disagreements, and the position / verbosity bias experiments,
* **performance** – latency, wall-clock time, token usage, throughput, and
  failures counted by category.

Conventions that keep the numbers honest:

* failed calls are never averaged in as good results; coverage is reported,
* an experiment that was not run is ``null``, never ``0``,
* kappa is reported alongside raw agreement because a high agreement rate on a
  skewed distribution can hide a useless judge.
"""
import statistics
from collections import Counter, defaultdict
from itertools import combinations

from judge.client import LIMITS

from .errors import CATEGORIES, empty_counts

CRITERIA = tuple(LIMITS)
FIELDS = CRITERIA + ("total",)
MAXIMA = {**LIMITS, "total": 8}
MAJOR_DISAGREEMENT_THRESHOLD = 2
SEVERITY_NOTE = ("Scores are model-assigned unless independent human review is "
                 "attested; they are not a substitute for it.")


# --------------------------------------------------------------------- basics
def percentile(values, fraction):
    """Linear-interpolation percentile (p50/p95), matching the judge's reports."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def describe(values):
    """Count/mean/median/p95/min/max, or all ``None`` when there is no data."""
    numbers = [value for value in values if isinstance(value, (int, float))]
    if not numbers:
        return {"count": 0, "mean": None, "median": None, "p95": None,
                "min": None, "max": None, "stdev": None}
    return {
        "count": len(numbers),
        "mean": sum(numbers) / len(numbers),
        "median": statistics.median(numbers),
        "p95": percentile(numbers, 0.95),
        "min": min(numbers),
        "max": max(numbers),
        "stdev": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
    }


def score_distribution(totals):
    """Counts for every possible total, so absent scores stay visible as zero."""
    counter = Counter(totals)
    return {str(value): counter.get(value, 0) for value in range(MAXIMA["total"] + 1)}


# ---------------------------------------------------------------- statistics
def cohen_kappa(first, second, weight="none"):
    """Cohen's kappa for paired integer ratings.

    ``weight`` is ``"none"``, ``"linear"`` or ``"quadratic"``. Totals are
    ordinal, so the weighted forms are reported next to the raw agreement rate.
    """
    if not first or len(first) != len(second):
        return None
    categories = sorted(set(first) | set(second))
    count = len(first)
    if categories[-1] == categories[0]:
        # Only one distinct rating: chance agreement cannot be estimated, so
        # kappa is undefined. Reporting 0.0 would read as "no agreement" when
        # the raters actually agreed on every pair.
        return None
    observed = {}
    for left, right in zip(first, second):
        observed[(left, right)] = observed.get((left, right), 0) + 1
    left_marginal = Counter(first)
    right_marginal = Counter(second)

    def cost(left, right):
        span = categories[-1] - categories[0]
        if weight == "none":
            return 0.0 if left == right else 1.0
        distance = abs(left - right) / span
        return distance if weight == "linear" else distance ** 2

    observed_disagreement = sum(cost(left, right) * count_
                                for (left, right), count_ in observed.items()) / count
    expected_disagreement = sum(cost(left, right) * left_marginal[left] * right_marginal[right]
                                for left in categories for right in categories) / (count ** 2)
    if expected_disagreement == 0:
        return None
    # Standard weighted form: kappa = 1 - observed / expected. With unweighted
    # 0/1 costs this reduces to the usual (po - pe) / (1 - pe).
    return 1 - observed_disagreement / expected_disagreement


def agreement_stats(pairs):
    """Agreement statistics for a list of ``(scores_a, scores_b)`` pairs."""
    report = {}
    for field in FIELDS:
        differences = [abs(left[field] - right[field]) for left, right in pairs]
        if not differences:
            report[field] = {"comparisons": 0, "agreements": 0, "disagreements": 0,
                             "agreement_percent": None, "within_one_percent": None,
                             "mean_absolute_difference": None, "cohens_kappa": None,
                             "cohens_kappa_linear": None}
            continue
        count = len(differences)
        exact = sum(1 for value in differences if value == 0)
        left = [pair[0][field] for pair in pairs]
        right = [pair[1][field] for pair in pairs]
        report[field] = {
            "comparisons": count,
            "agreements": exact,
            "disagreements": count - exact,
            "agreement_percent": 100 * exact / count,
            "within_one_percent": 100 * sum(1 for value in differences if value <= 1) / count,
            "mean_absolute_difference": sum(differences) / count,
            "cohens_kappa": cohen_kappa(left, right),
            "cohens_kappa_linear": cohen_kappa(left, right, "linear"),
        }
    return report


def bias_summary(attempted, valid, changed, deltas=None, note=""):
    """Bias statistics that stay ``null`` when the experiment was not run."""
    if not attempted:
        state = "not_run"
    elif not valid:
        state = "no_valid_comparisons"
    else:
        state = "measured"
    summary = {
        "state": state,
        "attempted": attempted,
        "valid_comparisons": valid,
        "changed": changed if valid else None,
        "changed_percent": (100 * changed / valid) if valid else None,
    }
    if deltas is not None:
        summary["average_score_change"] = (sum(deltas) / len(deltas)) if deltas else None
        summary["max_score_change"] = max((abs(value) for value in deltas), default=None)
    if note:
        summary["note"] = note
    return summary


# ------------------------------------------------------------------- system
def system_metrics(items, system_rows, judge_rows, response_id=None):
    """Scores, coverage, breakdowns, and the failures that caused them."""
    index = {item["id"]: item for item in items}
    judged = {row["item_id"]: row for row in judge_rows
              if row.get("item_id") and (response_id is None or row.get("response_id") == response_id)}
    graded = [row for row in judged.values() if row.get("status") == "ok" and row.get("scores")]
    scores = [row["scores"] for row in graded]
    system_ok = [row for row in system_rows if row.get("status") == "ok"]
    system_failed = [row for row in system_rows if row.get("status") != "ok"]

    by_category, by_difficulty = defaultdict(list), defaultdict(list)
    for row in graded:
        item = index.get(row["item_id"], {})
        by_category[item.get("category", "unknown")].append(row["scores"]["total"])
        by_difficulty[item.get("difficulty", "unknown")].append(row["scores"]["total"])

    low_scores = sorted(
        ({"item_id": row["item_id"], "category": index.get(row["item_id"], {}).get("category"),
          "total": row["scores"]["total"], "scores": row["scores"],
          "reason": row.get("reason")} for row in graded if row["scores"]["total"] < MAXIMA["total"]),
        key=lambda entry: (entry["total"], entry["item_id"]))

    weaknesses = {}
    for criterion, maximum in LIMITS.items():
        awarded = [score[criterion] for score in scores]
        lost = [row["item_id"] for row in graded if row["scores"][criterion] < maximum]
        weaknesses[criterion] = {
            "maximum": maximum,
            "average": (sum(awarded) / len(awarded)) if awarded else None,
            "points_lost": sum(maximum - value for value in awarded),
            "items_not_full_marks": len(lost),
            "items": lost[:20],
        }

    failures = Counter()
    for row in system_failed:
        failures[(row.get("error") or {}).get("category", "internal")] += 1
    for row in judge_rows:
        if row.get("status") != "ok":
            failures[("judge:" + ((row.get("error") or {}).get("category", "internal")))] += 1

    warnings = Counter()
    for row in system_rows:
        for warning in row.get("warnings") or []:
            warnings[warning] += 1

    return {
        "dataset_items": len(items),
        "system_attempted": len(system_rows),
        "system_successful": len(system_ok),
        "system_failed": len(system_failed),
        "judge_attempted": len(judged),
        "judge_successful": len(graded),
        "judge_failed": len(judged) - len(graded),
        "coverage_percent": (100 * len(graded) / len(items)) if items else None,
        "quality": {
            "average_total_out_of_8": (sum(score["total"] for score in scores) / len(scores)) if scores else None,
            "average_by_criterion": {criterion: (sum(score[criterion] for score in scores) / len(scores))
                                     if scores else None for criterion in CRITERIA},
            "score_distribution": score_distribution([score["total"] for score in scores]),
            "full_marks_items": sum(1 for score in scores if score["total"] == MAXIMA["total"]),
            "items_below_full_marks": sum(1 for score in scores if score["total"] < MAXIMA["total"]),
            "note": SEVERITY_NOTE,
        },
        "by_category": {name: {"items": len(values), "average_total_out_of_8": sum(values) / len(values)}
                        for name, values in sorted(by_category.items())},
        "by_difficulty": {name: {"items": len(values), "average_total_out_of_8": sum(values) / len(values)}
                          for name, values in sorted(by_difficulty.items())},
        "criterion_weaknesses": weaknesses,
        "lowest_scored_items": low_scores[:15],
        "failed_items": [{"item_id": row["item_id"], "category": (row.get("error") or {}).get("category"),
                          "message": (row.get("error") or {}).get("message")}
                         for row in system_failed],
        "failures_by_category": {name: failures.get(name, 0) for name in sorted(failures)},
        "response_warnings": dict(warnings),
        "judge_total_corrections": sum(1 for row in graded if row.get("judge_total_corrected")),
    }


# --------------------------------------------------------------- reliability
def human_agreement(labels):
    """Agreement between the two human evaluators, per labelled reply."""
    pairs = []
    for group in labels.values():
        for left, right in combinations(group, 2):
            pairs.append((left["scores"], right["scores"]))
    return agreement_stats(pairs)


def judge_human_agreement(judge_rows, labels, response_id=None):
    """Judge-versus-human agreement, reported separately for each evaluator."""
    per_evaluator = defaultdict(list)
    major = []
    compared = 0
    for row in judge_rows:
        if row.get("status") != "ok" or not row.get("scores"):
            continue
        if response_id and row.get("response_id") != response_id:
            continue
        key = (row["item_id"], row.get("response_id"))
        for label in labels.get(key, []):
            per_evaluator[label["evaluator_id"]].append((label["scores"], row["scores"]))
            compared += 1
            if abs(row["scores"]["total"] - label["scores"]["total"]) >= MAJOR_DISAGREEMENT_THRESHOLD:
                major.append({
                    "item_id": key[0], "response_id": key[1], "evaluator_id": label["evaluator_id"],
                    "human_total": label["scores"]["total"], "judge_total": row["scores"]["total"],
                    "human_scores": label["scores"], "judge_scores": row["scores"],
                    "judge_reason": row.get("reason"), "human_reason": label.get("explanation"),
                })
    stats = {evaluator: agreement_stats(pairs) for evaluator, pairs in per_evaluator.items()}
    return {
        "by_evaluator": stats,
        "comparisons": compared,
        "major_disagreement_threshold": MAJOR_DISAGREEMENT_THRESHOLD,
        "major_disagreement_count": len(major),
        "major_disagreement_percent": (100 * len(major) / compared) if compared else None,
        "major_disagreements": sorted(major, key=lambda entry: -abs(entry["judge_total"] - entry["human_total"]))[:20],
    }


def labelled_coverage(judge_rows, labels, response_id=None, labels_reviewed=False):
    matched = sum(1 for row in judge_rows
                  if (row["item_id"], row.get("response_id")) in labels
                  and (response_id is None or row.get("response_id") == response_id))
    graded = sum(1 for row in judge_rows
                 if row.get("status") == "ok" and (response_id is None or row.get("response_id") == response_id))
    return {
        "graded_replies": graded,
        "replies_with_human_labels": matched,
        "unlabelled_replies": graded - matched,
        "label_status": ("independently_reviewed_attested" if labels_reviewed else "seeded_unverified"),
        "note": ("Seeded labels are not independent human review; agreement against them is "
                 "a smoke check, not a validated judge-reliability result."),
    }


# --------------------------------------------------------------- performance
def experiment_spend(entries):
    """Judge calls, tokens, and latency spent on the bias experiments.

    ``entries`` are the ``extra_calls`` records saved in ``position.jsonl`` and
    ``verbosity.jsonl``. Returns ``None`` when no experiment call was made, so
    an unrun experiment reports ``null`` rather than a misleading zero.
    """
    calls = [entry for entry in (entries or []) if isinstance(entry, dict)]
    if not calls:
        return None
    latencies = [entry["latency_ms"] for entry in calls if isinstance(entry.get("latency_ms"), (int, float))]
    return {
        "judge_calls": len(calls),
        "judge_tokens": _token_totals(entry.get("usage") for entry in calls),
        "judge_latency_ms": describe(latencies),
        "note": ("Extra judge calls made only by the bias experiments. The system and judge "
                 "phases above do not include them, so add these figures to the run total."),
    }


def performance_metrics(system_rows, judge_rows, wall_clock_seconds=None, experiments=None):
    """Latency, tokens, and throughput for the system and the judge."""
    system_latency = [row["latency_ms"] for row in system_rows
                      if row.get("status") == "ok" and isinstance(row.get("latency_ms"), (int, float))]
    judge_latency = [row["judge_latency_ms"] for row in judge_rows
                     if row.get("status") == "ok" and isinstance(row.get("judge_latency_ms"), (int, float))]
    system_tokens = _token_totals(row.get("tokens") for row in system_rows if row.get("status") == "ok")
    judge_tokens = _token_totals(row.get("judge_usage") for row in judge_rows if row.get("status") == "ok")
    attempted = len(system_rows) or 1
    experiment_calls = (experiments or {}).get("judge_calls")
    return {
        "wall_clock_seconds": wall_clock_seconds,
        "system_latency_ms": describe(system_latency),
        "judge_latency_ms": describe(judge_latency),
        "system_tokens": system_tokens,
        "judge_tokens": judge_tokens,
        "experiments": experiments,
        "requests": {"system": len(system_rows), "judge": len(judge_rows),
                     "experiment_judge_calls": experiment_calls},
        "throughput_items_per_minute": (60 * attempted / wall_clock_seconds) if wall_clock_seconds else None,
        "sequential_model_calls": len(system_rows) + len(judge_rows) + (experiment_calls or 0),
        "note": "Latency is per request, measured with time.perf_counter(). "
                "The harness runs sequentially, so wall-clock time is the sum of "
                "request latencies plus local processing.",
    }


def _token_totals(usages):
    totals = {"prompt": 0, "completion": 0, "total": 0, "items_with_usage": 0}
    for usage in usages:
        if not isinstance(usage, dict):
            continue
        prompt = usage.get("prompt")
        completion = usage.get("completion")
        if prompt is None and completion is None:
            continue
        totals["items_with_usage"] += 1
        totals["prompt"] += prompt or 0
        totals["completion"] += completion or 0
        totals["total"] += (usage.get("total") if usage.get("total") is not None
                            else (prompt or 0) + (completion or 0))
    return totals


def error_breakdown(rows, key="error"):
    """Failures counted by harness category, with an example message each."""
    counts, examples = empty_counts(), {}
    for row in rows:
        if row.get("status") == "ok":
            continue
        error = row.get(key) or {}
        category = error.get("category", "internal")
        counts[category] = counts.get(category, 0) + 1
        examples.setdefault(category, error.get("message", ""))
    return {"counts": counts, "examples": examples}


def assemble(items, system_rows, judge_rows, labels=None, labels_reviewed=False,
             response_id=None, position_bias=None, verbosity_bias=None,
             wall_clock_seconds=None, experiment_calls=None):
    """Build the full ``metrics.json`` document."""
    labels = labels or {}
    metrics = {
        "system": system_metrics(items, system_rows, judge_rows, response_id),
        "reliability": {
            "label_status": ("independently_reviewed_attested" if labels_reviewed else "seeded_unverified"),
            "human_agreement": human_agreement(labels) if labels else None,
            "judge_vs_human": judge_human_agreement(judge_rows, labels, response_id) if labels else None,
            "coverage": labelled_coverage(judge_rows, labels, response_id, labels_reviewed) if labels else None,
            "position_bias": position_bias or bias_summary(0, 0, 0, note="not run by this harness run"),
            "verbosity_bias": verbosity_bias or bias_summary(0, 0, 0, note="not run by this harness run"),
            "note": SEVERITY_NOTE,
        },
        "performance": performance_metrics(system_rows, judge_rows, wall_clock_seconds,
                                            experiment_spend(experiment_calls)),
        "errors": {
            "categories": list(CATEGORIES),
            "system": error_breakdown(system_rows),
            "judge": error_breakdown(judge_rows),
        },
    }
    return metrics
