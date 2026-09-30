"""Dataset loading and validation.

Responsibilities of the loader:

* read JSONL written as UTF-8 or UTF-16 (Person 4's saved runs are UTF-16),
* validate every required field instead of trusting the file,
* refuse duplicate ids and keep malformed records as explicit error records,
* support golden / dev / test selection, and
* produce dataset statistics for the Person 1 handoff.

Invalid records are never silently dropped: they are returned in
``Dataset.errors`` and, unless ``allow_invalid`` is set, they stop the run.
"""
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .errors import DatasetError

REQUIRED_ITEM_FIELDS = ("id", "customer_message", "order_context")
REQUIRED_CONTEXT_FIELDS = ("order_number", "status", "items")
REQUIRED_LINE_FIELDS = ("product_name", "quantity", "line_total")
OPTIONAL_ITEM_FIELDS = ("split", "category", "difficulty", "reference_answer",
                        "expected_facts", "unavailable_info", "notes")
VALID_SPLITS = ("dev", "test")

# Person 4 recorded encoding damage in the v3 replies (e.g. "ORDÔÇæ10002").
# The harness flags such text instead of letting it be graded as correct.
_MOJIBAKE = re.compile(r"[ÔÃÂ][\u0080-\u00bf\u201a-\u201f\ufffd]")


@dataclass
class RecordError:
    """One rejected input record, with enough context to fix the source file."""

    source: str
    line: int
    category: str
    message: str
    item_id: str = None

    def to_record(self):
        return {"source": self.source, "line": self.line, "category": self.category,
                "message": self.message, "item_id": self.item_id}

    def __str__(self):
        return f"{self.source}:{self.line}: {self.message}"


@dataclass
class Dataset:
    items: list
    errors: list = field(default_factory=list)
    source: Path = None
    sha256: str = ""
    encoding: str = "utf-8"
    skipped: int = 0

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def by_id(self):
        return {item["id"]: item for item in self.items}

    @property
    def ids(self):
        return [item["id"] for item in self.items]


def detect_encoding(path):
    """Person 4's files are UTF-16; everything written by the harness is UTF-8."""
    raw = Path(path).read_bytes()[:2]
    if raw in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return "utf-8-sig"


def read_jsonl(path):
    """Return ``(rows, errors)``. Malformed lines become errors, not exceptions."""
    path = Path(path)
    if not path.exists():
        raise DatasetError("dataset_error", f"Dataset file not found: {path}")
    encoding = detect_encoding(path)
    try:
        text = path.read_bytes().decode(encoding)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DatasetError("dataset_error", f"Cannot decode {path} as {encoding}: {exc}") from None
    rows, errors = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            errors.append(RecordError(path.name, number, "dataset_error", f"invalid JSON: {exc}"))
            continue
        if not isinstance(row, dict):
            errors.append(RecordError(path.name, number, "dataset_error", "record is not a JSON object"))
            continue
        rows.append((number, row))
    return rows, errors


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_item(row, source="", line=0):
    """Return a list of human-readable problems (empty when the item is valid)."""
    problems = []
    for name in REQUIRED_ITEM_FIELDS:
        if name not in row:
            problems.append(f"missing required field {name!r}")
    item_id = row.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        problems.append("id must be a nonempty string")
    message = row.get("customer_message")
    if "customer_message" in row and (not isinstance(message, str) or not message.strip()):
        problems.append("customer_message must be a nonempty string")
    context = row.get("order_context")
    if "order_context" in row:
        if not isinstance(context, dict) or not context:
            problems.append("order_context must be a nonempty object")
        else:
            for name in REQUIRED_CONTEXT_FIELDS:
                if name not in context:
                    problems.append(f"order_context is missing {name!r}")
            lines = context.get("items")
            if not isinstance(lines, list) or not lines:
                problems.append("order_context.items must be a nonempty list")
            else:
                for position, entry in enumerate(lines):
                    if not isinstance(entry, dict):
                        problems.append(f"order_context.items[{position}] is not an object")
                        continue
                    for name in REQUIRED_LINE_FIELDS:
                        if name not in entry:
                            problems.append(f"order_context.items[{position}] is missing {name!r}")
    split = row.get("split")
    if split is not None and split not in VALID_SPLITS:
        problems.append(f"split must be one of {VALID_SPLITS}, got {split!r}")
    return [f"{source}:{line}: {problem}" if (source and line) else problem for problem in problems]


