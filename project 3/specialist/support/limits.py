"""Configuration and helpers for bounded graph execution."""

from __future__ import annotations

import os


def _configured_max_steps() -> int:
    raw = os.environ.get("MAX_STEPS", "20").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("MAX_STEPS must be a positive integer") from exc
    if value < 2:
        raise ValueError("MAX_STEPS must be at least 2")
    return value


MAX_STEPS = _configured_max_steps()


def can_consume(step_count: int, amount: int = 1) -> bool:
    """Whether ``amount`` node/tool attempts fit inside the step budget."""
    return amount >= 0 and step_count + amount <= MAX_STEPS


def remaining_steps(step_count: int) -> int:
    return max(0, MAX_STEPS - step_count)
