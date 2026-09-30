"""Command line interface: ``python -m harness <command>``.

Commands
--------
``validate``  load and check a dataset, print statistics (Person 1 handoff)
``run``       the full pipeline: dataset -> system -> judge -> metrics -> cost
``report``    rebuild metrics, cost, and the report from a finished run
``compare``   compare prompt versions across runs (Person 2 -> Person 4 handoff)

Exit codes: ``0`` success, ``1`` the run recorded item failures, ``2`` a
configuration or dataset problem.
"""
import argparse
import json
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import compare as compare_module
from . import cost as cost_module
from . import metrics as metrics_module
from . import report as report_module
from .config import PROJECT, resolve_config
from .dataset import (dataset_statistics, load_dataset, load_labels, load_responses,
                      read_jsonl, validate_item)
from .errors import CATEGORIES, HarnessError
from .judge_runner import judge_usage, replay_judge, run_judge
from .prompts import available_versions, load_prompt
from .providers import SystemClient
from .results import (JsonlSink, build_metadata, finalise_metadata, join_rows, prepare_run,
                      read_json, read_rows, refuse_overwrite, snapshot_prompt, utc_now, write_json)
from .system_runner import replay_system, run_system

DEFAULT_DATASET = PROJECT / "data" / "dev.jsonl"
DEFAULT_LABELS = PROJECT / "data" / "human_labels.jsonl"
EXIT_OK, EXIT_ITEM_FAILURES, EXIT_USAGE = 0, 1, 2


# --------------------------------------------------------------------- helpers
def _default_run_id():
    return datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def _print_dataset_statistics(statistics):
    print(f"items            : {statistics['items']}")
    print(f"distinct orders  : {statistics['distinct_orders']} "
          f"({statistics['mean_context_items']:.2f} line items per order)")
    print(f"with reference   : {statistics['with_reference_answer']}")
    print(f"invalid records  : {statistics['invalid_records']}")
    print("by split         : " + ", ".join(f"{k}={v}" for k, v in statistics["by_split"].items()))
    print("by category      : " + ", ".join(f"{k}={v}" for k, v in statistics["by_category"].items()))
    print("by difficulty    : " + ", ".join(f"{k}={v}" for k, v in statistics["by_difficulty"].items()))


def _progress(label, produced, target, started):
    elapsed = time.perf_counter() - started
    line = f"  {label}: {produced} done"
    if target:
        rate = elapsed / produced if produced else 0
        remaining = rate * max(0, target - produced)
        line += f", {elapsed:6.1f}s elapsed, ~{remaining:6.1f}s remaining"
    print(line, flush=True)


def _resolve_config(args):
    overrides = {
        "SYSTEM_PROVIDER": args.system_provider,
        "SYSTEM_MODEL": args.system_model,
        "SYSTEM_BASE_URL": args.system_base_url,
        "SYSTEM_API_KEY_ENV": args.system_api_key_env,
        "SYSTEM_PROMPT_VERSION": args.system_prompt,
        "JUDGE_PROVIDER": args.judge_provider,
        "JUDGE_MODEL": args.judge_model,
        "JUDGE_BASE_URL": args.judge_base_url,
        "JUDGE_PROMPT_VERSION": args.judge_prompt,
    }
    return resolve_config({key: value for key, value in overrides.items() if value},
                          env_file=args.env_file)


def _load_judge(config):
    from judge.client import Judge
    return Judge(config.judge.to_client_config())


def _judge_preflight(judge):
    """Check that the judge's provider and model can actually be used.

    The judge client deliberately does no network calls at construction time,
    so a missing local model would otherwise only surface after the first
    (slow) request. Returns a record describing the check.
    """
    if judge.provider != "ollama":
        return {"provider": judge.provider, "model": judge.model, "checked": "configured_only",
                "note": "Hosted judge; access and quotas cannot be verified locally."}
    import urllib.request
    try:
        with urllib.request.urlopen(judge.base + "/api/tags", timeout=15) as response:
            models = {entry.get("name") for entry in json.load(response).get("models", [])}
    except (OSError, ValueError, KeyError) as exc:
        raise HarnessError("network",
                           f"Cannot reach local Ollama at {judge.base}: {exc}") from None
    if judge.model not in models and not any(name.split(":")[0] == judge.model.split(":")[0] for name in models):
        raise HarnessError("model_missing",
                           f"Judge model {judge.model!r} is not installed. Install it with "
                           f"'ollama pull {judge.model}' or set JUDGE_MODEL to an installed "
                           f"model. Installed: {', '.join(sorted(models)) or 'none'}")
    return {"provider": judge.provider, "model": judge.model, "checked": "ollama_tags",
            "installed_models": len(models)}


def _judge_record(judge):
    if judge is None:
        return {}
    return {"model": judge.model, "provider": judge.provider, "prompt_version": judge.prompt_version,
            "prompt_sha256": judge.prompt_hash, "max_tokens": judge.max_tokens,
            "timeout_seconds": judge.timeout}


