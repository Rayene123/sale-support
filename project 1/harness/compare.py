"""Compare prompt versions across runs.

Answers the question the whole project exists for: *did a prompt change
actually improve the measured result?* Each run contributes one row with the
prompt version, coverage, average score, score distribution, latency, tokens,
and cost, plus the change against the first (baseline) row.

Two input styles are supported:

* harness run directories (``--run``), and
* the repository's earlier saved evidence (``--legacy``): Person 4's
  ``results/baseline_v*.jsonl`` latency/token files together with Person 3's
  saved judge comparison, so old and new numbers can be read in one table.
"""
import json
from pathlib import Path

from .config import PROJECT
from .errors import HarnessError
from .metrics import describe
from .results import read_json, read_rows

BASELINE_FILES = ("v1", "v2", "v3")
LEGACY_COMPARISON_DIRS = ("judge-comparison-v2-20260929",)


def run_row(run_dir):
    """Summarise one harness run directory."""
    run_dir = Path(run_dir)
    metadata = read_json(run_dir / "metadata.json")
    metrics = read_json(run_dir / "metrics.json")
    cost_path = run_dir / "cost.json"
    cost = read_json(cost_path) if cost_path.exists() else {}
    system = metrics.get("system", {})
    quality = system.get("quality", {})
    performance = metrics.get("performance", {})
    prompts = metadata.get("prompts") or [{}]
    dataset = metadata.get("dataset", {})
    combined_cost = (cost.get("combined") or {}).get("total_usd")
    return {
        "run_id": metadata.get("run_id"),
        "prompt_version": prompts[0].get("version"),
        "prompt_sha256": prompts[0].get("sha256"),
        "created_utc": metadata.get("created_utc"),
        "mode": metadata.get("mode"),
        "system_model": metadata.get("configuration", {}).get("system", {}).get("model"),
        "judge_model": metadata.get("judge", {}).get("model"),
        "judge_prompt_version": metadata.get("judge", {}).get("prompt_version"),
        "dataset": dataset.get("source"),
        "split": dataset.get("split"),
        "items": system.get("dataset_items"),
        "system_successful": system.get("system_successful"),
        "system_failed": system.get("system_failed"),
        "judge_successful": system.get("judge_successful"),
        "average_total_out_of_8": quality.get("average_total_out_of_8"),
        "score_distribution": quality.get("score_distribution"),
        "average_by_criterion": quality.get("average_by_criterion"),
        "avg_system_latency_ms": (performance.get("system_latency_ms") or {}).get("mean"),
        "p95_system_latency_ms": (performance.get("system_latency_ms") or {}).get("p95"),
        "avg_judge_latency_ms": (performance.get("judge_latency_ms") or {}).get("mean"),
        "total_system_tokens": (performance.get("system_tokens") or {}).get("total"),
        "total_judge_tokens": (performance.get("judge_tokens") or {}).get("total"),
        "combined_cost_usd": combined_cost,
        "source": str(run_dir),
    }


def _legacy_system_metrics(path):
    rows = read_rows(path)
    latencies = [row["latency_ms"] for row in rows
                 if isinstance(row.get("latency_ms"), (int, float))]
    tokens = sum(row.get("total_tokens") or 0 for row in rows)
    successful = sum(1 for row in rows if str(row.get("response", "")).strip())
    return {"items": len(rows), "successful": successful, "failed": len(rows) - successful,
            "latency": describe(latencies), "total_tokens": tokens,
            "model": next((row.get("model") for row in rows if row.get("model")), None)}


