"""Human-readable run report (``report.md``).

The JSON artefacts are the source of truth; this file only formats them so the
team can read a run during the demo without opening five JSON documents.
"""
from .metrics import CRITERIA, MAXIMA


def _table(headers, rows):
    if not rows:
        return "_no data_\n"
    widths = [max(len(str(headers[index])), *(len(str(row[index])) for row in rows))
              for index in range(len(headers))]
    def line(cells):
        return "| " + " | ".join(str(cells[index]).ljust(widths[index])
                                 for index in range(len(headers))) + " |"
    separator = "|" + "|".join("-" * (width + 2) for width in widths) + "|"
    return "\n".join([line(headers), separator] + [line(row) for row in rows]) + "\n"


def _number(value, digits=2, suffix=""):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def _percent(value):
    return "not run" if value is None else f"{value:.1f}%"


def build_report(metadata, metrics, cost, command):
    system = metrics.get("system", {})
    quality = system.get("quality", {})
    reliability = metrics.get("reliability", {})
    performance = metrics.get("performance", {})
    lines = []
    add = lines.append

    add(f"# Evaluation run `{metadata.get('run_id')}`\n")
    add(f"- mode: `{metadata.get('mode')}`")
    add(f"- created: {metadata.get('created_utc')}")
    add(f"- dataset: `{metadata.get('dataset', {}).get('source')}` "
        f"(sha256 `{str(metadata.get('dataset', {}).get('sha256'))[:12]}`)")
    add(f"- items: {system.get('dataset_items')} | system ok: {system.get('system_successful')} "
        f"| failed: {system.get('system_failed')} | judged ok: {system.get('judge_successful')}")
    prompt = (metadata.get("prompts") or [{}])[0]
    add(f"- system prompt: `{prompt.get('version')}` "
        f"(sha256 `{str(prompt.get('sha256'))[:12]}`) | model: "
        f"`{metadata.get('configuration', {}).get('system', {}).get('model')}`")
    judge = metadata.get("judge", {})
    add(f"- judge: `{judge.get('model')}` prompt `{judge.get('prompt_version')}` "
        f"(sha256 `{str(judge.get('prompt_sha256'))[:12]}`)")
    add(f"- label status: `{reliability.get('label_status')}`\n")

    run_block = metrics.get("run") or {}
    if run_block.get("notes"):
        add("## What this run does and does not prove\n")
        for note in run_block["notes"]:
            add(f"- {note}")
        add("")

    add("## Reproduce\n")
    add("```powershell\n" + command + "\n```\n")
    add("```text\npython -m harness run --run-id <new-id> --output results/harness/<new-id> ...\n```\n")

    add("## Quality\n")
    add(f"- average total: **{_number(quality.get('average_total_out_of_8'))} / 8**")
    add(f"- items with full marks: {quality.get('full_marks_items')} of {system.get('judge_successful')}")
    add(f"- items below full marks: {quality.get('items_below_full_marks')}")
    add(f"- coverage: {_percent(system.get('coverage_percent'))}\n")
    add("Score distribution:\n")
    distribution = quality.get("score_distribution") or {}
    add(_table(["total", *[str(value) for value in range(9)]],
               [["items", *[distribution.get(str(value), 0) for value in range(9)]]]))
    add("Average by criterion:\n")
    averages = quality.get("average_by_criterion") or {}
    add(_table(["criterion", "average", "maximum"],
               [[criterion, _number(averages.get(criterion)), MAXIMA[criterion]] for criterion in CRITERIA]))
    add("Weakest criteria (points lost across graded items):\n")
    weaknesses = system.get("criterion_weaknesses") or {}
    add(_table(["criterion", "average", "points lost", "items not full marks"],
               [[criterion, _number(value.get("average")), value.get("points_lost"),
                 value.get("items_not_full_marks")] for criterion, value in weaknesses.items()]))

    add("## By scenario category\n")
    add(_table(["category", "items", "average /8"],
               [[name, value.get("items"), _number(value.get("average_total_out_of_8"))]
                for name, value in (system.get("by_category") or {}).items()]))
    add("## By difficulty\n")
    add(_table(["difficulty", "items", "average /8"],
               [[name, value.get("items"), _number(value.get("average_total_out_of_8"))]
                for name, value in (system.get("by_difficulty") or {}).items()]))

    add("## Lowest scored items\n")
    add("_Only items below full marks are listed._\n")
    add(_table(["item", "category", "total", "judge reason"],
               [[row.get("item_id"), row.get("category"), row.get("total"),
                 (row.get("reason") or "")[:110]] for row in system.get("lowest_scored_items") or []]))

    add("## Failures\n")
    counts = ((metrics.get("errors") or {}).get("system") or {}).get("counts") or {}
    judge_counts = ((metrics.get("errors") or {}).get("judge") or {}).get("counts") or {}
    failures = {name: value for name, value in counts.items() if value}
    failures.update({f"judge:{name}": value for name, value in judge_counts.items() if value})
    add(_table(["phase", "category", "count"],
               [["system" if ":" not in name else name.split(":")[0], name, value]
                for name, value in sorted(failures.items())]))
    if system.get("failed_items"):
        add(_table(["item", "category", "message"],
                   [[row.get("item_id"), row.get("category"), (row.get("message") or "")[:90]]
                    for row in system["failed_items"]]))
    if system.get("response_warnings"):
        add(f"Response text warnings: {system['response_warnings']}\n")

    add("## Judge reliability\n")
    human = reliability.get("human_agreement")
    if human:
        add("Human vs human (total score):\n")
        add(_table(["comparisons", "exact agreement", "within 1 point", "mean abs diff",
                    "kappa", "kappa (linear)"],
                   [[human.get("total", {}).get("comparisons"),
                     _percent(human.get("total", {}).get("agreement_percent")),
                     _percent(human.get("total", {}).get("within_one_percent")),
                     _number(human.get("total", {}).get("mean_absolute_difference")),
                     _number(human.get("total", {}).get("cohens_kappa")),
                     _number(human.get("total", {}).get("cohens_kappa_linear"))]]))
        kappa = human.get("total", {}).get("cohens_kappa")
        if kappa is None or kappa == 0:
            add("Kappa at or near zero here does not mean the raters disagreed: it means chance "
                "agreement already explains the observed agreement, which happens when one "
                "evaluator's ratings have no variance. Read the raw columns, not kappa.\n")
    comparison = reliability.get("judge_vs_human")
    if comparison and comparison.get("comparisons"):
        add("Judge vs each human evaluator (total score):\n")
        rows = []
        for evaluator, stats in (comparison.get("by_evaluator") or {}).items():
            total = stats.get("total", {})
            rows.append([evaluator, total.get("comparisons"), _percent(total.get("agreement_percent")),
                         _percent(total.get("within_one_percent")),
                         _number(total.get("mean_absolute_difference")),
                         _number(total.get("cohens_kappa_linear"))])
        add(_table(["evaluator", "comparisons", "exact", "within 1", "mean abs diff",
                    "kappa (linear)"], rows))
        add(f"Major disagreements (>= 2 total points): {comparison.get('major_disagreement_count')} "
            f"({_percent(comparison.get('major_disagreement_percent'))})")
        if comparison.get("major_disagreements"):
            add(_table(["item", "evaluator", "human", "judge", "judge reason"],
                       [[row.get("item_id"), row.get("evaluator_id"), row.get("human_total"),
                         row.get("judge_total"), (row.get("judge_reason") or "")[:80]]
                        for row in comparison["major_disagreements"][:10]]))
    coverage = reliability.get("coverage")
    if coverage:
        add(f"Coverage: {coverage.get('replies_with_human_labels')} labelled of "
            f"{coverage.get('graded_replies')} graded; unlabelled "
            f"{coverage.get('unlabelled_replies')} ({coverage.get('label_status')}).")
    add("Bias experiments:\n")
    add(_table(["experiment", "state", "attempted", "valid", "changed", "changed %",
                "avg score change", "judge calls"],
               [[name, (reliability.get(name) or {}).get("state", "not_run"),
                 (reliability.get(name) or {}).get("attempted"),
                 (reliability.get(name) or {}).get("valid_comparisons"),
                 _number((reliability.get(name) or {}).get("changed"), 0),
                 _percent((reliability.get(name) or {}).get("changed_percent")),
                 _number((reliability.get(name) or {}).get("average_score_change")),
                 _number((reliability.get(name) or {}).get("judge_calls"), 0)]
                for name in ("position_bias", "verbosity_bias")]))
    for name in ("position_bias", "verbosity_bias"):
        note = (reliability.get(name) or {}).get("note")
        if note and (reliability.get(name) or {}).get("state") != "not_run":
            add(f"- `{name}`: {note}")
    add(f"_{reliability.get('note', '')}_\n")

    add("## Performance\n")
    add(_table(["phase", "requests", "mean ms", "p50 ms", "p95 ms", "max ms"],
               [["system", (performance.get("system_latency_ms") or {}).get("count"),
                 _number((performance.get("system_latency_ms") or {}).get("mean"), 1),
                 _number((performance.get("system_latency_ms") or {}).get("median"), 1),
                 _number((performance.get("system_latency_ms") or {}).get("p95"), 1),
                 _number((performance.get("system_latency_ms") or {}).get("max"), 1)],
                ["judge", (performance.get("judge_latency_ms") or {}).get("count"),
                 _number((performance.get("judge_latency_ms") or {}).get("mean"), 1),
                 _number((performance.get("judge_latency_ms") or {}).get("median"), 1),
                 _number((performance.get("judge_latency_ms") or {}).get("p95"), 1),
                 _number((performance.get("judge_latency_ms") or {}).get("max"), 1)]]))
    add(f"- wall clock: "
        + (f"{_number(performance.get('wall_clock_seconds'), 1)} s "
           f"({_number(performance.get('throughput_items_per_minute'), 2)} items/min)"
           if performance.get("wall_clock_seconds") is not None
           else "not measured (this run replayed saved results and made no model calls)"))
    replayed_clock = (metadata.get("judge") or {}).get("original_run_wall_clock_seconds")
    if replayed_clock:
        add(f"- original judge run wall clock: {_number(replayed_clock, 1)} s (from the replayed run's metadata)")
    for phase in ("system_tokens", "judge_tokens"):
        tokens = performance.get(phase) or {}
        add(f"- {phase.replace('_', ' ')}: prompt {tokens.get('prompt')}, "
            f"completion {tokens.get('completion')}, total {tokens.get('total')} "
            f"({tokens.get('items_with_usage')} items with usage)")
    experiments = performance.get("experiments")
    if experiments:
        tokens = experiments.get("judge_tokens") or {}
        add(f"- experiment judge calls: {experiments.get('judge_calls')}, "
            f"prompt {tokens.get('prompt')}, completion {tokens.get('completion')}, "
            f"total {tokens.get('total')}, mean "
            f"{_number((experiments.get('judge_latency_ms') or {}).get('mean'), 1)} ms")
    else:
        add("- experiment judge calls: n/a (no bias experiment ran in this run)")
    add(f"- judge arithmetic corrections applied: {system.get('judge_total_corrections')}\n")

    add("## Cost\n")
    add(_table(["phase", "status", "per item USD", "per 1,000 USD", "run total USD"],
               [[phase, (cost.get(phase) or {}).get("status"),
                 _number((cost.get(phase) or {}).get("per_item_usd"), 6),
                 _number((cost.get(phase) or {}).get("per_1000_requests_usd"), 4),
                 _number((cost.get(phase) or {}).get("total_usd"), 6)]
                for phase in ("system", "judge", "experiments", "combined", "run_total")]))
    projection = cost.get("volume_projection") or {}
    add(f"- {projection.get('multiplier')}x volume ({projection.get('items')} items): "
        f"combined {_number(projection.get('combined_usd'), 4)} USD")
    local = cost.get("local_inference") or {}
    add(f"- local inference: `{local.get('status')}`")
    for reason in (cost.get("system", {}).get("reason"), cost.get("judge", {}).get("reason"),
                   cost.get("experiments", {}).get("reason")):
        if reason:
            add(f"  - {reason}")
    for caveat in cost.get("caveats", []):
        add(f"- {caveat}")
    add("")
    return "\n".join(lines)
