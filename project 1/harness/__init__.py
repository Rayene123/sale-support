"""Person 2 — evaluation harness for the customer-support grader.

Pipeline::

    dataset -> evaluated system -> LLM judge -> structured results
            -> metrics (system, reliability, performance) -> cost -> report

The harness reuses Person 3's judge (``judge.Judge``) and Person 4's prompts and
saved replies, and adds the parts the project is missing: validation, one
command for a full evaluation, per-item structured results, metrics, cost and
latency analysis, prompt-version comparison, and reproducibility metadata.

Command line::

    python -m harness validate --dataset data/dev.jsonl
    python -m harness run --preflight
    python -m harness run --output results/harness/my-run
    python -m harness report --run results/harness/my-run
    python -m harness compare --legacy --run results/harness/my-run
"""
from .config import resolve_config
from .errors import CATEGORIES, HarnessError, SystemError
from .metrics import assemble
from .results import RunPaths

__all__ = ["assemble", "resolve_config", "RunPaths", "HarnessError", "SystemError", "CATEGORIES"]
__version__ = "1.0.0"
