"""Offline evaluation runner for Shopline Ops (Person 3).

Drives the real LangGraph with a deterministic injected tool executor. No
network, database, or model calls are made: the default paths use the graph's
offline deterministic proposal fallback and saved catalog/ticket snapshots.

Usage (from ``project 3``)::

    python -m eval.run --output eval/results/trajectories.jsonl

``--limit N`` runs a deterministic prefix of the scenario file for smoke tests.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

# graph.py loads dotenv at import time. Do this before importing agent.graph so
# a developer's key can never turn an offline evaluation into a model call.
with patch.dict(os.environ, {"PYTHON_DOTENV_DISABLED": "1"}):
    from agent import graph

from eval import score  # noqa: E402
from eval.fixtures import make_eval_executor  # noqa: E402

EVAL_ROOT = Path(__file__).resolve().parent
DEFAULT_SCENARIOS = EVAL_ROOT / "scenarios.jsonl"
DEFAULT_INJECTIONS = EVAL_ROOT / "injection_cases.jsonl"
DEFAULT_OUTPUT = EVAL_ROOT / "results" / "trajectories.jsonl"


class EvaluationError(ValueError):
    """Raised for an invalid scenario or injection case."""


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Load a UTF-8 JSONL file, one object per line; blank lines are ignored."""
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise EvaluationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise EvaluationError(f"{path}:{line_number}: expected an object")
            rows.append(row)
    return rows


def load_scenarios(path: Path | str = DEFAULT_SCENARIOS) -> list[dict[str, Any]]:
    return load_jsonl(path)


def load_injection_cases(path: Path | str = DEFAULT_INJECTIONS) -> list[dict[str, Any]]:
    return load_jsonl(path)


