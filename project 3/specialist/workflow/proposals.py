"""Construct the exact order and notification payloads shown for approval."""

from decimal import Decimal
from hashlib import sha256
import json
from uuid import uuid4

from specialist.contracts.setup import SetupPlan, setup_total
from specialist.sandbox.payloads import canonical_action_payload

from .steps import record_event


ORDER = "create_customer_order"
NOTIFICATION = "send_support_notification"


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def listing_snapshot(items):
    return {role: item.model_dump(mode="json") for role, item in items.items()}


def rules_total(items):
    return sum((p.price_tnd for p in items.values() if p.price_tnd is not None), Decimal(0))


def proposal_matches(case, revision, proposal_hash):
    proposal = case["proposal"]
    return (proposal is not None and revision == case["revision"]
            and proposal_hash == proposal["hash"]
            and _hash({key: value for key, value in proposal.items() if key != "hash"}) == proposal_hash)


def prepare_proposal(case, items, findings, status):
    plan = SetupPlan.model_validate(case["setup"]) if case.get("setup") else None
    quantities = {line.id: line.quantity for line in plan.items if not line.owned} if plan else dict.fromkeys(items, 1)
    order = canonical_action_payload(ORDER, {
        "customer_id": case["customer_id"],
        "items": [{"product_id": item.product_id, "name": item.name,
                   "quantity": quantities[key], "source_url": item.source_url, "unit_price_tnd": item.price_tnd}
                  for key, item in items.items() if key in quantities],
        "total_tnd": setup_total(plan, items) if plan else rules_total(items),
        "source_evidence_ids": [items[key].product_id for key in quantities],
    })
    notice = canonical_action_payload(NOTIFICATION, {
        "customer_id": case["customer_id"], "channel": "sandbox_outbox",
        "message": f"Your approved sandbox order totals {order['total_tnd']} TND.",
    })
    operation = str(uuid4())
    proposal = {
        "revision": case["revision"], "run_id": case["run_id"],
        "evidence": listing_snapshot(items), "findings": [f.model_dump() for f in findings],
        "actions": [
            {"action": ORDER, "operation_id": operation, "payload": order},
            {"action": NOTIFICATION, "operation_id": operation + ":notification", "payload": notice},
        ],
    }
    if plan:
        proposal["setup"] = plan.model_dump(mode="json")
    proposal["hash"] = _hash(proposal)
    case.update(status=status, proposal=proposal, findings=proposal["findings"], approval=None)
    record_event(case, "coordinator", "prepare_proposal", {"hash": proposal["hash"], "status": status})
