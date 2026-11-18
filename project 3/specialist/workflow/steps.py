"""Bounded case steps and allowlisted trace events."""

from datetime import datetime, timezone
import time

from specialist.contracts.purchasing import Finding, Listing, Requirements
from specialist.contracts.setup import SetupPlan
from specialist.observability import capture_event
from specialist.verification.display import verify_bundle
from specialist.verification.setup import verify_setup

from .cancellation import check_cancelled


EVIDENCE_MAX_AGE_S = 15 * 60
MAX_VERIFICATIONS = 18


class BudgetExhausted(RuntimeError):
    pass


class SourceBlocked(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc)


def case_requirements(case):
    return Requirements.model_validate(case["requirements"])


def load_listings(value):
    return {role: Listing.model_validate(item) for role, item in value.items()}


def is_fresh(item: Listing) -> bool:
    try:
        observed = datetime.fromisoformat(item.fetched_at.replace("Z", "+00:00"))
        return 0 <= (_now() - observed).total_seconds() <= EVIDENCE_MAX_AGE_S
    except (TypeError, ValueError):
        return False


def record_event(case, actor, name, detail, *, started=None):
    case["trajectory"].append({
        "case_id": case["case_id"], "run_id": case["run_id"],
        "revision": case["revision"], "actor": actor, "action": name,
        "detail": detail, "at": _now().isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2) if started is not None else 0,
        "remaining_steps": case["step_limit"] - case["steps"],
    })
    capture_event(case["trajectory"][-1])


def charge_step(case):
    check_cancelled()
    if case["steps"] >= case["step_limit"]:
        raise BudgetExhausted
    case["steps"] += 1


def call_tool(case, actor, action, info, invoke):
    charge_step(case)
    started = time.perf_counter()
    try:
        result = invoke()
    except Exception:
        result = {"success": False, "error": "tool_call_failed"}
    check_cancelled()
    if not isinstance(result, dict):
        result = {"success": False, "error": "invalid_tool_response"}
    error = result.get("error") if result.get("success") is not True else None
    code = error if error in ("invalid_product_source", "robots_disallowed", "source_blocked",
        "product_identity_unknown", "source_timeout", "source_unavailable", "invalid_product_evidence") else "tool_call_failed"
    record_event(case, actor, action, {**info, "outcome": code if error else "ok"}, started=started)
    if error == "source_blocked":
        raise SourceBlocked
    return result


def verify_candidate(case, items):
    charge_step(case)
    started = time.perf_counter()
    findings = verify_setup(SetupPlan.model_validate(case["setup"]), items) if case.get("setup") else verify_bundle(case_requirements(case), items)
    stale = [item.product_id for item in items.values() if not is_fresh(item)]
    if stale:
        findings.append(Finding(code="evidence_freshness", verdict="unknown",
                                reason="An exact listing is stale or lacks a valid timestamp"))
    record_event(case, "verifier", "check_candidate",
           {"products": [p.product_id for p in items.values()],
            "findings": [{"code": f.code, "verdict": f.verdict} for f in findings]}, started=started)
    return findings
