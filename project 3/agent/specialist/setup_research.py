"""Read plans and rank a bounded set of multi-item proposals."""
from __future__ import annotations

from heapq import heappop, heappush
from decimal import Decimal
import re

from .contracts import Listing
from .setup import KIND_NAMES
from .setup_verify import total
from .verify import _fold


_ACCESSORY = re.compile(r"^(?:support|c[aâ]ble|adaptateur|adapter|chargeur|charger|housse|sac)\b", re.I)


def matches_line(listing, line):
    kind = "[-\\s]+".join(re.escape(word) for word in re.split(r"[_-]+", line.kind))
    subject = KIND_NAMES.get(line.kind, kind)
    if not re.search(rf"\b(?:{subject})\b", _fold(listing.name)):
        return False
    if line.kind in KIND_NAMES and _ACCESSORY.match(listing.name):
        return False
    if line.exact_model:
        expected = re.findall(r"[a-z0-9]+", line.exact_model.lower())
        actual = re.findall(r"[a-z0-9]+", (listing.name + " " + " ".join(
            value for key, value in listing.specs.items()
            if key.casefold() in {"mpn", "sku", "reference", "model", "modèle"}
        )).lower())
        if not expected or not any(actual[i:i+len(expected)] == expected for i in range(len(actual))):
            return False
    return True


def read_plan_findings(plan, text, previous=None):
    """Check a few common omissions independently. The reviewer sees the entire plan."""
    problems = []
    expected = {name for name, expression in KIND_NAMES.items()
                if re.search(rf"\b(?:{expression})(?:s)?\b", text, re.I)
                and not re.search(rf"\b(?:without|remove|drop|sans)\s+(?:the\s+)?(?:{expression})(?:s)?\b", text, re.I)}
    if expected - {item.kind for item in plan.items}:
        problems.append("I may have missed an item. Please confirm the items and quantities for this setup.")
    words = {"two": 2, "three": 3, "four": 4, "deux": 2, "trois": 3, "quatre": 4}
    for kind, expression in KIND_NAMES.items():
        match = re.search(rf"\b([2-9]|10|{'|'.join(words)})\s+(?:{expression})(?:s)?\b", text, re.I)
        if match:
            token = match.group(1).lower()
            qty = words.get(token, int(token) if token.isdecimal() else 0)
            if sum(item.quantity for item in plan.items if item.kind == kind) != qty:
                problems.append(f"Please confirm the requested quantity for {kind}.")
    budget = re.search(r"\b(\d+(?:[ ,.\u202f]\d+)*)\s*(?:TND|DT|dinars?)\b", text, re.I)
    if budget:
        value = re.split(r"(?<=\d)[,.](?=\d{1,2}$)", budget.group(1))
        expected_budget = Decimal(".".join(re.sub(r"[^0-9]", "", part) for part in value))
        if plan.budget_tnd != expected_budget:
            problems.append("I could not preserve the exact TND budget. Please confirm it.")
    if re.search(r"\b(?:usd|eur|gbp)\b|[$€£]", text, re.I) and plan.budget_tnd is not None:
        problems.append("Please specify the budget in TND.")
    rates = {int(rate) for rate in re.findall(r"\b(\d+)\s*hz\b", text, re.I)}
    if rates and not rates <= {link.refresh_hz for link in plan.links} | {
        int(match.group(1)) for item in plan.items for spec in item.specs
        if spec.field.casefold() in {"refresh_hz", "refresh rate"}
        and (match := re.match(r"(\d+)", spec.value))
    }:
        problems.append("The plan does not preserve the requested display refresh rate.")
    if previous:
        reconfigure = re.search(r"\b(?:remove|drop|without|instead|replace|only|sans|remplace)\b", text, re.I)
        prior = {item.id: item for item in previous.items}
        updated = {item.id: item for item in plan.items}
        if not reconfigure and any(item_id not in updated or updated[item_id].kind != item.kind
                                  for item_id, item in prior.items()):
            problems.append("Please confirm whether any previous items should be removed or replaced.")
        # A plain budget change may only change the budget. Protect quantities
        # and links even when the model returned a syntactically valid plan.
        if re.fullmatch(r"\s*(?:actually[\s,]+|new\s+)?(?:(?:total\s+)?budget(?:\s+(?:of|is|to))?\s*|make\s+(?:that|it)\s*|under\s*)?[\d ,.\u202f]+\s*(?:TND|DT|dinars?)?[.!]?\s*", text, re.I):
            prior_items = [item.model_dump(exclude={"queries"}) for item in previous.items]
            next_items = [item.model_dump(exclude={"queries"}) for item in plan.items]
            if prior_items != next_items or previous.links != plan.links:
                problems.append("Changing the budget cannot change the requested products or connections.")
    return problems


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
    heap = [(total(plan, selection(zero)) or Decimal(0), zero)]
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
                heappush(heap, (total(plan, selection(next_index)) or Decimal(0), next_index))


def cached_matches(line, cached, fresh):
    return [row for fields in cached if fresh(row := Listing.model_validate(fields)) and matches_line(row, line)]