def resume_request(request: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Use the checkpoint's normalized values when resuming a product order.

    ``start_order_run`` derives a short query and normalized criteria from the
    customer's prose. The graph rechecks those fields on every resume, so the
    runner must send back the values from the paused snapshot.
    """
    merged = deepcopy(request)
    # Top-level bounds are already inside the checkpoint's normalized
    # product_criteria. Re-supplying them as floats would be re-normalized to a
    # different decimal string and fail the graph's equality check.
    for key in ("price_min_tnd", "price_max_tnd"):
        merged.pop(key, None)
    for key in ("customer_id", "product_query", "product_criteria"):
        if result.get(key) is not None:
            merged[key] = deepcopy(result[key])
    return merged


def resolve_template(value: Any, result: dict[str, Any]) -> Any:
    """Resolve ``$draft.operation_id`` style references from the paused result."""
    if isinstance(value, str) and value.startswith("$"):
        node: Any = result
        for part in value[1:].split("."):
            if not isinstance(node, dict) or part not in node:
                raise EvaluationError(f"Cannot resolve template {value!r}")
            node = node[part]
        return deepcopy(node)
    if isinstance(value, dict):
        return {key: resolve_template(item, result) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_template(item, result) for item in value]
    return value


@contextmanager
def bounded_steps(value: int | None) -> Iterator[None]:
    """Temporarily override the graph's MAX_STEPS for one scenario."""
    previous = graph.MAX_STEPS
    if value is not None:
        graph.MAX_STEPS = value
    try:
        yield
    finally:
        graph.MAX_STEPS = previous


@contextmanager
def offline_model(case):
    """Keep provider calls local, including when exercising structured model parsing."""
    with patch.dict(os.environ, {"SPECIALIST_LEGACY_LLM": "false"}):
        if "model_response" not in case:
            yield
            return
        with patch.object(graph, "OllamaPlanner") as provider:
            os.environ["SPECIALIST_LEGACY_LLM"] = "true"
            invoke = provider.from_env.return_value.structured
            invoke.return_value = deepcopy(case["model_response"])
            yield
            if not invoke.called:
                raise EvaluationError("Scripted model response was never requested")


def run_case(case: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Run one scenario or injection case and return its raw evaluation record."""
    if "fixture_id" not in case or "request" not in case:
        raise EvaluationError(f"{case.get('id', '<unknown>')}: fixture_id and request are required")

    executor, recorder = make_eval_executor(
        case["fixture_id"],
        extra_faults=case.get("faults"),
        extra_mutations=case.get("mutations"),
    )
    request = deepcopy(case["request"])
    resume_plan = deepcopy(case.get("resume", []))
    approval_index: int | None = None

    approved_draft = None
    with bounded_steps(case.get("max_steps")), offline_model(case):
        started = time.perf_counter()
        result = graph.run_operator(request, tool_executor=executor)
        for step in resume_plan:
            stage = step.get("stage")
            if stage not in {"selection", "approval"}:
                raise EvaluationError(f"{case.get('id')}: unsupported resume stage {stage!r}")
            if not step.get("replay") and result.get("status") not in {"awaiting_approval", "awaiting_customer_selection", "partially_completed"}:
                break
            value = resolve_template(step.get("value"), result)
            if stage == "approval" and isinstance(value, dict) and value.get("decision") == "approve":
                # Record the call boundary at which a valid-looking approval was
                # supplied. The scorer uses it to detect writes made before it.
                draft = result.get("draft") or {}
                if (approval_index is None and result.get("status") == "awaiting_approval"
                        and draft.get("operation_id") and value == {"decision": "approve", "operation_id": draft["operation_id"]}):
                    approved_draft = deepcopy(draft)
                    approval_index = len(recorder.calls)
            checkpoint_request = resume_request(request, result)
            if stage == "selection":
                result = graph.run_operator(
                    checkpoint_request, run_id=result["run_id"], selection=value, tool_executor=executor
                )
            else:
                result = graph.run_operator(
                    checkpoint_request, value, run_id=result["run_id"], tool_executor=executor
                )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)

    record: dict[str, Any] = {
        "id": case["id"],
        "kind": kind,
        "category": case.get("category") or case.get("attack_type"),
        "description": case.get("description", ""),
        "fixture_id": case["fixture_id"],
        "request": request,
        "resume": resume_plan,
        "expected": case.get("expected"),
        "assertions": case.get("assertions"),
        "known_gap": case.get("known_gap"),
        "result": result,
        "tool_calls": recorder.to_json(),
        "approval_granted_at_call_index": approval_index,
        "approved_draft": approved_draft,
        "latency_ms": latency_ms,
        "max_steps_in_effect": case.get("max_steps", graph.MAX_STEPS),
    }
    return record


def run_all(
    scenarios_path: Path | str = DEFAULT_SCENARIOS,
    injections_path: Path | str = DEFAULT_INJECTIONS,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Run scenarios first, then injection cases, in file order."""
    scenarios = load_scenarios(scenarios_path)
    injections = load_injection_cases(injections_path)
    if limit is not None:
        scenarios = scenarios[:limit]
        injections = injections[:limit]
    records = []
    for kind, cases in (("scenario", scenarios), ("injection", injections)):
        for case in cases:
            try:
                records.append(run_case(case, kind=kind))
            except Exception as exc:
                # Preserve the rest of the report and fail this case explicitly.
                records.append({"id": case.get("id"), "kind": kind,
                                "category": case.get("category") or case.get("attack_type"),
                                "fixture_id": case.get("fixture_id"),
                                "runner_error": type(exc).__name__})
    return records


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--injections", type=Path, default=DEFAULT_INJECTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=None, help="summary JSON path")
    parser.add_argument("--markdown", type=Path, default=None, help="readable summary path")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N of each file")
    args = parser.parse_args(argv)

    records = run_all(args.scenarios, args.injections, limit=args.limit)
    write_jsonl(args.output, records)

    summary = score.summarize(records)
    summary_path = args.summary or args.output.parent / "summary.json"
    markdown_path = args.markdown or args.output.parent / "summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(score.render_markdown(summary), encoding="utf-8")

    totals = summary["totals"]
    print(
        f"Ran {totals['total']} cases: {totals['passed']} passed, "
        f"{totals['failed']} failed (pass rate {totals['pass_rate']:.1%})."
    )
    print(f"Trajectories: {args.output}")
    print(f"Summary:      {summary_path}")
    print(f"Readable:     {markdown_path}")
    return 0 if totals["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
