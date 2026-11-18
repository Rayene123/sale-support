"""Record a human decision for the current immutable purchasing proposal."""

import time

from specialist.contracts.validation import validate_identifier

from .case_state import APPROVABLE, CaseConflict
from .proposals import proposal_matches
from .steps import record_event


APPROVAL_MAX_AGE_S = 15 * 60


def record_decision(store, case_id, customer_id, *, reviewer_id, revision, proposal_hash, decision):
    """The reviewer identity must come from authenticated server context."""
    validate_identifier(reviewer_id)
    if reviewer_id == customer_id or decision not in {"approve", "reject", "timeout"}:
        raise CaseConflict("Invalid reviewer or decision")
    with store.update(case_id, customer_id) as case:
        if case["status"] not in APPROVABLE or not proposal_matches(case, revision, proposal_hash):
            raise CaseConflict("Decision is not for the current exact proposal")
        if decision == "approve":
            case["approval"] = {"reviewer_id": reviewer_id, "revision": revision,
                                "hash": proposal_hash, "expires_at": time.time() + APPROVAL_MAX_AGE_S}
        case["status"] = {"approve": "approved", "reject": "rejected", "timeout": "timed_out"}[decision]
        record_event(case, "reviewer", "record_decision", {"decision": decision, "hash": proposal_hash})
        return case
