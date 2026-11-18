"""Revalidate, reserve, execute, and reconcile one approved sandbox action."""

import time

from specialist.catalog.research import matches_line, matches_role
from specialist.contracts.setup import SetupPlan

from .case_state import EXECUTABLE, MAX_REVISIONS, CaseConflict, advance_revision
from .proposals import ORDER, prepare_proposal, proposal_matches
from .steps import BudgetExhausted, SourceBlocked, call_tool, charge_step, record_event, load_listings, verify_candidate


def execute_next(store, researcher, writer, case_id, customer_id, *, expected_revision=None, expected_hash=None):
    """Resume one approved action. The writer must supply durable receipt lookup."""
    if writer is None:
        raise CaseConflict("No trusted sandbox writer is configured")
    with store.update(case_id, customer_id) as case:
        proposal = case["proposal"]
        if expected_revision is not None and (case["revision"] != expected_revision
                or not proposal or proposal["hash"] != expected_hash):
            raise CaseConflict("Execution is not for the current exact proposal")
        if case["status"] == "completed":
            return case
        if case["status"] not in EXECUTABLE:
            raise CaseConflict("Execution requires current approval")
        approval = case["approval"]
        if not approval or not proposal_matches(case, approval["revision"], approval["hash"]):
            raise CaseConflict("Approval does not match the stored proposal")
        try:
            action = next(a for a in proposal["actions"] if a["operation_id"] not in case["receipts"])
            operation_id = action["operation_id"]
            if operation_id in case["attempted"]:
                charge_step(case)
                try:
                    receipt = writer.receipt(action, proposal["run_id"])
                except Exception:
                    case["status"] = "reconciliation_required"
                    record_event(case, "coordinator", "receipt_unavailable", {"operation_id": operation_id})
                    return case
                if receipt is not None:
                    try:
                        _record(case, action, receipt)
                    except ValueError:
                        case["status"] = "reconciliation_required"
                        record_event(case, "coordinator", "receipt_invalid", {"operation_id": operation_id})
                    return case
            if time.time() >= approval["expires_at"]:
                case["status"] = "timed_out"
                record_event(case, "coordinator", "expire_approval", {"receipts_preserved": len(case["receipts"])})
                return case
            if action["action"] == ORDER and not refresh_proposal(case, researcher):
                return case
            # Commit the intent before an external write, so a restarted process
            # checks for a receipt even if the RPC committed after our last save.
            charge_step(case)
            if operation_id not in case["attempted"]:
                case["attempted"].append(operation_id)
            record_event(case, "coordinator", "reserve_write", {"operation_id": operation_id})
            reserved_run = proposal["run_id"]
        except SourceBlocked:
            case.update(status="source_unavailable", approval=None, attempted=[])
            record_event(case, "coordinator", "stop_source_blocked", {})
            return case
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            record_event(case, "coordinator", "stop_budget", {"receipts_preserved": len(case["receipts"])})
            return case

    with store.update(case_id, customer_id) as case:
        # A concurrent worker may already have received this exact operation.
        if (case["run_id"] != reserved_run or operation_id in case["receipts"]
                or case["status"] not in EXECUTABLE):
            return case
        if time.time() >= case["approval"]["expires_at"]:
            case["status"] = "timed_out"
            return case
        started = time.perf_counter()
        try:
            receipt = writer.apply(action, reserved_run, case["approval"])
            _record(case, action, receipt, started=started)
        except Exception:
            case["status"] = "partially_completed" if case["receipts"] else "reconciliation_required"
            record_event(case, "sandbox", "write_unconfirmed", {"operation_id": operation_id}, started=started)
        return case


def _record(case, action, receipt, *, started=None):
    operation = action["operation_id"]
    if not isinstance(receipt, dict) or receipt.get("success") is not True or receipt.get("operation_id") != operation:
        raise ValueError("Sandbox response was not a matching receipt")
    case["receipts"][operation] = receipt
    case["status"] = "completed" if len(case["receipts"]) == len(case["proposal"]["actions"]) else "partially_completed"
    record_event(case, "sandbox", "receipt_confirmed", {"action": action["action"], "operation_id": operation}, started=started)


def refresh_proposal(case, researcher):
    old = load_listings(case["proposal"]["evidence"])
    lines = {line.id: line for line in SetupPlan.model_validate(case["setup"]).items} if case.get("setup") else {}
    fresh = {}
    changes = []
    for role, item in old.items():
        value = researcher.detail(item, lambda actor, action, info, fn: call_tool(case, actor, action, info, fn))
        if not value or not (matches_line(value, lines[role]) if lines else matches_role(value, role)):
            changes.append({"product_id": item.product_id, "field": "source", "before": "verified", "after": "unavailable"})
            continue
        fresh[role] = value
        fields = ("specs", "name") if lines and lines[role].owned else ("price_tnd", "availability", "specs", "name")
        for field in fields:
            prior, current = getattr(item, field), getattr(value, field)
            if prior != current:
                changes.append({"product_id": item.product_id, "field": field,
                                "before": str(prior) if field != "specs" else "previous specifications",
                                "after": str(current) if field != "specs" else "specifications changed"})
    findings = verify_candidate(case, fresh)
    verified = all(f.verdict == "pass" for f in findings)
    if changes or not verified:
        # This branch is reached only after proving that no write was persisted.
        case["attempted"] = []
        if case["revision"] >= MAX_REVISIONS:
            case.update(status="verification_blocked", approval=None, changes=changes,
                        findings=[f.model_dump() for f in findings])
            return False
        advance_revision(case)
        case["changes"] = changes
        record_event(case, "coordinator", "invalidate_approval", {"changes": changes})
        if verified:
            prepare_proposal(case, fresh, findings, "reapproval_required")
        else:
            case.update(status="verification_blocked", findings=[f.model_dump() for f in findings])
        for role, item in old.items():
            kept = [p for p in case["evidence"].get(role, []) if p["product_id"] != item.product_id]
            if role in fresh:
                kept.append(fresh[role].model_dump(mode="json"))
            case["evidence"][role] = kept
            pins = case.get("shopping_pins", {})
            if role in pins and pins[role]["product_id"] == item.product_id:
                pins[role] = fresh[role].model_dump(mode="json") if role in fresh else {
                    **pins[role], "fetched_at": "",
                }
        return False
    return True
