"""Deterministic baseline for standalone laptop and monitor research."""

from itertools import product

from specialist.catalog.research import matches_role
from specialist.contracts.purchasing import Finding, Listing
from specialist.verification.display import verify_bundle

from .proposals import listing_snapshot, rules_total, prepare_proposal
from .steps import MAX_VERIFICATIONS, call_tool, charge_step, record_event, is_fresh, case_requirements, verify_candidate


def research_rules(case, researcher):
    requirements = case_requirements(case)
    charge_step(case)
    if requirements.unanswered:
        case["status"] = "awaiting_clarification"
        record_event(case, "coordinator", "ask_clarification", {"questions": requirements.unanswered})
        return
    mode = case["mode"]
    available = {role: [] for role in requirements.items}
    seen = {role: set() for role in requirements.items}
    evaluations = 0
    evaluated = set()
    checked = []
    call = lambda role, operation, info, fn: call_tool(case, role, operation, info, fn)
    rounds = 1 if mode == "fixed" else 2
    detail_limit = 1 if mode == "fixed" else 3
    for attempt in range(rounds):
        if attempt:
            if mode == "adaptive" and any(row[3] for row in checked):
                break
            record_event(case, "coordinator", "broaden_research", {"reason": "No verified setup yet"})
        for role in requirements.items:
            if attempt == 0 and mode != "fixed":
                cached = [Listing.model_validate(item) for item in case["evidence"].get(role, [])]
                available[role] = [item for item in cached if is_fresh(item)]
                seen[role].update(item.product_id for item in available[role])
                if available[role]:
                    record_event(case, "researcher", "reuse_evidence", {"role": role, "count": len(available[role])})
                    continue
            listings = researcher.candidates(role, attempt, call)
            available[role].extend(researcher.inspect_candidates(
                listings, lambda listing: matches_role(listing, role), seen[role], detail_limit, call))
            case["evidence"][role] = [p.model_dump(mode="json") for p in available[role]]
        if not all(available.values()):
            continue
        combinations = [dict(zip(requirements.items, combination))
                        for combination in product(*available.values())]
        combinations.sort(key=lambda items: rules_total(items))
        for items in combinations:
            identity = tuple(item.product_id for item in items.values())
            if identity in evaluated or evaluations >= MAX_VERIFICATIONS:
                continue
            evaluations += 1
            evaluated.add(identity)
            if mode == "adaptive_verifier":
                findings = verify_candidate(case, items)
                verified = all(finding.verdict == "pass" for finding in findings)
                eligible = verified
            else:
                charge_step(case)
                findings = verify_bundle(requirements, items, check_connection=False)
                eligible = (all(finding.verdict == "pass" for finding in findings)
                            and all(is_fresh(item) for item in items.values()))
                verified = False
                record_event(case, "researcher", "filter_candidate", {"eligible": eligible})
            checked.append((items, findings, verified, eligible))
        if any(row[3] for row in checked):
            break
    best = next((row for row in sorted(checked, key=lambda row: rules_total(row[0]))
                 if row[2]), None)
    case["alternatives"] = [
        {"items": listing_snapshot(items), "total_tnd": str(rules_total(items)) if all(
            item.price_tnd is not None for item in items.values()) else None,
         "verdict": "pass" if verified else ("fail" if any(f.verdict == "fail" for f in findings) else "unknown"),
         "findings": [f.model_dump() for f in findings]}
        for items, findings, verified, _ in checked[:MAX_VERIFICATIONS]
    ]
    if best:
        prepare_proposal(case, best[0], best[1], "awaiting_approval")
    elif mode != "adaptive_verifier":
        # Baselines produce a candidate for scoring, never a writable proposal.
        baseline = next((row for row in checked if row[3]), None)
        case.update(status="baseline_candidate" if baseline else "verification_blocked",
                    candidate=listing_snapshot(baseline[0]) if baseline else None)
    else:
        case["status"] = "verification_blocked"
        case["findings"] = ([f.model_dump() for f in checked[0][1]] if checked else
            [Finding(code="required_evidence", verdict="unknown",
                     reason="Exact catalog evidence was unavailable for all required products").model_dump()])
        record_event(case, "coordinator", "stop_unverified", {"reason": "No independently verified setup"})
