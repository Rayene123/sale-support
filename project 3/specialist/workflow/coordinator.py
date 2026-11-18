"""Coordinator for a bounded, persistent evidence-based purchase case."""

from __future__ import annotations

import time
from uuid import uuid4

from specialist.catalog.research import Researcher
from specialist.contracts.purchasing import Mode, Requirements, read_requirements
from specialist.contracts.setup import SetupPlan
from specialist.contracts.validation import validate_identifier
from specialist.observability import model_attempt

from .approval import record_decision
from .case_state import CaseConflict, advance_revision, can_revise
from .execution import execute_next
from .planner import ModelUnavailable, OllamaPlanner
from .planning import read_plan_findings
from .research_rules import research_rules
from .research_setup import research_setup
from .steps import BudgetExhausted, SourceBlocked, charge_step, record_event, case_requirements
from .store import CaseStore


MODES = {"fixed", "adaptive", "adaptive_verifier"}


class Specialist:
    """Call with authenticated server identities. Does not authenticate users itself."""

    def __init__(self, store: CaseStore, researcher: Researcher | None = None, *,
                 writer=None, step_limit: int = 96, mode: Mode = "adaptive_verifier", planner=None,
                 record_customer_message: bool = False):
        if mode not in MODES or not 1 <= step_limit <= 256:
            raise ValueError("Unsupported mode or step limit")
        self.store = store
        self.researcher = researcher or Researcher.tunisianet()
        self.writer = writer
        self.step_limit = step_limit
        self.mode = mode
        self.planner = planner
        self.record_customer_message = record_customer_message

    @classmethod
    def with_local_model(cls, store, researcher=None, *, writer=None, step_limit=96, record_customer_message=False):
        """Server entry point for free-form purchasing requests."""
        return cls(store, researcher, writer=writer, step_limit=step_limit, planner=OllamaPlanner.from_env(),
                   record_customer_message=record_customer_message)

    def start(self, customer_id: str, text: str) -> dict:
        validate_identifier(customer_id)
        if self.planner and self.mode != "adaptive_verifier":
            raise ValueError("The hybrid planner requires independent verification")
        requirements = Requirements() if self.planner else read_requirements(text)
        case = {
            "case_id": str(uuid4()), "run_id": str(uuid4()), "customer_id": customer_id,
            "revision": 1, "status": "research_pending", "mode": self.mode,
            "requirements": requirements.model_dump(mode="json"),
            "steps": 0, "step_limit": self.step_limit, "evidence": {},
            "trajectory": [], "history": [], "proposal": None, "findings": [],
            "alternatives": [], "approval": None, "receipts": {}, "attempted": [],
            "changes": [],
        }
        if self.planner:
            case["planner_kind"] = "hybrid"
            self._interpret(case, text)
        if self.record_customer_message:
            case["customer_message"] = text.strip()
        self.store.insert(case)
        if case["status"] == "research_pending":
            return self.research(case["case_id"], customer_id)
        return case

    def research(self, case_id, customer_id):
        with self.store.update(case_id, customer_id) as case:
            if case["status"] != "research_pending":
                raise CaseConflict("Case is not pending research")
            self._research(case)
            return case

    def revise(self, case_id, customer_id, text, *, expected_revision: int):
        with self.store.update(case_id, customer_id) as case:
            if expected_revision != case["revision"] or not can_revise(case):
                raise CaseConflict("Case revision changed or execution already started")
            if case.get("planner_kind") == "hybrid":
                previous = SetupPlan.model_validate(case["setup"]) if case.get("setup") else None
                advance_revision(case)
                case["changes"] = []
                self._interpret(case, text, previous)
                if case["status"] == "research_pending":
                    self._research(case)
            else:
                requirements = read_requirements(text, case_requirements(case))
                advance_revision(case)
                case.update(requirements=requirements.model_dump(mode="json"), changes=[])
                self._research(case)
            if self.record_customer_message:
                case["customer_message"] = text.strip()
            return case

    def _interpret(self, case, text, previous=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 1200:
            raise ValueError("Enter a purchasing request of 1 to 1200 characters")
        started = time.perf_counter()
        try:
            charge_step(case)
            if self.planner is None:
                raise ModelUnavailable("Planner not configured")
            model_attempt()
            plan = SetupPlan.model_validate(self.planner.plan(text, previous))
            problems = read_plan_findings(plan, text, previous)
            # Retain the previous plan as the revision anchor if the model
            # dropped a constraint. A malformed plan must not become memory.
            if not problems:
                case["setup"] = plan.model_dump(mode="json")
            case["questions"] = plan.missing() + problems
            status = "awaiting_clarification" if case["questions"] else "research_pending"
            case["status"] = status
            record_event(case, "planner", "interpret_setup",
                   {"items": len(plan.items), "relationships": len(plan.links), "status": status}, started=started)
        except ModelUnavailable:
            case.update(status="planner_unavailable", questions=["The purchasing model could not interpret this request."])
            record_event(case, "planner", "planner_unavailable", {}, started=started)
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            record_event(case, "coordinator", "stop_budget", {})

    def _research(self, case):
        search = research_setup if case.get("planner_kind") == "hybrid" else research_rules
        try:
            search(case, self.researcher)
        except SourceBlocked:
            case["status"] = "source_unavailable"
            record_event(case, "coordinator", "stop_source_blocked", {})
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            record_event(case, "coordinator", "stop_budget", {})

    def decide(self, case_id, customer_id, *, reviewer_id, revision, proposal_hash, decision):
        return record_decision(self.store, case_id, customer_id, reviewer_id=reviewer_id,
                               revision=revision, proposal_hash=proposal_hash, decision=decision)

    def execute_next(self, case_id, customer_id, *, expected_revision=None, expected_hash=None):
        return execute_next(self.store, self.researcher, self.writer, case_id, customer_id,
                            expected_revision=expected_revision, expected_hash=expected_hash)
