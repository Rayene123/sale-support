"""Coordinator for a bounded, persistent evidence-based purchase case."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from itertools import product
import json
import time
from uuid import uuid4

from agent.observability import capture_event, model_attempt
from agent.tools.payloads import canonical_action_payload
from agent.tools.schemas import validate_identifier
from .contracts import Finding, Listing, Mode, Requirements, read_requirements
from .research import Researcher, matches_role
from .store import CaseStore
from .verify import verify_bundle
from .setup import SetupPlan
from .setup_research import candidates_in_price_order, cached_matches, matches_line, read_plan_findings
from .setup_verify import total as setup_total, verify_setup
from .planner import ModelUnavailable, OllamaPlanner

MODES = {"fixed", "adaptive", "adaptive_verifier"}
ORDER = "create_customer_order"
NOTIFICATION = "send_support_notification"
MAX_REVISIONS = 8
MAX_VERIFICATIONS = 18
EVIDENCE_MAX_AGE_S = 15 * 60
APPROVAL_MAX_AGE_S = 15 * 60
TERMINAL = {"completed", "rejected", "timed_out"}


class BudgetExhausted(RuntimeError):
    pass


class SourceBlocked(RuntimeError):
    pass


class CaseConflict(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _requirements(case):
    return Requirements.model_validate(case["requirements"])


def _items(value):
    return {role: Listing.model_validate(item) for role, item in value.items()}


def _is_fresh(item: Listing) -> bool:
    try:
        observed = datetime.fromisoformat(item.fetched_at.replace("Z", "+00:00"))
        return 0 <= (_now() - observed).total_seconds() <= EVIDENCE_MAX_AGE_S
    except (TypeError, ValueError):
        return False


def _event(case, actor, name, detail, *, started=None):
    case["trajectory"].append({
        "case_id": case["case_id"], "run_id": case["run_id"],
        "revision": case["revision"], "actor": actor, "action": name,
        "detail": detail, "at": _now().isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2) if started is not None else 0,
        "remaining_steps": case["step_limit"] - case["steps"],
    })
    capture_event(case["trajectory"][-1])


def _charge(case):
    if case["steps"] >= case["step_limit"]:
        raise BudgetExhausted
    case["steps"] += 1


def _call(case, actor, action, info, invoke):
    _charge(case)
    started = time.perf_counter()
    try:
        result = invoke()
    except Exception:
        result = {"success": False, "error": "tool_call_failed"}
    if not isinstance(result, dict):
        result = {"success": False, "error": "invalid_tool_response"}
    error = result.get("error") if result.get("success") is not True else None
    code = error if error in ("invalid_product_source", "robots_disallowed", "source_blocked",
        "product_identity_unknown", "source_timeout", "source_unavailable", "invalid_product_evidence") else "tool_call_failed"
    _event(case, actor, action, {**info, "outcome": code if error else "ok"}, started=started)
    if error == "source_blocked":
        raise SourceBlocked
    return result


def _verify(case, items):
    _charge(case)
    started = time.perf_counter()
    findings = verify_setup(SetupPlan.model_validate(case["setup"]), items) if case.get("setup") else verify_bundle(_requirements(case), items)
    stale = [item.product_id for item in items.values() if not _is_fresh(item)]
    if stale:
        findings.append(Finding(code="evidence_freshness", verdict="unknown",
                                reason="An exact listing is stale or lacks a valid timestamp"))
    _event(case, "verifier", "check_candidate",
           {"products": [p.product_id for p in items.values()],
            "findings": [{"code": f.code, "verdict": f.verdict} for f in findings]}, started=started)
    return findings


def _snapshot(items):
    return {role: item.model_dump(mode="json") for role, item in items.items()}


def _total(items):
    return sum((p.price_tnd for p in items.values() if p.price_tnd is not None), Decimal(0))


class Specialist:
    """Call with authenticated server identities. Does not authenticate users itself."""

    def __init__(self, store: CaseStore, researcher: Researcher | None = None, *,
                 writer=None, step_limit: int = 96, mode: Mode = "adaptive_verifier", planner=None):
        if mode not in MODES or not 1 <= step_limit <= 256:
            raise ValueError("Unsupported mode or step limit")
        self.store = store
        self.researcher = researcher or Researcher.tunisianet()
        self.writer = writer
        self.step_limit = step_limit
        self.mode = mode
        self.planner = planner

    @classmethod
    def with_local_model(cls, store, researcher=None, *, writer=None, step_limit=96):
        """Server entry point for free-form purchasing requests."""
        return cls(store, researcher, writer=writer, step_limit=step_limit, planner=OllamaPlanner.from_env())

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
            if (expected_revision != case["revision"] or case["receipts"] or case["attempted"]
                    or case["status"] in TERMINAL | {"approved", "partially_completed", "reconciliation_required"}):
                raise CaseConflict("Case revision changed or execution already started")
            if case.get("planner_kind") == "hybrid":
                previous = SetupPlan.model_validate(case["setup"]) if case.get("setup") else None
                self._advance(case)
                case["changes"] = []
                self._interpret(case, text, previous)
                if case["status"] == "research_pending":
                    self._research(case)
            else:
                requirements = read_requirements(text, _requirements(case))
                self._advance(case)
                case.update(requirements=requirements.model_dump(mode="json"), changes=[])
                self._research(case)
            return case

    def _interpret(self, case, text, previous=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 1200:
            raise ValueError("Enter a purchasing request of 1 to 1200 characters")
        started = time.perf_counter()
        try:
            _charge(case)
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
            _event(case, "planner", "interpret_setup",
                   {"items": len(plan.items), "relationships": len(plan.links), "status": status}, started=started)
        except ModelUnavailable:
            case.update(status="planner_unavailable", questions=["The purchasing model could not interpret this request."])
            _event(case, "planner", "planner_unavailable", {}, started=started)
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            _event(case, "coordinator", "stop_budget", {})

    @staticmethod
    def _advance(case):
        if case["revision"] >= MAX_REVISIONS:
            raise CaseConflict("Case reached its revision limit")
        case["history"].append({key: deepcopy(case[key]) for key in
                                ("revision", "run_id", "requirements", "setup", "proposal", "approval", "status") if key in case})
        case.update(revision=case["revision"] + 1, run_id=str(uuid4()), status="research_pending",
                    proposal=None, approval=None, findings=[], alternatives=[], candidate=None)

    def _research(self, case):
        if case.get("planner_kind") == "hybrid":
            self._research_setup(case)
            return
        requirements = _requirements(case)
        try:
            _charge(case)
            if requirements.unanswered:
                case["status"] = "awaiting_clarification"
                _event(case, "coordinator", "ask_clarification", {"questions": requirements.unanswered})
                return
            mode = case["mode"]
            available = {role: [] for role in requirements.items}
            seen = {role: set() for role in requirements.items}
            evaluations = 0
            evaluated = set()
            checked = []
            call = lambda role, operation, info, fn: _call(case, role, operation, info, fn)
            rounds = 1 if mode == "fixed" else 2
            detail_limit = 1 if mode == "fixed" else 3
            for attempt in range(rounds):
                if attempt:
                    if mode == "adaptive" and any(row[3] for row in checked):
                        break
                    _event(case, "coordinator", "broaden_research", {"reason": "No verified setup yet"})
                for role in requirements.items:
                    if attempt == 0 and mode != "fixed":
                        cached = [Listing.model_validate(item) for item in case["evidence"].get(role, [])]
                        available[role] = [item for item in cached if _is_fresh(item)]
                        seen[role].update(item.product_id for item in available[role])
                        if available[role]:
                            _event(case, "researcher", "reuse_evidence", {"role": role, "count": len(available[role])})
                            continue
                    listings = self.researcher.candidates(role, attempt, call)
                    for seed in [p for p in listings if p.product_id not in seen[role]][:detail_limit]:
                        seen[role].add(seed.product_id)
                        item = self.researcher.detail(seed, call)
                        if item is not None and matches_role(item, role):
                            available[role].append(item)
                    case["evidence"][role] = [p.model_dump(mode="json") for p in available[role]]
                if not all(available.values()):
                    continue
                combinations = [dict(zip(requirements.items, combination))
                                for combination in product(*available.values())]
                combinations.sort(key=lambda items: _total(items))
                for items in combinations:
                    identity = tuple(item.product_id for item in items.values())
                    if identity in evaluated or evaluations >= MAX_VERIFICATIONS:
                        continue
                    evaluations += 1
                    evaluated.add(identity)
                    if mode == "adaptive_verifier":
                        findings = _verify(case, items)
                        verified = all(finding.verdict == "pass" for finding in findings)
                        eligible = verified
                    else:
                        _charge(case)
                        findings = verify_bundle(requirements, items, check_connection=False)
                        eligible = (all(finding.verdict == "pass" for finding in findings)
                                    and all(_is_fresh(item) for item in items.values()))
                        verified = False
                        _event(case, "researcher", "filter_candidate", {"eligible": eligible})
                    checked.append((items, findings, verified, eligible))
                if any(row[3] for row in checked):
                    break
            best = next((row for row in sorted(checked, key=lambda row: _total(row[0]))
                         if row[2]), None)
            case["alternatives"] = [
                {"items": _snapshot(items), "total_tnd": str(_total(items)) if all(
                    item.price_tnd is not None for item in items.values()) else None,
                 "verdict": "pass" if verified else ("fail" if any(f.verdict == "fail" for f in findings) else "unknown"),
                 "findings": [f.model_dump() for f in findings]}
                for items, findings, verified, _ in checked[:MAX_VERIFICATIONS]
            ]
            if best:
                self._propose(case, best[0], best[1], "awaiting_approval")
            elif mode != "adaptive_verifier":
                # Baselines produce a candidate for scoring, never a writable proposal.
                baseline = next((row for row in checked if row[3]), None)
                case.update(status="baseline_candidate" if baseline else "verification_blocked",
                            candidate=_snapshot(baseline[0]) if baseline else None)
            else:
                case["status"] = "verification_blocked"
                case["findings"] = ([f.model_dump() for f in checked[0][1]] if checked else
                    [Finding(code="required_evidence", verdict="unknown",
                             reason="Exact catalog evidence was unavailable for all required products").model_dump()])
                _event(case, "coordinator", "stop_unverified", {"reason": "No independently verified setup"})
        except SourceBlocked:
            case["status"] = "source_unavailable"
            _event(case, "coordinator", "stop_source_blocked", {})
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            _event(case, "coordinator", "stop_budget", {})

    def _research_setup(self, case):
        plan = SetupPlan.model_validate(case["setup"])
        call = lambda actor, action, info, fn: _call(case, actor, action, info, fn)
        available = {line.id: cached_matches(line, case["evidence"].get(line.id, []), _is_fresh)
                     for line in plan.items}
        queries = {line.id: self.researcher.queries_for(line) for line in plan.items}
        seen = {line_id: {item.product_id for item in items} for line_id, items in available.items()}
        evaluated = set()
        rejected = []
        try:
            _charge(case)
            for attempt in range(2):
                if attempt:
                    _charge(case)
                    _event(case, "coordinator", "broaden_research",
                           {"reason": "The first results did not verify the complete setup"})
                for line in plan.items:
                    if attempt == 0 and available[line.id]:
                        _event(case, "researcher", "reuse_evidence", {"line": line.id})
                        continue
                    line_queries = queries[line.id]
                    if attempt >= len(line_queries):
                        continue
                    seeds = self.researcher.search_line(line, line_queries[attempt], call)
                    for seed in [item for item in seeds if item.product_id not in seen[line.id]][:2]:
                        seen[line.id].add(seed.product_id)
                        detail = self.researcher.detail(seed, call)
                        if detail is not None and matches_line(detail, line):
                            available[line.id].append(detail)
                    case["evidence"][line.id] = [row.model_dump(mode="json") for row in available[line.id]]
                if not all(available.values()):
                    continue
                # Keep room to inspect alternatives after a failed first round.
                for items in candidates_in_price_order(plan, available, limit=MAX_VERIFICATIONS):
                    if len(evaluated) >= MAX_VERIFICATIONS or (attempt == 0 and len(evaluated) >= 8):
                        break
                    key = tuple(item.product_id for item in items.values())
                    if key in evaluated:
                        continue
                    evaluated.add(key)
                    findings = _verify(case, items)
                    if all(f.verdict == "pass" for f in findings):
                        case["alternatives"] = rejected
                        self._propose(case, items, findings, "awaiting_approval")
                        return
                    rejected.append({"items": _snapshot(items), "verdict": "fail" if any(
                        f.verdict == "fail" for f in findings) else "unknown",
                        "findings": [f.model_dump() for f in findings]})
            missing = [line for line, rows in available.items() if not rows]
            case["findings"] = rejected[0]["findings"] if rejected else [
                Finding(code="listing_unverified", verdict="unknown",
                        reason=f"Could not verify an exact catalog listing for {line}").model_dump()
                for line in missing
            ]
            case.update(status="verification_blocked", alternatives=rejected)
            _event(case, "coordinator", "stop_unverified", {"missing_lines": missing})
        except SourceBlocked:
            case["status"] = "source_unavailable"
            _event(case, "coordinator", "stop_source_blocked", {})
        except BudgetExhausted:
            case["status"] = "step_limit_reached"
            _event(case, "coordinator", "stop_budget", {})

    @staticmethod
    def _propose(case, items, findings, status):
        plan = SetupPlan.model_validate(case["setup"]) if case.get("setup") else None
        quantities = {line.id: line.quantity for line in plan.items if not line.owned} if plan else dict.fromkeys(items, 1)
        order = canonical_action_payload(ORDER, {
            "customer_id": case["customer_id"],
            "items": [{"product_id": item.product_id, "name": item.name,
                       "quantity": quantities[key], "source_url": item.source_url, "unit_price_tnd": item.price_tnd}
                      for key, item in items.items() if key in quantities],
            "total_tnd": setup_total(plan, items) if plan else _total(items),
            "source_evidence_ids": [items[key].product_id for key in quantities],
        })
        notice = canonical_action_payload(NOTIFICATION, {
            "customer_id": case["customer_id"], "channel": "sandbox_outbox",
            "message": f"Your approved sandbox order totals {order['total_tnd']} TND.",
        })
        operation = str(uuid4())
        proposal = {
            "revision": case["revision"], "run_id": case["run_id"],
            "evidence": _snapshot(items), "findings": [f.model_dump() for f in findings],
            "actions": [
                {"action": ORDER, "operation_id": operation, "payload": order},
                {"action": NOTIFICATION, "operation_id": operation + ":notification", "payload": notice},
            ],
        }
        if plan:
            proposal["setup"] = plan.model_dump(mode="json")
        proposal["hash"] = _hash(proposal)
        case.update(status=status, proposal=proposal, findings=proposal["findings"], approval=None)
        _event(case, "coordinator", "prepare_proposal", {"hash": proposal["hash"], "status": status})

    def decide(self, case_id, customer_id, *, reviewer_id, revision, proposal_hash, decision):
        """The reviewer identity must come from authenticated server context."""
        validate_identifier(reviewer_id)
        if reviewer_id == customer_id or decision not in {"approve", "reject", "timeout"}:
            raise CaseConflict("Invalid reviewer or decision")
        with self.store.update(case_id, customer_id) as case:
            proposal = case["proposal"]
            if (case["status"] not in {"awaiting_approval", "reapproval_required"} or not proposal
                    or revision != case["revision"] or proposal_hash != proposal["hash"]
                    or _hash({k: v for k, v in proposal.items() if k != "hash"}) != proposal_hash):
                raise CaseConflict("Decision is not for the current exact proposal")
            if decision == "approve":
                case["approval"] = {"reviewer_id": reviewer_id, "revision": revision,
                                    "hash": proposal_hash, "expires_at": time.time() + APPROVAL_MAX_AGE_S}
            case["status"] = {"approve": "approved", "reject": "rejected", "timeout": "timed_out"}[decision]
            _event(case, "reviewer", "record_decision", {"decision": decision, "hash": proposal_hash})
            return case

    def execute_next(self, case_id, customer_id, *, expected_revision=None, expected_hash=None):
        """Resume one approved action. The writer must supply durable receipt lookup."""
        if self.writer is None:
            raise CaseConflict("No trusted sandbox writer is configured")
        with self.store.update(case_id, customer_id) as case:
            proposal = case["proposal"]
            if expected_revision is not None and (case["revision"] != expected_revision
                    or not proposal or proposal["hash"] != expected_hash):
                raise CaseConflict("Execution is not for the current exact proposal")
            if case["status"] == "completed":
                return case
            if case["status"] not in {"approved", "partially_completed", "reconciliation_required"}:
                raise CaseConflict("Execution requires current approval")
            approval = case["approval"]
            if (not proposal or not approval or approval["revision"] != case["revision"]
                    or approval["hash"] != proposal["hash"]
                    or _hash({k: v for k, v in proposal.items() if k != "hash"}) != approval["hash"]):
                raise CaseConflict("Approval does not match the stored proposal")
            try:
                action = next(a for a in proposal["actions"] if a["operation_id"] not in case["receipts"])
                operation_id = action["operation_id"]
                if operation_id in case["attempted"]:
                    _charge(case)
                    try:
                        receipt = self.writer.receipt(action, proposal["run_id"])
                    except Exception:
                        case["status"] = "reconciliation_required"
                        _event(case, "coordinator", "receipt_unavailable", {"operation_id": operation_id})
                        return case
                    if receipt is not None:
                        try:
                            self._record(case, action, receipt)
                        except ValueError:
                            case["status"] = "reconciliation_required"
                            _event(case, "coordinator", "receipt_invalid", {"operation_id": operation_id})
                        return case
                if time.time() >= approval["expires_at"]:
                    case["status"] = "timed_out"
                    _event(case, "coordinator", "expire_approval", {"receipts_preserved": len(case["receipts"])})
                    return case
                if action["action"] == ORDER and not self._refresh(case):
                    return case
                # Commit the intent before an external write, so a restarted process
                # checks for a receipt even if the RPC committed after our last save.
                _charge(case)
                if operation_id not in case["attempted"]:
                    case["attempted"].append(operation_id)
                _event(case, "coordinator", "reserve_write", {"operation_id": operation_id})
                reserved_run = proposal["run_id"]
            except SourceBlocked:
                case.update(status="source_unavailable", approval=None, attempted=[])
                _event(case, "coordinator", "stop_source_blocked", {})
                return case
            except BudgetExhausted:
                case["status"] = "step_limit_reached"
                _event(case, "coordinator", "stop_budget", {"receipts_preserved": len(case["receipts"])})
                return case

        with self.store.update(case_id, customer_id) as case:
            # A concurrent worker may already have received this exact operation.
            if (case["run_id"] != reserved_run or operation_id in case["receipts"]
                    or case["status"] not in {"approved", "partially_completed", "reconciliation_required"}):
                return case
            if time.time() >= case["approval"]["expires_at"]:
                case["status"] = "timed_out"
                return case
            started = time.perf_counter()
            try:
                receipt = self.writer.apply(action, reserved_run, case["approval"])
                self._record(case, action, receipt, started=started)
            except Exception:
                case["status"] = "partially_completed" if case["receipts"] else "reconciliation_required"
                _event(case, "sandbox", "write_unconfirmed", {"operation_id": operation_id}, started=started)
            return case

    @staticmethod
    def _record(case, action, receipt, *, started=None):
        operation = action["operation_id"]
        if not isinstance(receipt, dict) or receipt.get("success") is not True or receipt.get("operation_id") != operation:
            raise ValueError("Sandbox response was not a matching receipt")
        case["receipts"][operation] = receipt
        case["status"] = "completed" if len(case["receipts"]) == len(case["proposal"]["actions"]) else "partially_completed"
        _event(case, "sandbox", "receipt_confirmed", {"action": action["action"], "operation_id": operation}, started=started)

    def _refresh(self, case):
        old = _items(case["proposal"]["evidence"])
        lines = {line.id: line for line in SetupPlan.model_validate(case["setup"]).items} if case.get("setup") else {}
        fresh = {}
        changes = []
        for role, item in old.items():
            value = self.researcher.detail(item, lambda actor, action, info, fn: _call(case, actor, action, info, fn))
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
        findings = _verify(case, fresh)
        verified = all(f.verdict == "pass" for f in findings)
        if changes or not verified:
            # This branch is reached only after proving that no write was persisted.
            case["attempted"] = []
            if case["revision"] >= MAX_REVISIONS:
                case.update(status="verification_blocked", approval=None, changes=changes,
                            findings=[f.model_dump() for f in findings])
                return False
            self._advance(case)
            case["changes"] = changes
            _event(case, "coordinator", "invalidate_approval", {"changes": changes})
            if verified:
                self._propose(case, fresh, findings, "reapproval_required")
            else:
                case.update(status="verification_blocked", findings=[f.model_dump() for f in findings])
            for role, item in old.items():
                kept = [p for p in case["evidence"].get(role, []) if p["product_id"] != item.product_id]
                if role in fresh:
                    kept.append(fresh[role].model_dump(mode="json"))
                case["evidence"][role] = kept
            return False
        return True
