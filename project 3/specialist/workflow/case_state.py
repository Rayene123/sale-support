"""Shared case transitions and the states exposed to the workbench."""

from copy import deepcopy
from uuid import uuid4


MAX_REVISIONS = 8
APPROVABLE = {"awaiting_approval", "reapproval_required"}
EXECUTABLE = {"approved", "partially_completed", "reconciliation_required"}
TERMINAL = {"completed", "rejected", "timed_out"}
FOLLOW_UP = {"awaiting_clarification", "awaiting_approval", "verification_blocked",
             "reapproval_required", "planner_unavailable", "source_unavailable"}


class CaseConflict(ValueError):
    """A submitted command does not apply to the current case."""


def can_revise(case):
    return not (case["receipts"] or case["attempted"] or case["status"] in TERMINAL | EXECUTABLE)


def advance_revision(case):
    if case["revision"] >= MAX_REVISIONS:
        raise CaseConflict("Case reached its revision limit")
    case["history"].append({key: deepcopy(case[key]) for key in
                            ("revision", "run_id", "requirements", "setup", "proposal", "approval", "status") if key in case})
    case.update(revision=case["revision"] + 1, run_id=str(uuid4()), status="research_pending",
                proposal=None, approval=None, findings=[], alternatives=[], candidate=None)
