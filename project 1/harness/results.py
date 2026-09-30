"""Run directory layout, streaming writers, and reproducibility metadata.

A harness run is a self-describing directory::

    results/harness/<run_id>/
        metadata.json     configuration, hashes, environment, completion status
        system.jsonl      one row per item from the evaluated system (streamed)
        judge.jsonl       one row per graded reply (streamed)
        items.jsonl       items.jsonl = system + judge joined, one row per item
        errors.jsonl      every categorised failure, for later analysis
        metrics.json      system, reliability, and performance metrics
        cost.json         cost analysis and volume projections
        report.md         human-readable summary
        prompts/          exact prompt texts used by this run

Rows are flushed as they are produced, so an interrupted run keeps its
completed work. Existing directories are never overwritten; ``--resume``
continues a previous run instead.
"""
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECT
from .errors import ConfigurationError

DERIVED_FILES = ("items.jsonl", "errors.jsonl", "metrics.json", "cost.json", "report.md")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def git_commit():
    """Best-effort commit id; a missing repository or git is not an error."""
    try:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True,
                                   text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_sha256(*relative_paths):
    """Hash harness source files so a run can be tied to the code that made it."""
    hashes = {}
    for name in relative_paths:
        path = PROJECT / name
        if path.exists():
            hashes[name] = file_sha256(path)
    return hashes


def environment_record():
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_commit": git_commit(),
    }


def write_json(path, value, exclusive=False):
    """Write JSON, optionally refusing to overwrite an existing file.

    The refusal is a :class:`ConfigurationError` rather than a raw
    ``FileExistsError`` so the caller reports it like any other problem
    instead of printing a traceback.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x" if exclusive else "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except FileExistsError:
        raise ConfigurationError(f"{path} already exists; pass --force to overwrite it") from None
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_row(row):
    return json.dumps(row, ensure_ascii=False)


class JsonlSink:
    """Append-only JSONL writer that flushes every row immediately."""

    def __init__(self, path, resume=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.count = 0
        self._stream = self.path.open("a" if resume else "x", encoding="utf-8")

    def write(self, row):
        self._stream.write(dump_row(row) + "\n")
        self._stream.flush()
        self.count += 1

    def close(self):
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


def read_rows(path):
    """Read a JSONL artefact, ignoring blank lines. Returns ``[]`` when absent.

    Encoding is detected, so Person 4's UTF-16 result files can be read by the
    comparison command without conversion.
    """
    from .dataset import detect_encoding  # local import avoids a cycle

    path = Path(path)
    if not path.exists():
        return []
    text = path.read_bytes().decode(detect_encoding(path))
    rows = []
    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


@dataclass
class RunPaths:
    """Every file belonging to one run, in one place."""

    root: Path

    @property
    def metadata(self):
        return self.root / "metadata.json"

    @property
    def system_rows(self):
        return self.root / "system.jsonl"

    @property
    def judge_rows(self):
        return self.root / "judge.jsonl"

    @property
    def item_rows(self):
        return self.root / "items.jsonl"

    @property
    def error_rows(self):
        return self.root / "errors.jsonl"

    @property
    def metrics(self):
        return self.root / "metrics.json"

    @property
    def cost(self):
        return self.root / "cost.json"

    @property
    def report(self):
        return self.root / "report.md"

    @property
    def prompts(self):
        return self.root / "prompts"

    def exists(self):
        return self.root.exists()


def refuse_overwrite(root):
    """Raise if continuing would overwrite a previous run.

    Checked before any model call, so a mistyped ``--output`` never spends
    money and never damages saved results.
    """
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        if not (root / "metadata.json").exists():
            raise ConfigurationError(
                f"{root} is not a harness run directory (no metadata.json)")
        raise ConfigurationError(
            f"{root} already exists and is not empty; choose a new --output "
            "directory or pass --resume to continue that run")


def prepare_run(root, resume=False):
    """Create (or reopen) a run directory. Refuses to clobber existing data."""
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        if not resume:
            refuse_overwrite(root)
        if not (root / "metadata.json").exists():
            raise ConfigurationError(f"{root} is not a harness run directory (no metadata.json)")
        return RunPaths(root)
    root.mkdir(parents=True, exist_ok=True)
    paths = RunPaths(root)
    paths.prompts.mkdir(exist_ok=True)
    return paths


def snapshot_prompt(paths, name, text):
    path = paths.prompts / name
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return {"name": f"prompts/{name}", "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def build_metadata(run_id, config, dataset_record, prompt_records, judge_record,
                   mode, limits, labels_record=None, sources=None, reproduction=None, resume=False):
    """Assemble ``metadata.json``. Secrets are never included."""
    return {
        "run_id": run_id,
        "harness_version": "1.0.0",
        "created_utc": utc_now(),
        "mode": mode,
        "resumed": resume,
        "configuration": config.to_record(),
        "limits": limits,
        "dataset": dataset_record,
        "prompts": prompt_records,
        "judge": judge_record or {},
        "labels": labels_record or {"used": False},
        "input_sources": sources or {},
        "reproduction": reproduction or {},
        "environment": environment_record(),
        "code_sha256": code_sha256("harness/dataset.py", "harness/providers.py",
                                   "harness/system_runner.py", "harness/judge_runner.py",
                                   "harness/metrics.py", "harness/cost.py", "harness/cli.py",
                                   "harness/results.py", "judge/client.py"),
        "completed_utc": None,
        "status": "in_progress",
    }


def finalise_metadata(paths, extra=None):
    metadata = read_json(paths.metadata)
    metadata["completed_utc"] = utc_now()
    metadata["status"] = "complete"
    if extra:
        metadata.update(extra)
    write_json(paths.metadata, metadata)
    return metadata


def join_rows(paths, items_index):
    """Build ``items.jsonl``: exactly one row per evaluation item.

    System failures and judge failures both appear, so coverage is auditable:
    a missing item can only mean the run was interrupted.
    """
    system = {row["item_id"]: row for row in read_rows(paths.system_rows)}
    judge = {(row["item_id"], row["response_id"]): row for row in read_rows(paths.judge_rows)}
    errors = []
    rows = []
    for item_id in items_index:
        item = items_index[item_id] if isinstance(items_index, dict) else None
        system_row = system.get(item_id)
        response_id = system_row.get("response_id") if system_row else None
        judge_row = judge.get((item_id, response_id)) if response_id else None
        if system_row is None and judge_row is None:
            continue
        row = {
            "item_id": item_id,
            "split": (item or {}).get("split"),
            "category": (item or {}).get("category"),
            "difficulty": (item or {}).get("difficulty"),
            "system": system_row,
            "judge": judge_row,
            "status": _row_status(system_row, judge_row),
        }
        rows.append(row)
        for phase, source in (("system", system_row), ("judge", judge_row)):
            if source and source.get("status") == "error":
                error = source.get("error") or {}
                errors.append({"item_id": item_id, "phase": phase,
                               "category": error.get("category", "internal"),
                               "message": error.get("message", ""),
                               "error_type": error.get("type"), "metadata": error.get("metadata")})
    with paths.item_rows.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(dump_row(row) + "\n")
    with paths.error_rows.open("w", encoding="utf-8") as stream:
        for row in errors:
            stream.write(dump_row(row) + "\n")
    return rows, errors


def _row_status(system_row, judge_row):
    if system_row is None:
        return "not_run"
    if system_row.get("status") == "error":
        return "system_error"
    if judge_row is None:
        return "not_judged"
    return judge_row.get("status", "unknown")
