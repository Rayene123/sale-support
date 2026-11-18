"""Research and rank bounded combinations from a model-generated setup."""

from decimal import Decimal
from heapq import heappop, heappush

from specialist.catalog.research import matches_line
from specialist.contracts.purchasing import Finding, Listing
from specialist.contracts.setup import SetupPlan, setup_total

from .proposals import listing_snapshot, prepare_proposal
from .shopping_intent import battery_hours
from .steps import MAX_VERIFICATIONS, call_tool, charge_step, record_event, is_fresh, verify_candidate


def research_setup(case, researcher):
    plan = SetupPlan.model_validate(case["setup"])
    call = lambda actor, action, info, fn: call_tool(case, actor, action, info, fn)
    pins = case.get("shopping_pins", {})
    excluded = case.get("shopping_excluded", {})
    available = {line.id: [item for item in cached_matches(line, case["evidence"].get(line.id, []), is_fresh)
                           if item.product_id != excluded.get(line.id)] for line in plan.items}
    query_choices = researcher.broader_queries if case.get("shop_policy") else researcher.queries_for
    queries = {line.id: query_choices(line) for line in plan.items}
    for line in plan.items:
        if line.id in pins:
            pinned = Listing.model_validate(pins[line.id])
            if matches_line(pinned, line):
                latest = next((item for item in available[line.id] if item.product_id == pinned.product_id), None)
                pinned = latest or (pinned if is_fresh(pinned) else researcher.detail(pinned, call))
                available[line.id] = [pinned] if pinned else []
                case["evidence"][line.id] = [item.model_dump(mode="json") for item in available[line.id]]
    seen = {line_id: {item.product_id for item in items} for line_id, items in available.items()}
    evaluated = set()
    rejected = []
    preferred = None
    rank_battery = case.get("shop_rank_battery")
    charge_step(case)
    rounds = 3 if case.get("shop_policy") and any(len(q) > 2 for q in queries.values()) else 2
    for attempt in range(rounds):
        if attempt:
            charge_step(case)
            record_event(case, "coordinator", "broaden_research",
                   {"reason": "The first results did not verify the complete setup"})
        for line in plan.items:
            if line.id in pins and matches_line(Listing.model_validate(pins[line.id]), line):
                continue
            if attempt == 0 and available[line.id]:
                record_event(case, "researcher", "reuse_evidence", {"line": line.id})
                continue
            line_queries = queries[line.id]
            if attempt >= len(line_queries):
                continue
            seeds = [item for item in researcher.search_line(
                line, line_queries[attempt], call, shopper=case.get("shop_policy"), budget=plan.budget_tnd)
                     if item.product_id != excluded.get(line.id)]
            available[line.id].extend(researcher.inspect_candidates(
                seeds, lambda listing: matches_line(listing, line), seen[line.id], 2, call))
            case["evidence"][line.id] = [row.model_dump(mode="json") for row in available[line.id]]
        if not all(available.values()):
            continue
        # Keep room to inspect alternatives after a failed first round.
        cap = MAX_VERIFICATIONS if attempt == rounds - 1 else 8 + attempt * 5
        for items in candidates_in_price_order(plan, available, limit=MAX_VERIFICATIONS):
            if len(evaluated) >= cap:
                break
            key = tuple(item.product_id for item in items.values())
            if key in evaluated:
                continue
            evaluated.add(key)
            findings = verify_candidate(case, items)
            if all(f.verdict == "pass" for f in findings):
                if rank_battery:
                    score = sum(battery_hours(items[line.id]) for line in plan.items
                                if not line.owned and line.kind == "laptop")
                    total = setup_total(plan, items)
                    key = (score, -(total or Decimal(0)))
                    if preferred is None or key > preferred[0]:
                        preferred = (key, items, findings)
                    continue
                case["alternatives"] = rejected
                prepare_proposal(case, items, findings, "awaiting_approval")
                return
            rejected.append({"items": listing_snapshot(items), "verdict": "fail" if any(
                f.verdict == "fail" for f in findings) else "unknown",
                "findings": [f.model_dump() for f in findings]})
    if preferred:
        case["alternatives"] = rejected
        prepare_proposal(case, preferred[1], preferred[2], "awaiting_approval")
        return
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
