"""Research and rank bounded combinations from a model-generated setup."""

from decimal import Decimal
from heapq import heappop, heappush

from specialist.catalog.research import matches_line
from specialist.contracts.purchasing import Finding, Listing
from specialist.contracts.setup import SetupPlan, setup_total

from .proposals import listing_snapshot, prepare_proposal
from .steps import MAX_VERIFICATIONS, call_tool, charge_step, record_event, is_fresh, verify_candidate


def research_setup(case, researcher):
    plan = SetupPlan.model_validate(case["setup"])
    call = lambda actor, action, info, fn: call_tool(case, actor, action, info, fn)
    available = {line.id: cached_matches(line, case["evidence"].get(line.id, []), is_fresh)
                 for line in plan.items}
    queries = {line.id: researcher.queries_for(line) for line in plan.items}
    seen = {line_id: {item.product_id for item in items} for line_id, items in available.items()}
    evaluated = set()
    rejected = []
    charge_step(case)
    for attempt in range(2):
        if attempt:
            charge_step(case)
            record_event(case, "coordinator", "broaden_research",
                   {"reason": "The first results did not verify the complete setup"})
        for line in plan.items:
            if attempt == 0 and available[line.id]:
                record_event(case, "researcher", "reuse_evidence", {"line": line.id})
                continue
            line_queries = queries[line.id]
            if attempt >= len(line_queries):
                continue
            seeds = researcher.search_line(line, line_queries[attempt], call)
            available[line.id].extend(researcher.inspect_candidates(
                seeds, lambda listing: matches_line(listing, line), seen[line.id], 2, call))
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
            findings = verify_candidate(case, items)
            if all(f.verdict == "pass" for f in findings):
                case["alternatives"] = rejected
                prepare_proposal(case, items, findings, "awaiting_approval")
                return
            rejected.append({"items": listing_snapshot(items), "verdict": "fail" if any(
                f.verdict == "fail" for f in findings) else "unknown",
                "findings": [f.model_dump() for f in findings]})
    missing = [line for line, rows in available.items() if not rows]
    case["findings"] = rejected[0]["findings"] if rejected else [
        Finding(code="listing_unverified", verdict="unknown",
                reason=f"Could not verify an exact catalog listing for {line}").model_dump()
        for line in missing
    ]
    case.update(status="verification_blocked", alternatives=rejected)
    record_event(case, "coordinator", "stop_unverified", {"missing_lines": missing})


def candidates_in_price_order(plan, available, *, limit):
    """Yield the cheapest combinations without building the full Cartesian product."""
    lines = plan.items
    rows = [
        sorted(available[line.id],
               key=lambda item: item.price_tnd if item.price_tnd is not None and not line.owned else Decimal(0))
        for line in lines
    ]

    def selection(indices):
        return {line.id: rows[i][index] for i, (line, index) in enumerate(zip(lines, indices))}

    zero = tuple(0 for _ in lines)
    visited = {zero}
    heap = [(setup_total(plan, selection(zero)) or Decimal(0), zero)]
    for _ in range(limit):
        if not heap:
            return
        _, indices = heappop(heap)
        yield selection(indices)
        for i, index in enumerate(indices):
            if index + 1 == len(rows[i]):
                continue
            next_index = indices[:i] + (index + 1,) + indices[i+1:]
            if next_index not in visited:
                visited.add(next_index)
                heappush(heap, (setup_total(plan, selection(next_index)) or Decimal(0), next_index))


def cached_matches(line, cached, fresh):
    return [row for fields in cached if fresh(row := Listing.model_validate(fields)) and matches_line(row, line)]