def legacy_rows(project=PROJECT):
    """Summarise the repository's earlier saved runs (no model is called)."""
    comparison_path = None
    for name in LEGACY_COMPARISON_DIRS:
        candidate = project / "results" / name / "comparison.json"
        if candidate.exists():
            comparison_path = candidate
            break
    if comparison_path is None:
        raise HarnessError("configuration",
                           f"No saved judge comparison found in {project / 'results'}")
    comparison = read_json(comparison_path)
    rows = []
    for version in BASELINE_FILES:
        baseline = project / "results" / f"baseline_{version}.jsonl"
        if not baseline.exists():
            continue
        system = _legacy_system_metrics(baseline)
        quality = (comparison.get("versions", {}).get(version) or {}).get("quality", {})
        rows.append({
            "run_id": f"legacy_{version}",
            "prompt_version": version,
            "prompt_sha256": None,
            "created_utc": None,
            "mode": "legacy_saved_run",
            "system_model": system["model"],
            "judge_model": comparison.get("model"),
            "judge_prompt_version": comparison.get("judge_prompt_version"),
            "dataset": "results/baseline_%s.jsonl" % version,
            "split": "dev",
            "items": system["items"],
            "system_successful": system["successful"],
            "system_failed": system["failed"],
            "judge_successful": (comparison.get("versions", {}).get(version) or {}).get("successful_responses"),
            "average_total_out_of_8": quality.get("average_total_out_of_8"),
            "score_distribution": quality.get("score_distribution"),
            "average_by_criterion": quality.get("average_by_criterion"),
            "avg_system_latency_ms": system["latency"].get("mean"),
            "p95_system_latency_ms": system["latency"].get("p95"),
            "avg_judge_latency_ms": None,
            "total_system_tokens": system["total_tokens"],
            "total_judge_tokens": None,
            "combined_cost_usd": None,
            "source": str(baseline),
        })
    return rows, comparison_path


def with_deltas(rows):
    """Add the change in average score against the first row."""
    baseline = next((row["average_total_out_of_8"] for row in rows
                     if row.get("average_total_out_of_8") is not None), None)
    for row in rows:
        average = row.get("average_total_out_of_8")
        row["delta_vs_baseline"] = (None if average is None or baseline is None
                                    else average - baseline)
    return rows


def build_comparison(run_dirs=(), include_legacy=False, project=PROJECT):
    """Collect rows from harness runs and/or the repository's saved evidence."""
    rows = [run_row(directory) for directory in run_dirs]
    sources = {"runs": [str(directory) for directory in run_dirs], "legacy": None}
    if include_legacy:
        legacy, legacy_path = legacy_rows(project)
        rows.extend(legacy)
        sources["legacy"] = str(legacy_path)
    if not rows:
        raise HarnessError("configuration", "No runs selected; pass --run or --legacy")
    rows.sort(key=lambda row: (row.get("prompt_version") or "", row.get("run_id") or ""))
    return with_deltas(rows), sources


def _number(value, digits=3, suffix=""):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}{suffix}"
    return f"{value}{suffix}"


def comparison_markdown(rows, sources):
    lines = ["# Prompt version comparison\n"]
    for label, value in sources.items():
        if value:
            lines.append(f"- {label}: {', '.join(value) if isinstance(value, list) else value}")
    lines.append("")
    headers = ["prompt", "run", "items", "judged", "avg /8", "delta", "avg system ms",
               "p95 system ms", "system tokens", "judge tokens", "cost USD"]
    table_rows = []
    for row in rows:
        table_rows.append([
            row.get("prompt_version"), row.get("run_id"), row.get("items"),
            row.get("judge_successful"), _number(row.get("average_total_out_of_8")),
            _number(row.get("delta_vs_baseline")), _number(row.get("avg_system_latency_ms"), 1),
            _number(row.get("p95_system_latency_ms"), 1), row.get("total_system_tokens"),
            row.get("total_judge_tokens"), _number(row.get("combined_cost_usd"), 6),
        ])
    widths = [max(len(str(headers[index])), *(len(str(row[index])) for row in table_rows))
              for index in range(len(headers))]
    lines.append("| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |")
    lines.append("|" + "|".join("-" * (width + 2) for width in widths) + "|")
    for row in table_rows:
        lines.append("| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))) + " |")
    lines.append("")
    lines.append("Score distributions:\n")
    for row in rows:
        distribution = row.get("score_distribution") or {}
        if not distribution:
            continue
        lines.append(f"- **{row.get('prompt_version')}** ({row.get('run_id')}): " +
                     ", ".join(f"{score}/8: {count}" for score, count in sorted(distribution.items()) if count))
    lines.append("")
    lines.append("Notes:\n")
    lines.append("- Scores are model-assigned unless the run attests independent human review.")
    lines.append("- Averages are computed over graded items only; check coverage before comparing.")
    lines.append("- Latency and tokens differ by hardware and provider; do not read them as quality.")
    lines.append("- `legacy_*` rows come from saved files, not from a fresh run of this harness.")
    lines.append("")
    return "\n".join(lines)


def write_comparison(path, rows, sources):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump({"rows": rows, "sources": sources}, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    markdown = path.with_suffix(".md")
    markdown.write_text(comparison_markdown(rows, sources), encoding="utf-8")
    return path, markdown