def _judge_record_from_rows(rows, source):
    """Describe the judge from replayed rows, including the original run's timings.

    A replayed run makes no judge request, so the recorded latency and wall
    clock are labelled as belonging to the original run.
    """
    ok = [row for row in rows if row.get("status") == "ok"]
    record = {
        "model": next((row.get("judge_model") for row in ok if row.get("judge_model")), None),
        "prompt_version": next((row.get("judge_prompt_version") for row in ok
                                if row.get("judge_prompt_version")), None),
        "prompt_sha256": next((row.get("judge_prompt_sha256") for row in ok
                               if row.get("judge_prompt_sha256")), None),
        "replayed_from": str(source),
    }
    original = Path(source).parent / "metadata.json"
    if original.exists():
        try:
            saved = read_json(original)
        except ValueError:
            saved = {}
        record["original_run"] = {"model": saved.get("model"), "prompt_version": saved.get("prompt_version"),
                                  "prompt_sha256": saved.get("prompt_sha256"),
                                  "started_utc": saved.get("started_utc"),
                                  "completed_utc": saved.get("completed_utc")}
        started, completed = saved.get("started_utc"), saved.get("completed_utc")
        if started and completed:
            try:
                record["original_run_wall_clock_seconds"] = round(
                    (datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds(), 2)
            except ValueError:
                pass
    return record


def _load_pairs(path, items_index, limit=None, other_responses=None):
    """Reviewed pairs, or deterministic pairs between two saved response sets."""
    pairs = []
    if path:
        rows, errors = read_jsonl(path)
        if errors:
            raise HarnessError("dataset_error", "; ".join(str(error) for error in errors[:5]))
        for row in rows:
            if row.get("item_id") not in items_index:
                raise HarnessError("dataset_error", f"Unknown item_id in pairs: {row.get('item_id')!r}")
            if not all(isinstance(row.get(key), str) and row[key].strip() for key in ("answer_a", "answer_b")):
                raise HarnessError("dataset_error", "Each pair needs nonempty answer_a and answer_b")
            if row["answer_a"] == row["answer_b"]:
                raise HarnessError("dataset_error", f"Position pair for {row['item_id']} is not distinct")
            pairs.append({"item_id": row["item_id"], "answer_a": row["answer_a"],
                          "answer_b": row["answer_b"], "origin": "reviewed_file"})
    elif other_responses:
        other = {row["item_id"]: row.get("response_text") for row in other_responses}
        candidates = []
        for item_id, text in other.items():
            mine = items_index.get(item_id, {}).get("_response")
            if not (isinstance(text, str) and text.strip() and isinstance(mine, str) and mine.strip()):
                continue
            if text.strip() == mine.strip():
                continue  # identical replies cannot expose an order effect
            candidates.append(item_id)
        ordered, seen_categories = [], set()
        for item_id in candidates:  # cover every category first, then the rest
            category = items_index[item_id].get("category")
            if category not in seen_categories:
                ordered.append(item_id)
                seen_categories.add(category)
        ordered += [item_id for item_id in candidates if item_id not in ordered]
        for item_id in ordered:
            pairs.append({"item_id": item_id, "answer_a": items_index[item_id]["_response"],
                          "answer_b": other[item_id], "origin": "auto_two_responses"})
    if limit:
        pairs = pairs[:limit]
    return pairs


# -------------------------------------------------------------------- validate
def command_validate(args):
    """Load a dataset, report problems, and print statistics. No model calls."""
    dataset = load_dataset(args.dataset, split=args.split, categories=args.category,
                           ids=args.item_id, limit=args.limit, allow_invalid=args.allow_invalid)
    statistics = dataset_statistics(dataset)
    print(f"dataset: {dataset.source} ({dataset.encoding}, sha256 {dataset.sha256[:12]})")
    _print_dataset_statistics(statistics)
    if dataset.errors:
        print(f"\n{len(dataset.errors)} invalid record(s) kept as errors:")
        for error in dataset.errors[:20]:
            print(f"  {error}")
        if len(dataset.errors) > 20:
            print(f"  ... and {len(dataset.errors) - 20} more")
    if args.json_out:
        write_json(args.json_out, {"statistics": statistics, "errors": [e.to_record() for e in dataset.errors]},
                   exclusive=not args.force)
        print(f"\nwrote {args.json_out}")
    if args.check_prompts:
        print("\nsystem prompts available:")
        for version, info in available_versions().items():
            print(f"  {version}: {info['characters']} chars, sha256 {info['sha256'][:12]}")
    return EXIT_OK if not dataset.errors else EXIT_ITEM_FAILURES


# -------------------------------------------------------------------------- run
def command_run(args):
    """Run the full evaluation pipeline and write a self-describing run directory."""
    started = time.perf_counter()
    config = _resolve_config(args)
    dataset = load_dataset(args.dataset, split=args.split, categories=args.category,
                           ids=args.item_id, limit=args.limit, allow_invalid=args.allow_invalid)
    items = dataset.items
    index = {item["id"]: item for item in items}
    labels = load_labels(args.labels) if args.labels and Path(args.labels).exists() else {}
    if args.labels and not labels:
        raise HarnessError("configuration", f"No labels loaded from {args.labels}")
    prompt_text, prompt_sha, prompt_path = load_prompt(config.system.prompt_version)

    run_id = args.run_id or _default_run_id()
    output = Path(args.output) if args.output else config.results_root / run_id
    print(f"run id      : {run_id}")
    print(f"output      : {output}")
    print(f"dataset     : {dataset.source} ({len(items)} items, sha256 {dataset.sha256[:12]})")
    print(f"system      : {config.system.provider}/{config.system.model} "
          f"prompt {config.system.prompt_version} ({prompt_sha[:12]})")
    print(f"judge       : {config.judge.provider}/{config.judge.model} "
          f"prompt {config.judge.prompt_version}")
    if args.system_source:
        print(f"system src  : replay {args.system_source}")
    if args.judge_source:
        print(f"judge src   : replay {args.judge_source}")
    if labels:
        print(f"labels      : {args.labels} ({len(labels)} labelled replies)")

    if args.preflight:
        return _preflight(args, config, prompt_text, items, index)

    if not args.resume:
        refuse_overwrite(output)  # before any provider call, so nothing is spent

    # Both provider checks run before the run directory is created, so a
    # configuration problem never leaves a half-built run behind.
    client = None
    if not args.skip_system and not args.system_source:
        client = SystemClient(config.system, prompt_text)
        print(f"preflight   : {client.preflight()}")
    judge = None
    if not args.skip_judge and not args.judge_source:
        judge = _load_judge(config)
        print(f"judge check : {_judge_preflight(judge)}")

    paths = prepare_run(output, resume=args.resume)
    resuming = args.resume and paths.metadata.exists()

    previous_metadata = read_json(paths.metadata) if resuming else {}
    done_system = {row["item_id"] for row in read_rows(paths.system_rows)}
    done_judge = {row["item_id"] for row in read_rows(paths.judge_rows)}

    prompt_records = [snapshot_prompt(paths, f"system_{config.system.prompt_version}.txt", prompt_text)]
    prompt_records[0].update({"version": config.system.prompt_version, "sha256": prompt_sha,
                              "source": prompt_path})
    command = _reproduction_command(args, run_id)
    if judge is not None:
        prompt_records.append(snapshot_prompt(paths, f"{judge.prompt_version}.txt", judge.prompt))
    if not resuming:
        write_json(paths.metadata, build_metadata(
            run_id, config,
            {"source": str(dataset.source), "sha256": dataset.sha256, "encoding": dataset.encoding,
             "items_selected": len(items), "statistics": dataset_statistics(dataset),
             "invalid_records": len(dataset.errors)},
            prompt_records, _judge_record(judge),
            mode=("replay" if (args.system_source or args.judge_source) else "live"),
            limits={"limit": args.limit, "item_ids": args.item_id, "categories": args.category,
                    "judge_limit": args.judge_limit, "verbosity_limit": args.verbosity_limit,
                    "position_limit": args.position_limit, "position_repeats": args.position_repeats},
            labels_record={"file": str(args.labels) if labels else None,
                           "labelled_replies": len(labels), "independently_reviewed": args.labels_reviewed},
            sources={"system_responses": str(args.system_source) if args.system_source else None,
                     "judge_results": str(args.judge_source) if args.judge_source else None,
                     "position_pairs": str(args.position_pairs) if args.position_pairs else None,
                     "auto_pairs_from": str(args.auto_pairs_from) if args.auto_pairs_from else None},
            reproduction={"command": command}), exclusive=True)
    else:
        metadata = previous_metadata
        metadata["resumed"] = True
        metadata["limits"].update({"judge_limit": args.judge_limit, "verbosity_limit": args.verbosity_limit,
                                   "position_limit": args.position_limit, "position_repeats": args.position_repeats})
        write_json(paths.metadata, metadata)

    # ---------------------------------------------------------------- system
    system_rows = []
    if args.skip_system:
        print("system phase: skipped (--skip-system)")
    else:
        with JsonlSink(paths.system_rows, resume=resuming) as sink:
            if args.system_source:
                responses = load_responses(args.system_source, response_id=args.response_id)
                selected = [response for response in responses if response["item_id"] in index]
                missing = [response["item_id"] for response in responses
                           if response["item_id"] not in index]
                if missing:
                    print(f"warning    : {len(missing)} saved replies are not in this dataset "
                          f"and were skipped: {', '.join(missing[:5])}")
                system_rows = replay_system(selected, items, config.system.prompt_version,
                                            prompt_sha, sink=sink.write,
                                            response_id=args.response_id or responses[0]["response_id"])
                mismatched = sorted({row.get("replayed_prompt_version") for row in system_rows
                                     if "prompt_version_mismatch" in row["warnings"]})
                if mismatched:
                    print(f"warning    : the saved file records prompt_version "
                          f"{', '.join(str(value) for value in mismatched)} but this run is labelled "
                          f"{config.system.prompt_version}; pass --system-prompt to match the saved run")
            else:
                target = len([item for item in items if item["id"] not in done_system])
                system_rows = run_system(client, items, config.system.prompt_version, prompt_sha,
                                         response_id=args.response_id or run_id, sink=sink.write,
                                         skip_ids=done_system, limit=args.limit, source="live")
                _progress("system", len(system_rows), target, started)
        if resuming:
            # Earlier invocations' rows are part of this run: judge what is in
            # the file, not only what this invocation produced.
            system_rows = read_rows(paths.system_rows)
    system_failed = sum(1 for row in system_rows if row.get("status") != "ok")
    print(f"system phase: {len(system_rows)} rows, {len(system_rows) - system_failed} ok, {system_failed} failed")

    # ----------------------------------------------------------------- judge
    judge_rows = []
    response_id = system_rows[0]["response_id"] if system_rows else None
    if args.skip_judge:
        print("judge phase : skipped (--skip-judge)")
    elif args.judge_source:
        with JsonlSink(paths.judge_rows, resume=resuming) as sink:
            judge_rows = replay_judge(args.judge_source, system_rows, sink=sink.write)
        print(f"judge phase : replayed {len(judge_rows)} grades from {args.judge_source}")
        judge = None
        replayed = _judge_record_from_rows(judge_rows, args.judge_source)
        metadata = read_json(paths.metadata)
        metadata["judge"] = replayed
        write_json(paths.metadata, metadata)
    else:
        with JsonlSink(paths.judge_rows, resume=resuming) as sink:
            target = len([row for row in system_rows if row.get("status") == "ok"
                          and row["item_id"] not in done_judge])
            judge_rows = run_judge(judge, items, system_rows, sink=sink.write,
                                   skip_ids=done_judge, limit=args.judge_limit)
            _progress("judge", len(judge_rows), target, started)
    judge_failed = sum(1 for row in judge_rows if row.get("status") != "ok")
    print(f"judge phase : {len(judge_rows)} grades, {len(judge_rows) - judge_failed} ok, {judge_failed} failed")

    # ------------------------------------------------------ bias experiments
    for item_id, row in zip([r["item_id"] for r in system_rows], system_rows):
        index[item_id]["_response"] = row.get("response_text")
    position = verbosity = None
    if args.position_limit or args.position_pairs or args.auto_pairs_from:
        if judge is None and not args.judge_source:
            raise HarnessError("configuration", "Position-bias tests need the judge")
        pairs = _load_pairs(args.position_pairs, index, limit=args.position_limit,
                            other_responses=(load_responses(args.auto_pairs_from)
                                             if args.auto_pairs_from else None))
        position = _run_position_experiment(judge, items, pairs, args.position_repeats)
        _write_experiment_rows(output / "position.jsonl", position["rows"])
        print(f"position    : {position['summary']['changed_percent'] if position['summary']['valid_comparisons'] else 'not measured'}"
              f" ({position['summary']['valid_comparisons']} pairs, {args.position_repeats} repeat(s))")
    if args.verbosity_limit:
        if judge is None and not args.judge_source:
            raise HarnessError("configuration", "Verbosity tests need the judge")
        verbosity = _run_verbosity_experiment(judge, items, system_rows, args.verbosity_limit,
                                              judge_rows=judge_rows)
        _write_experiment_rows(output / "verbosity.jsonl", verbosity["rows"])
        print(f"verbosity   : average score change {verbosity['summary']['average_score_change']}"
              f" over {verbosity['summary']['valid_comparisons']} replies")
    experiment_calls = ((position or {}).get("extra_calls") or []) + ((verbosity or {}).get("extra_calls") or [])

    # ------------------------------------------------- metrics, cost, report
    elapsed = time.perf_counter() - started
    live_calls = ((not args.skip_system and not args.system_source)
                  or (not args.skip_judge and not args.judge_source))
    wall_clock = ((previous_metadata.get("wall_clock_seconds_total") or 0.0) + elapsed) if live_calls else None
    joined, errors = join_rows(paths, index)
    missing = [item_id for item_id in index if not any(row["item_id"] == item_id for row in joined)]
    document = metrics_module.assemble(
        items, system_rows, judge_rows, labels=labels, labels_reviewed=args.labels_reviewed,
        response_id=response_id, position_bias=position["summary"] if position else None,
        verbosity_bias=verbosity["summary"] if verbosity else None,
        experiment_calls=experiment_calls,
        wall_clock_seconds=round(wall_clock, 2) if wall_clock is not None else None)
    metadata = read_json(paths.metadata)
    document["run"] = {"run_id": run_id, "mode": metadata.get("mode"),
                       "response_id": response_id, "prompt_version": config.system.prompt_version,
                       "items_without_result": missing,
                       "items_per_split": {split: sum(1 for item in items if item.get("split") == split)
                                           for split in sorted({item.get("split") for item in items if item.get("split")})},
                       "invocation_seconds": round(elapsed, 2),
                       "replayed_judge_wall_clock_seconds": metadata.get("judge", {}).get("original_run_wall_clock_seconds"),
                       "notes": _run_notes(args, config, dataset, labels, system_rows, judge_rows, response_id)}
    write_json(paths.metrics, document)
    cost_document = cost_module.build_cost_report(
        document, config.pricing, len(items), config.system, config.judge,
        wall_clock_seconds=round(wall_clock, 2) if wall_clock is not None else None,
        multiplier=args.cost_multiplier)
    write_json(paths.cost, cost_document)
    paths.report.write_text(report_module.build_report(
        metadata, document, cost_document, command), encoding="utf-8")
    finalise_metadata(paths, {"wall_clock_seconds_total": round(wall_clock, 2) if wall_clock is not None else None,
                              "invocation_seconds": round(elapsed, 2),
                              "item_rows": len(joined), "error_rows": len(errors),
                              "missing_items": missing})

    print(f"\nitems        : {len(joined)} rows ({len(missing)} without a result)")
    print(f"errors       : {len(errors)} (categories: {', '.join(CATEGORIES)})")
    quality = document["system"]["quality"]
    print(f"average /8   : {_fmt(quality['average_total_out_of_8'])} "
          f"(judged {document['system']['judge_successful']}/{len(items)})")
    print(f"latency ms   : system {_fmt(document['performance']['system_latency_ms']['mean'], 1)}, "
          f"judge {_fmt(document['performance']['judge_latency_ms']['mean'], 1)}")
    print(f"cost         : {cost_document['combined']['status']} "
          f"({_fmt(cost_document['combined'].get('total_usd'), 6)} USD for this run)")
    print(f"artifacts    : {paths.metrics.name}, {paths.cost.name}, {paths.report.name}, "
          f"{paths.item_rows.name}, {paths.error_rows.name}")
    return EXIT_ITEM_FAILURES if (system_failed or judge_failed or errors) else EXIT_OK


def _fmt(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def _run_notes(args, config, dataset, labels, system_rows=None, judge_rows=None, response_id=None):
    """Plain-language notes about what this run does and does not prove."""
    notes = []
    if args.system_source:
        notes.append("System replies were replayed from a saved run: no system model was called, "
                     "and latency/usage are the original run's measurements.")
    if args.judge_source:
        notes.append("Judge grades were replayed from a saved judge run: no judge model was called.")
    if system_rows is not None and judge_rows is not None and not (args.system_source or args.judge_source):
        notes.append("Every latency and token figure in this run was measured by this harness.")
    if dataset.errors:
        notes.append(f"{len(dataset.errors)} dataset record(s) were invalid and are excluded "
                     "(--allow-invalid).")
    if not labels:
        notes.append("No human labels were loaded, so judge-human agreement is not reported.")
    elif judge_rows is not None:
        matched = sum(1 for row in judge_rows
                      if (row["item_id"], row.get("response_id")) in labels)
        if matched == 0:
            notes.append(f"The loaded labels do not cover reply set {response_id!r}: they label "
                         "reference answers, so judge-human agreement is not reported. Human labels "
                         "for these exact replies are still required.")
        elif not args.labels_reviewed:
            notes.append(f"{matched} graded replies have labels, but the labels are seeded rather "
                         "than independently reviewed, so agreement is a smoke check only.")
    if config.system.provider == "ollama" and not args.system_source:
        notes.append("The evaluated system ran locally; there is no API cost for its replies.")
    return notes


def _reproduction_command(args, run_id):
    parts = ["python", "-m", "harness", "run",
             f"--run-id {run_id}",
             f"--output {shlex.quote(str(args.output)) if args.output else 'results/harness/' + run_id}",
             f"--dataset {shlex.quote(str(args.dataset))}"]
    for flag, value in (("--system-source", args.system_source), ("--judge-source", args.judge_source),
                        ("--response-id", args.response_id), ("--labels", args.labels),
                        ("--position-pairs", args.position_pairs),
                        ("--auto-pairs-from", args.auto_pairs_from)):
        if value:
            parts.append(f"{flag} {shlex.quote(str(value))}")
    if args.system_prompt:
        parts.append(f"--system-prompt {args.system_prompt}")
    if args.judge_prompt:
        parts.append(f"--judge-prompt {args.judge_prompt}")
    if args.limit:
        parts.append(f"--limit {args.limit}")
    if args.judge_limit:
        parts.append(f"--judge-limit {args.judge_limit}")
    if args.verbosity_limit:
        parts.append(f"--verbosity-limit {args.verbosity_limit}")
    if args.position_limit:
        parts.append(f"--position-limit {args.position_limit}")
    if args.position_repeats != 1:
        parts.append(f"--position-repeats {args.position_repeats}")
    if args.labels_reviewed:
        parts.append("--labels-reviewed")
    if args.skip_system:
        parts.append("--skip-system")
    if args.skip_judge:
        parts.append("--skip-judge")
    return " ".join(parts)


def _preflight(args, config, prompt_text, items, index):
    """Check configuration and provider readiness without spending model calls."""
    print("\npreflight")
    client = None
    if not args.skip_system and not args.system_source:
        client = SystemClient(config.system, prompt_text)
        print(f"  system  : {client.preflight()}")
    else:
        print("  system  : skipped or replayed")
    if not args.skip_judge and not args.judge_source:
        judge = _load_judge(config)
        print(f"  judge   : {_judge_record(judge)} | {_judge_preflight(judge)}")
    else:
        print("  judge   : skipped or replayed")
    if not args.system_source:
        print(f"  estimate: {len(items)} system calls and {len(items)} judge calls, run sequentially")
    print(f"  prices  : {config.pricing.to_record()}")
    print("preflight ok")
    return EXIT_OK


# ------------------------------------------------------------- bias experiments
PADDING = (" Thank you for contacting us. We appreciate your time. Please let us know if you have "
           "any other questions.")


def _run_position_experiment(judge, items, pairs, repeats=1):
    """Grade the same pair in both orders and map verdicts back to reply identity."""
    index = {item["id"]: item for item in items}
    rows, valid, changed, extra_calls = [], 0, 0, []
    for pair in pairs:
        item = index[pair["item_id"]]
        trials, pair_calls = [], []
        for _ in range(max(1, repeats)):
            forward = _judge_call(judge.prefer, item, pair["answer_a"], pair["answer_b"])
            reverse = _judge_call(judge.prefer, item, pair["answer_b"], pair["answer_a"])
            pair_calls += [_call_spend(forward), _call_spend(reverse)]
            if forward["status"] == "ok" and reverse["status"] == "ok":
                first = _canonical(forward["winner"])
                second = _canonical(reverse["winner"], swapped=True)
                trials.append({"forward": forward["winner"], "reverse": reverse["winner"],
                               "mapped_forward": first, "mapped_reverse": second,
                               "consistent": first == second,
                               "forward_reason": forward.get("reason"),
                               "reverse_reason": reverse.get("reason")})
            else:
                trials.append({"forward": forward.get("kind", "unknown"),
                               "reverse": reverse.get("kind", "unknown"),
                               "forward_error": forward.get("message"), "reverse_error": reverse.get("message"),
                               "consistent": None})
        good = [trial for trial in trials if trial["consistent"] is not None]
        inconsistent = bool(good) and any(not trial["consistent"] for trial in good)
        valid += 1 if good else 0
        changed += 1 if inconsistent else 0
        extra_calls += pair_calls
        rows.append({**pair, "trials": trials, "changed": inconsistent if good else None,
                     "judge_calls": len(pair_calls), "extra_calls": pair_calls})
    summary = metrics_module.bias_summary(
        len(pairs), valid, changed,
        note="Verdicts are mapped back to the original reply identities. With more than one "
             "repeat, a pair counts as order-sensitive if any repeat disagreed; that also "
             "captures ordinary model variation, so read it as a screening result.")
    summary["judge_calls"] = len(extra_calls)
    return {"rows": rows, "summary": summary, "extra_calls": extra_calls}


def _call_spend(record):
    """Usage and latency of one judge call, for experiment cost accounting."""
    return {"usage": judge_usage(record.get("usage")), "latency_ms": record.get("latency_ms")}


def _write_experiment_rows(path, rows):
    """Save experiment rows as JSONL, one per line, so ``report`` can read them.

    Unlike the streaming system and judge rows, these files are recomputed in
    full by every invocation, so an existing file is replaced rather than
    appended to (which would duplicate rows after ``--resume``).
    """
    with Path(path).open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return Path(path)


def _canonical(winner, swapped=False):
    if winner == "tie":
        return "tie"
    return {"A": "B", "B": "A"}[winner] if swapped else winner


def _judge_call(function, *args):
    """Call a judge method and normalise success and failure into one shape.

    ``Judge.grade`` and ``Judge.prefer`` return their result without a status
    key, so add one here instead of making every caller remember that detail.
    """
    from judge.client import JudgeError
    started = time.perf_counter()
    try:
        result = function(*args)
    except JudgeError as exc:
        metadata = exc.metadata if isinstance(exc.metadata, dict) else {}
        return {"status": "error", "kind": exc.kind, "message": str(exc),
                "latency_ms": metadata.get("latency_ms", (time.perf_counter() - started) * 1000),
                "usage": metadata.get("usage")}
    if not isinstance(result, dict):
        return {"status": "error", "kind": "invalid_output",
                "message": f"judge call returned {type(result).__name__}, expected a dict",
                "latency_ms": (time.perf_counter() - started) * 1000}
    return {**result, "status": "ok"}


def _run_verbosity_experiment(judge, items, system_rows, limit, judge_rows=None):
    """Grade padded copies of replies and record the score change.

    The original grade produced earlier in this run is reused when available, so
    a verbosity test costs one extra judge call per item instead of two.
    """
    index = {item["id"]: item for item in items}
    graded = {row["item_id"]: row for row in (judge_rows or []) if row.get("status") == "ok"}
    rows, deltas, extra_calls = [], [], []
    for system_row in [row for row in system_rows if row.get("status") == "ok"][:limit]:
        item = index[system_row["item_id"]]
        original = system_row["response_text"]
        padded_text = original + PADDING
        saved = graded.get(system_row["item_id"])
        if saved and saved.get("scores"):
            # Already paid for in the judge phase, so it is not an extra cost.
            original_grade = {"status": "ok", "scores": saved["scores"], "reason": saved.get("reason"),
                              "latency_ms": saved.get("judge_latency_ms"), "usage": saved.get("judge_usage"),
                              "reused": True}
        else:
            original_grade = _judge_call(judge.grade, item["customer_message"], item["order_context"], original)
            extra_calls.append(_call_spend(original_grade))
        padded_grade = _judge_call(judge.grade, item["customer_message"], item["order_context"], padded_text)
        extra_calls.append(_call_spend(padded_grade))
        valid = (original_grade.get("status", "ok") == "ok" and padded_grade.get("status", "ok") == "ok"
                 and isinstance(original_grade.get("scores"), dict) and isinstance(padded_grade.get("scores"), dict))
        delta = (padded_grade["scores"]["total"] - original_grade["scores"]["total"]) if valid else None
        if delta is not None:
            deltas.append(delta)
        rows.append({
            "item_id": system_row["item_id"], "response_id": system_row.get("response_id"),
            "original_text": original, "padded_text": padded_text,
            "original_scores": original_grade.get("scores"), "padded_scores": padded_grade.get("scores"),
            "delta": delta,
            "original_grade_reused": bool(original_grade.get("reused")),
            "padded_judge_latency_ms": padded_grade.get("latency_ms"),
            "padded_judge_usage": judge_usage(padded_grade.get("usage")),
            "extra_calls": [_call_spend(padded_grade)] + ([] if original_grade.get("reused")
                                                           else [_call_spend(original_grade)]),
            "warnings": ["Padding adds filler; confirm the original was already polite and that "
                         "relevance did not change before reading a delta as verbosity bias."],
        })
    attempted = len(rows)
    changed = sum(1 for delta in deltas if delta != 0)
    summary = metrics_module.bias_summary(
        attempted, len(deltas), changed, deltas,
        note="A padded reply adds no facts. A score change can still reflect tone, relevance, or "
             "model variability rather than length preference alone; inspect the stored texts.")
    summary["judge_calls"] = len(extra_calls)
    summary["original_grades_reused"] = sum(1 for row in rows if row["original_grade_reused"])
    return {"rows": rows, "summary": summary, "extra_calls": extra_calls}


# ---------------------------------------------------------------------- report
def command_report(args):
    """Recompute metrics, cost, and report from a finished run (no model calls)."""
    run_dir = Path(args.run)
    paths = prepare_run_existing(run_dir)
    metadata = read_json(paths.metadata)
    system_rows = read_rows(paths.system_rows)
    judge_rows = read_rows(paths.judge_rows)
    index = {row["item_id"]: row for row in system_rows}
    items = [{"id": item_id, "split": row.get("split"), "category": row.get("category"),
              "difficulty": row.get("difficulty")} for item_id, row in index.items()]
    # --labels defaults to the file this run was started with, so a rebuilt
    # report carries the same agreement statistics as the original run.
    label_path = args.labels or (metadata.get("labels") or {}).get("file")
    labels, label_note = {}, None
    if label_path and Path(label_path).exists():
        labels = load_labels(label_path)
    elif label_path:
        label_note = (f"The human labels recorded for this run ({label_path}) could not be read, "
                      "so agreement statistics are not reported; pass --labels to supply them.")
    response_id = system_rows[0]["response_id"] if system_rows else None
    config = resolve_config({"SYSTEM_PROVIDER": metadata["configuration"]["system"]["provider"],
                             "SYSTEM_MODEL": metadata["configuration"]["system"]["model"],
                             "SYSTEM_PROMPT_VERSION": metadata["configuration"]["system"]["prompt_version"]},
                            env_file=metadata.get("configuration", {}).get("env_file") or None)
    position = _existing_bias(paths.root / "position.jsonl", "position")
    verbosity = _existing_bias(paths.root / "verbosity.jsonl", "verbosity")
    experiment_calls = _saved_experiment_calls(paths.root)
    wall_clock = metadata.get("wall_clock_seconds_total")
    joined, errors = join_rows(paths, index)
    document = metrics_module.assemble(
        items, system_rows, judge_rows, labels=labels,
        labels_reviewed=bool((metadata.get("labels") or {}).get("independently_reviewed")),
        response_id=response_id, position_bias=position, verbosity_bias=verbosity,
        experiment_calls=experiment_calls,
        wall_clock_seconds=wall_clock)
    document["run"] = {"run_id": metadata.get("run_id"), "response_id": response_id,
                       "prompt_version": metadata.get("configuration", {}).get("system", {}).get("prompt_version"),
                       "items_without_result": [item_id for item_id in index
                                               if item_id not in {row["item_id"] for row in joined}],
                       "mode": metadata.get("mode"),
                       "replayed_judge_wall_clock_seconds":
                           metadata.get("judge", {}).get("original_run_wall_clock_seconds"),
                       "notes": (["Metrics rebuilt from the saved rows of this run; no model was called."]
                                 + ([label_note] if label_note else []))}
    write_json(paths.metrics, document)
    cost_document = cost_module.build_cost_report(
        document, config.pricing, len(index), config.system, config.judge,
        wall_clock_seconds=wall_clock, multiplier=args.cost_multiplier)
    write_json(paths.cost, cost_document)
    paths.report.write_text(report_module.build_report(
        metadata, document, cost_document, _reproduction_command_from_metadata(metadata)),
        encoding="utf-8")
    print(f"rebuilt {paths.metrics}, {paths.cost}, {paths.report} for {run_dir}")
    print(f"average /8: {_fmt(document['system']['quality']['average_total_out_of_8'])} "
          f"over {document['system']['judge_successful']} graded replies")
    return EXIT_ITEM_FAILURES if errors else EXIT_OK


def _reproduction_command_from_metadata(metadata):
    command = metadata.get("reproduction", {}).get("command")
    return command or "python -m harness report --run <this run directory>"


def _existing_bias(path, name):
    """Rebuild a bias summary from a saved experiment file, keeping nulls honest."""
    if not Path(path).exists():
        return metrics_module.bias_summary(0, 0, 0, note=f"{name} experiment not run in this run")
    rows = read_rows(path)
    if name == "verbosity":
        deltas = [row["delta"] for row in rows if row.get("delta") is not None]
        summary = metrics_module.bias_summary(len(rows), len(deltas), sum(1 for d in deltas if d != 0), deltas)
    else:
        valid = [row for row in rows if row.get("changed") is not None]
        summary = metrics_module.bias_summary(len(rows), len(valid), sum(1 for row in valid if row["changed"]))
    summary["judge_calls"] = (sum(row["judge_calls"] for row in rows if isinstance(row.get("judge_calls"), int))
                              or None)
    return summary


def _saved_experiment_calls(root):
    """Extra judge calls recorded in the saved experiment files, for cost reporting."""
    calls = []
    for name in ("position.jsonl", "verbosity.jsonl"):
        path = Path(root) / name
        if not path.exists():
            continue
        for row in read_rows(path):
            calls.extend(call for call in (row.get("extra_calls") or []) if isinstance(call, dict))
    return calls


def prepare_run_existing(run_dir):
    from .results import RunPaths
    paths = RunPaths(Path(run_dir))
    if not paths.metadata.exists():
        raise HarnessError("configuration", f"{run_dir} is not a harness run directory")
    return paths


# --------------------------------------------------------------------- compare
def command_compare(args):
    """Compare prompt versions across runs and the repository's saved evidence."""
    rows, sources = compare_module.build_comparison(run_dirs=args.run or [],
                                                    include_legacy=args.legacy)
    output = Path(args.output) if args.output else (compare_module.PROJECT / "results" / "harness"
                                                   / "comparisons" / "prompt_versions")
    if output.exists() and not args.force:
        raise HarnessError("configuration", f"{output} exists; pass --force to overwrite")
    path, markdown = compare_module.write_comparison(output, rows, sources)
    print(compare_module.comparison_markdown(rows, sources))
    print(f"wrote {path} and {markdown}")
    return EXIT_OK


# ------------------------------------------------------------------------ cost
def command_cost(args):
    """Print the cost analysis of a run (recomputed from saved rows)."""
    paths = prepare_run_existing(Path(args.run))
    command_report(argparse.Namespace(run=Path(args.run), labels=args.labels, cost_multiplier=args.cost_multiplier))
    cost_document = read_json(paths.cost)
    for phase in ("system", "judge", "combined"):
        entry = cost_document.get(phase, {})
        print(f"{phase:8s} {entry.get('status'):16s} per item "
              f"{_fmt(entry.get('per_item_usd'), 6)} USD  per 1,000 "
              f"{_fmt(entry.get('per_1000_requests_usd'), 4)} USD  total "
              f"{_fmt(entry.get('total_usd'), 6)} USD")
    projection = cost_document.get("volume_projection", {})
    print(f"{projection.get('multiplier')}x volume ({projection.get('items')} items): "
          f"{_fmt(projection.get('combined_usd'), 4)} USD")
    return EXIT_OK


# ----------------------------------------------------------------------- main
def build_parser():
    parser = argparse.ArgumentParser(prog="python -m harness", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_dataset_flags(target):
        target.add_argument("--dataset", type=Path, default=DEFAULT_DATASET,
                            help="Dataset JSONL (default: data/dev.jsonl)")
        target.add_argument("--split", choices=("dev", "test"))
        target.add_argument("--category", action="append", help="Only this category (repeatable)")
        target.add_argument("--item-id", action="append", help="Only these item ids (repeatable)")
        target.add_argument("--limit", type=int, help="Evaluate at most this many items")
        target.add_argument("--allow-invalid", action="store_true",
                            help="Keep going when records fail validation (they are reported)")

    validate = sub.add_parser("validate", help="Validate a dataset and print statistics")
    add_dataset_flags(validate)
    validate.add_argument("--json-out", type=Path, help="Write statistics to this JSON file")
    validate.add_argument("--force", action="store_true", help="Overwrite --json-out")
    validate.add_argument("--check-prompts", action="store_true", help="List available system prompts")
    validate.set_defaults(handler=command_validate)

    run = sub.add_parser("run", help="Run the evaluation pipeline")
    add_dataset_flags(run)
    run.add_argument("--output", type=Path, help="New run directory (default: results/harness/<run-id>)")
    run.add_argument("--run-id", help="Run identifier recorded in the artifacts")
    run.add_argument("--resume", action="store_true", help="Continue an interrupted run directory")
    run.add_argument("--preflight", action="store_true",
                     help="Check configuration and provider readiness, then stop")
    run.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent / ".env")
    run.add_argument("--system-provider", choices=("ollama", "openai"))
    run.add_argument("--system-model")
    run.add_argument("--system-base-url")
    run.add_argument("--system-api-key-env", help="Name of the variable holding the system API key")
    run.add_argument("--system-prompt", help="System prompt version (default v1; files prompts/system_v*.txt)")
    run.add_argument("--system-source", type=Path,
                     help="Replay saved system replies (Person 4's results/baseline_v*.jsonl)")
    run.add_argument("--response-id", help="Identifier for this reply set (labels must match it)")
    run.add_argument("--skip-system", action="store_true")
    run.add_argument("--skip-judge", action="store_true")
    run.add_argument("--judge-provider", choices=("ollama", "groq"))
    run.add_argument("--judge-model")
    run.add_argument("--judge-base-url")
    run.add_argument("--judge-prompt", choices=("judge_v1", "judge_v2"))
    run.add_argument("--judge-source", type=Path, help="Replay a saved judge results.jsonl")
    run.add_argument("--judge-limit", type=int, help="Grade at most this many replies")
    run.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                     help="Human labels used for the reliability section (default: data/human_labels.jsonl)")
    run.add_argument("--labels-reviewed", action="store_true",
                     help="Assert that the labels were independently human reviewed")
    run.add_argument("--verbosity-limit", type=int, default=0,
                     help="Grade this many padded copies of replies to test verbosity bias")
    run.add_argument("--position-pairs", type=Path,
                     help="Reviewed distinct pairs: item_id, answer_a, answer_b (JSONL)")
    run.add_argument("--auto-pairs-from", type=Path,
                     help="Build position pairs against another saved reply file")
    run.add_argument("--position-limit", type=int, help="Use at most this many position pairs")
    run.add_argument("--position-repeats", type=int, default=1,
                     help="Repeat each order test this many times to separate order from noise")
    run.add_argument("--cost-multiplier", type=int, default=cost_module.DEFAULT_MULTIPLIER,
                     help="Volume multiplier for the cost projection (default 100)")
    run.set_defaults(handler=command_run)

    report = sub.add_parser("report", help="Rebuild metrics, cost, and report for a run")
    report.add_argument("--run", required=True, type=Path, help="Run directory")
    report.add_argument("--labels", type=Path, help="Human labels (default: from the run metadata)")
    report.add_argument("--cost-multiplier", type=int, default=cost_module.DEFAULT_MULTIPLIER)
    report.set_defaults(handler=command_report)

    comparison = sub.add_parser("compare", help="Compare prompt versions across runs")
    comparison.add_argument("--run", action="append", type=Path, help="Harness run directory (repeatable)")
    comparison.add_argument("--legacy", action="store_true",
                            help="Include the repository's earlier saved system/judge runs")
    comparison.add_argument("--output", type=Path, help="Output JSON path (a .md file is written too)")
    comparison.add_argument("--force", action="store_true", help="Overwrite existing output")
    comparison.set_defaults(handler=command_compare)

    cost = sub.add_parser("cost", help="Print the cost analysis of a run")
    cost.add_argument("--run", required=True, type=Path, help="Run directory")
    cost.add_argument("--labels", type=Path)
    cost.add_argument("--cost-multiplier", type=int, default=cost_module.DEFAULT_MULTIPLIER)
    cost.set_defaults(handler=command_cost)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "limit", None) is not None and args.limit < 1:
        parser.error("--limit must be positive")
    for name in ("judge_limit", "verbosity_limit", "position_limit", "cost_multiplier"):
        value = getattr(args, name, None)
        if value is not None and value < 0:
            parser.error(f"--{name.replace('_', '-')} must not be negative")
    if getattr(args, "position_repeats", 1) < 1:
        parser.error("--position-repeats must be positive")
    try:
        return args.handler(args)
    except HarnessError as exc:
        print(f"ERROR [{exc.kind}]: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\ninterrupted: completed rows were flushed; rerun with --resume to continue",
              file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
