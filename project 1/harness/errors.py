"""Error taxonomy for the evaluation harness.

Every failure the harness can observe is mapped to exactly one category so
that failures are counted and analysed instead of disappearing into an
exception. A single failed item must never stop an evaluation, so each
category ends up as a row in ``errors.jsonl`` and a count in ``metrics.json``.

The judge already raises ``judge.JudgeError`` with its own ``kind`` values.
``JUDGE_KIND_TO_CATEGORY`` translates them so that system failures and judge
failures can be counted in the same report.
"""

# Canonical categories used in results.jsonl / errors.jsonl / metrics.json.
CATEGORIES = (
    "configuration",          # missing or contradictory settings
    "dataset_error",          # unreadable/duplicated/malformed dataset record
    "missing_field",          # a required field is absent or the wrong type
    "system_error",           # the evaluated system failed for another reason
    "api_error",              # provider returned an HTTP error
    "timeout",                # socket/request timeout
    "network",                # connection refused, DNS, TLS, reset
    "model_missing",          # the requested model is not installed
    "incomplete_output",      # provider stopped before finishing the answer
    "refusal",                # the provider declined to answer
    "judge_error",            # judge failed for an unmapped reason
    "invalid_judge_output",   # judge output was not valid rubric JSON
    "internal",               # harness bug; should be reported, not hidden
)

JUDGE_KIND_TO_CATEGORY = {
    "configuration": "configuration",
    "input": "missing_field",
    "api": "api_error",
    "model_missing": "model_missing",
    "network": "network",
    "timeout": "timeout",
    "invalid_output": "invalid_judge_output",
    "incomplete": "incomplete_output",
    "refusal": "refusal",
}


class HarnessError(Exception):
    """Base error carrying a stable category plus non-secret metadata."""

    def __init__(self, kind, message, metadata=None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.metadata = metadata or {}

    def __str__(self):
        return self.message

    def as_record(self, item_id=None, phase=None):
        """Serialisable error record. Never contains a provider body or key."""
        return {
            "item_id": item_id,
            "phase": phase,
            "category": self.kind,
            "message": self.message,
            "metadata": self.metadata,
        }


class SystemError(HarnessError):
    """The evaluated customer-support system could not produce a reply."""


class DatasetError(HarnessError):
    """A dataset file is missing, unreadable, or fails validation."""


class ConfigurationError(HarnessError):
    def __init__(self, message):
        super().__init__("configuration", message)


def category_for_judge_kind(kind):
    """Map a ``JudgeError.kind`` to a harness category."""
    return JUDGE_KIND_TO_CATEGORY.get(kind, "judge_error")


def empty_counts():
    """Zeroed category counts, used so every report has the same shape."""
    return {name: 0 for name in CATEGORIES}
