"""Coordinator for a bounded, persistent evidence-based purchase case."""

from __future__ import annotations

from decimal import Decimal
import re
import time
from uuid import uuid4

from specialist.catalog.research import Researcher, matches_line
from specialist.contracts.purchasing import Mode, Requirements, read_requirements
from specialist.contracts.setup import SetupPlan
from specialist.contracts.validation import validate_identifier
from specialist.observability import model_attempt

from .approval import record_decision
from .cancellation import check_cancelled
from .case_state import CaseConflict, advance_revision, can_revise
from .execution import execute_next, refresh_proposal
from .planner import ModelUnavailable, OllamaPlanner
from .planning import read_plan_findings
from .proposals import proposal_matches
from .research_rules import research_rules
from .research_setup import research_setup
from .shopping_intent import (
    carry_requirements, direct_budget_revision, enforce_standalone, lock_requested_items,
    reference_kind, retailer_reference, requests_checkout, wants_battery,
)
from .steps import BudgetExhausted, SourceBlocked, call_tool, charge_step, record_event, case_requirements
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
        if self.record_customer_message:
            case["customer_message"] = text.strip()
            case["shop_policy"] = True
        if self.planner:
            case["planner_kind"] = "hybrid"
            self._interpret(case, text)
        if self.record_customer_message and case["status"] == "research_pending":
            self._research(case)
        check_cancelled()
        self.store.insert(case)
        if case["status"] == "research_pending":
            return self.research(case["case_id"], customer_id)
        return case

    def research(self, case_id, customer_id):
        with self.store.update(case_id, customer_id) as case:
            if case["status"] != "research_pending":
                raise CaseConflict("Case is not pending research")
            self._research(case)
            check_cancelled()
            return case

    def revise(self, case_id, customer_id, text, *, expected_revision: int):
        with self.store.update(case_id, customer_id) as case:
            if expected_revision != case["revision"] or not can_revise(case):
                raise CaseConflict("Case revision changed or execution already started")
            if self.record_customer_message and case.get("proposal") and requests_checkout(text):
                check_cancelled()
                case["shop_checkout_request"] = text.strip()
                rows = case["proposal"]["actions"][0]["payload"]["items"]
                noun = "listing" if len(rows) == 1 else "listings"
                case["shop_notice"] = f"Open the {noun} below to place your order on Tunisianet."
                return case
            case.pop("shop_checkout_request", None)
            case.pop("shop_notice", None)
            if case.get("planner_kind") == "hybrid":
                previous = SetupPlan.model_validate(case["setup"]) if case.get("setup") else None
                prior_proposal = case["proposal"]
                advance_revision(case)
                case["changes"] = []
                self._interpret(case, text, previous, prior_proposal)
                if case["status"] == "research_pending":
                    self._research(case)
            else:
                requirements = read_requirements(text, case_requirements(case))
                advance_revision(case)
                case.update(requirements=requirements.model_dump(mode="json"), changes=[])
                self._research(case)
            if self.record_customer_message:
                case["customer_message"] = text.strip()
            check_cancelled()
            return case

    def _interpret(self, case, text, previous=None, prior_proposal=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 1200:
            raise ValueError("Enter a purchasing request of 1 to 1200 characters")
        started = time.perf_counter()
        try:
            charge_step(case)
            if self.planner is None:
                raise ModelUnavailable("Planner not configured")
            reference = None
            if self.record_customer_message:
                case["shop_policy"] = True
                case.pop("shop_notice", None)
                case["shop_rank_battery"] = wants_battery(text)
                lock_requested_items(case, text, previous, prior_proposal)
                if linked := retailer_reference(text):
                    raw, product_id, source = linked
                    listing = self.researcher.exact_listing(product_id, source,
                        lambda actor, action, info, fn: call_tool(case, actor, action, info, fn))
                    kind = reference_kind(listing) if listing else None
                    if not listing:
                        case.update(status="awaiting_clarification",
                                    questions=["What’s the exact model of the product in your link?"])
                        return
                    label = kind.replace("_", " ") if kind else "product"
                    owned_hint = re.search(r"\b(?:already (?:own|have)|i own|i have|j’ai)\b[^.!?]{0,80}$",
                                           text[:text.index(raw)], re.I)
                    reference = (listing, kind, bool(owned_hint))
                    text = text.replace(raw, f"the {label} in my Tunisianet link")
            plan = direct_budget_revision(text, previous, prior_proposal) if self.record_customer_message else None
            if plan is None:
                model_attempt()
                plan = SetupPlan.model_validate(self.planner.plan(text, previous))
                check_cancelled()
                if self.record_customer_message:
                    plan = carry_requirements(enforce_standalone(plan, text, previous), previous, text)
            if reference:
                listing, kind, explicitly_owned = reference
                matches = [line for line in plan.items
                           if line.kind == kind or (kind is None and matches_line(
                               listing, line.model_copy(update={"exact_model": None})))]
                if len(matches) != 1:
                    case.update(status="awaiting_clarification",
                                questions=["Which product in your setup is the Tunisianet link for?"])
                    return
                line = matches[0]
                model = listing.name.split(" / ", 1)[0][:80]
                items = [item.model_copy(update={"exact_model": model, "owned": line.owned or explicitly_owned})
                         if item.id == line.id else item
                         for item in plan.items]
                plan = plan.model_copy(update={"items": items, "questions": [] if line.owned and plan.budget_tnd is not None else plan.questions})
                case.setdefault("shopping_pins", {})[line.id] = listing.model_dump(mode="json")
            problems = read_plan_findings(plan, text, previous)
            # Retain the previous plan as the revision anchor if the model
            # dropped a constraint. A malformed plan must not become memory.
            if not problems:
                case["setup"] = plan.model_dump(mode="json")
            if self.record_customer_message:
                blockers = plan.model_copy(update={"questions": []}).missing()
                case["questions"] = blockers + problems
            else:
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
        except SourceBlocked:
            case.update(status="source_unavailable", questions=[])
            record_event(case, "coordinator", "stop_source_blocked", {})

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

    def refresh_shopping(self, case_id, customer_id, *, revision, proposal_hash):
        with self.store.update(case_id, customer_id) as case:
            if not self.record_customer_message or not proposal_matches(case, revision, proposal_hash):
                raise CaseConflict("This recommendation has changed")
            before = case["proposal"]["actions"][0]["payload"]
            case.pop("shop_checkout_request", None)
            case["shop_policy"] = True
            try:
                if refresh_proposal(case, self.researcher):
                    case["shop_notice"] = "I checked again. The price and availability are the same."
                    return case
                if not case["proposal"] and case["revision"] > revision:
                    self._research(case)
            except SourceBlocked:
                case["shop_notice"] = "Tunisianet isn’t responding. Try checking again later."
                return case
            except BudgetExhausted:
                case["shop_notice"] = "I couldn’t finish rechecking. Start a new chat to try again."
                return case
            case["customer_message"] = "Recheck price and stock"
            if not case["proposal"]:
                case["shop_notice"] = "I couldn’t confirm the previous setup as shown or find a replacement that fits."
            else:
                after = case["proposal"]["actions"][0]["payload"]
                old_ids = [item["product_id"] for item in before["items"]]
                new_ids = [item["product_id"] for item in after["items"]]
                change = Decimal(after["total_tnd"]) - Decimal(before["total_tnd"])
                if old_ids != new_ids:
                    case["shop_notice"] = "The previous setup changed. I found a replacement that fits your request."
                elif change:
                    movement = "up" if change > 0 else "down"
                    delta = f"{abs(change):,.2f}".rstrip("0").rstrip(".")
                    case["shop_notice"] = f"The price went {movement} by {delta} TND."
                else:
                    case["shop_notice"] = "I’ve updated the recommendation with the latest listing details."
            return case

    def execute_next(self, case_id, customer_id, *, expected_revision=None, expected_hash=None):
        return execute_next(self.store, self.researcher, self.writer, case_id, customer_id,
                            expected_revision=expected_revision, expected_hash=expected_hash)