def load_dataset(path, split=None, categories=None, ids=None, limit=None, allow_invalid=False):
    """Load, validate, and filter a dataset file.

    ``allow_invalid=False`` (default) refuses to start when any record fails
    validation, so a broken dataset can never be half-evaluated.
    """
    rows, errors = read_jsonl(path)
    items, seen, problems = [], {}, list(errors)
    for number, row in rows:
        row_problems = validate_item(row)
        item_id = row.get("id")
        if isinstance(item_id, str) and item_id.strip():
            if item_id in seen:
                row_problems.append(f"duplicate id {item_id!r} (first seen on line {seen[item_id]})")
            seen[item_id] = number
        if row_problems:
            errors.append(RecordError(Path(path).name, number, "dataset_error",
                                      "; ".join(row_problems), item_id if isinstance(item_id, str) else None))
            continue
        if split and row.get("split") != split:
            continue
        if categories and row.get("category") not in categories:
            continue
        if ids and row["id"] not in ids:
            continue
        items.append(row)
        if limit and len(items) >= limit:
            break
    if not allow_invalid and errors:
        summary = "; ".join(str(error) for error in errors[:5])
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        raise DatasetError("dataset_error",
                           f"{path} has {len(errors)} invalid record(s): {summary}{more}")
    if not items:
        raise DatasetError("dataset_error",
                           f"No usable items selected from {path} "
                           f"(split={split!r}, categories={sorted(categories) if categories else None})")
    return Dataset(items=items, errors=errors, source=Path(path),
                   sha256=sha256_of(path), encoding=detect_encoding(path),
                   skipped=len(errors))


def dataset_statistics(dataset):
    """Counts the Person 1 handoff needs: size, splits, categories, difficulty."""
    items = dataset.items if isinstance(dataset, Dataset) else list(dataset)
    return {
        "items": len(items),
        "id_range": [items[0]["id"], items[-1]["id"]] if items else None,
        "by_split": dict(sorted(Counter(item.get("split", "unknown") for item in items).items())),
        "by_category": dict(sorted(Counter(item.get("category", "unknown") for item in items).items())),
        "by_difficulty": dict(sorted(Counter(item.get("difficulty", "unknown") for item in items).items())),
        "with_reference_answer": sum(1 for item in items if str(item.get("reference_answer", "")).strip()),
        "order_context_lines": sum(len(item["order_context"]["items"]) for item in items),
        "distinct_orders": len({item["order_context"]["order_number"] for item in items}),
        "mean_context_items": (sum(len(item["order_context"]["items"]) for item in items) / len(items)) if items else None,
        "sha256": dataset.sha256 if isinstance(dataset, Dataset) else None,
        "source": str(dataset.source) if isinstance(dataset, Dataset) and dataset.source else None,
        "invalid_records": len(dataset.errors) if isinstance(dataset, Dataset) else 0,
    }


