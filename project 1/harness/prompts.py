"""Versioned system prompts for the evaluated customer-support system.

The prompt is part of the experiment: every run records the version and the
SHA-256 of the exact text, so a score can always be tied to a prompt file.
"""
import hashlib
import json
import re
from pathlib import Path

from .config import PROJECT
from .errors import ConfigurationError

PROMPT_DIR = PROJECT / "prompts"
_PATTERN = re.compile(r"^system_(v\d+)\.txt$")


def available_versions(prompt_dir=PROMPT_DIR):
    """Return ``{version: {path, sha256, characters}}`` for every prompt file."""
    versions = {}
    for path in sorted(Path(prompt_dir).glob("system_v*.txt")):
        match = _PATTERN.match(path.name)
        if not match:
            continue
        text = path.read_text(encoding="utf-8")
        versions[match.group(1)] = {
            "path": str(path.relative_to(PROJECT)),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "characters": len(text),
        }
    if not versions:
        raise ConfigurationError(f"No system_v*.txt prompts found in {prompt_dir}")
    return versions


def load_prompt(version, prompt_dir=PROMPT_DIR):
    """Load one prompt version, returning ``(text, sha256, path)``."""
    versions = available_versions(prompt_dir)
    if version not in versions:
        raise ConfigurationError(
            f"Unknown system prompt version {version!r}; available: {', '.join(sorted(versions))}")
    path = Path(prompt_dir) / f"system_{version}.txt"
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ConfigurationError(f"{path} is empty")
    return text, versions[version]["sha256"], str(path.relative_to(PROJECT))


def build_user_message(item):
    """The single user turn sent to the evaluated system (one model call per item).

    Kept byte-compatible with Person 4's runner so a replayed result file and a
    live run describe the same request.
    """
    return ("Customer message:\n"
            f"{item['customer_message']}\n\n"
            "Order context:\n"
            f"{json.dumps(item['order_context'], ensure_ascii=False, indent=2)}")