def load_labels(path):
    """Load human labels as ``{(item_id, response_id): [label, ...]}``.

    The schema is Person 1's: ``item_id``, ``response_id``, ``response_text``,
    ``evaluator_id``, ``scores`` and an optional ``explanation``.
    """
    from judge.client import LIMITS  # local import keeps the dependency explicit

    labels, errors, seen = {}, [], set()
    parsed, parse_errors = read_jsonl(path)
    errors.extend(parse_errors)
    for number, row in parsed:
        problems = []
        for name in ("item_id", "response_id", "response_text", "evaluator_id"):
            if not isinstance(row.get(name), str) or not row[name].strip():
                problems.append(f"{name!r} must be a nonempty string")
        scores = row.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(LIMITS) | {"total"}:
            problems.append("scores must contain the five criteria plus total")
        else:
            for name, limit in {**LIMITS, "total": 8}.items():
                value = scores.get(name)
                if type(value) is not int or not 0 <= value <= limit:
                    problems.append(f"scores.{name} must be an integer in 0..{limit}")
            if all(type(scores.get(name)) is int for name in scores) and \
                    scores.get("total") != sum(scores.get(name, 0) for name in LIMITS):
                problems.append("scores.total does not match the criterion sum")
        if problems:
            errors.append(RecordError(Path(path).name, number, "dataset_error", "; ".join(problems)))
            continue
        key = (row["item_id"], row["response_id"])
        identity = (*key, row["evaluator_id"])
        if identity in seen:
            errors.append(RecordError(Path(path).name, number, "dataset_error",
                                      f"duplicate evaluator label {identity}"))
            continue
        seen.add(identity)
        existing = labels.setdefault(key, [])
        if existing and existing[0]["response_text"] != row["response_text"]:
            errors.append(RecordError(Path(path).name, number, "dataset_error",
                                      f"two different response texts labelled for {key}"))
            continue
        existing.append(row)
    if errors:
        summary = "; ".join(str(error) for error in errors[:5])
        raise DatasetError("dataset_error", f"{path}: {len(errors)} invalid label record(s): {summary}")
    if not labels:
        raise DatasetError("dataset_error", f"{path}: no labels found")
    return labels


def load_responses(path, response_id=None):
    """Normalise saved system replies into ``{item_id, response_id, ...}`` rows.

    Both schemas are accepted: Person 4's ``id``/``response`` (UTF-16 JSONL)
    and the harness' ``item_id``/``response_text``.
    """
    identifier = response_id or Path(path).stem
    responses, errors = [], []
    parsed, parse_errors = read_jsonl(path)
    errors.extend(parse_errors)
    for number, row in parsed:
        item_id = row.get("item_id", row.get("id"))
        text = row.get("response_text", row.get("response"))
        problems = []
        if not isinstance(item_id, str) or not item_id.strip():
            problems.append("item_id/ id must be a nonempty string")
        if not isinstance(text, str):
            problems.append("response_text/ response must be a string")
        if problems:
            errors.append(RecordError(Path(path).name, number, "dataset_error", "; ".join(problems)))
            continue
        responses.append({
            "item_id": item_id,
            "response_id": row.get("response_id") or identifier,
            "response_text": text,
            "source_file": str(path),
            # Person 4's saved runs and this harness' own system.jsonl rows
            # spell these fields differently; both are accepted.
            "system_model": row.get("model", row.get("system_model")),
            "system_latency_ms": row.get("latency_ms", row.get("system_latency_ms")),
            "system_prompt_version": row.get("prompt_version", row.get("system_prompt_version")),
            "system_tokens": {
                "prompt": row.get("prompt_tokens"),
                "completion": row.get("completion_tokens"),
                "total": row.get("total_tokens"),
            },
        })
    if errors:
        summary = "; ".join(str(error) for error in errors[:5])
        raise DatasetError("dataset_error", f"{path}: {len(errors)} invalid response record(s): {summary}")
    if not responses:
        raise DatasetError("dataset_error", f"{path}: no responses found")
    seen = set()
    for response in responses:
        key = (response["item_id"], response["response_id"])
        if key in seen:
            raise DatasetError("dataset_error", f"{path}: duplicate response for {key}")
        seen.add(key)
    return responses


def text_warnings(text):
    """Report text that would corrupt a score even when the JSON is valid."""
    warnings = []
    if "\ufffd" in text:
        warnings.append("replacement_characters")
    if _MOJIBAKE.search(text):
        warnings.append("mojibake")
    return warnings
