"""Verify an extensible shopping graph with exact listing evidence."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import re

from .contracts import Finding, Listing
from .setup import Item, Link, SetupPlan
from .verify import _display_mode, _evidence, _fold, _ports


def total(plan: SetupPlan, items: dict[str, Listing]) -> Decimal | None:
    purchased = [item for item in plan.items if not item.owned]
    if any(item.id not in items or items[item.id].price_tnd is None for item in purchased):
        return None
    return sum((items[item.id].price_tnd * item.quantity for item in purchased), Decimal(0))


def _aliases(field: str) -> set[str]:
    label = _fold(field).strip()
    groups = (
        {"ram", "ram_gb", "memory", "memoire", "memoire vive", "installed ram"},
        {"storage", "storage_gb", "ssd", "disque dur", "stockage"},
        {"monitor_inches", "display size", "screen size", "taille ecran", "diagonale"},
        {"resolution", "native resolution", "listing resolution", "resolution du panneau"},
        {"refresh_hz", "refresh rate", "taux de rafraichissement"},
        {"stock quantity", "quantite en stock", "available units"},
    )
    return next((group for group in groups if label in group), {label})


def _values(item: Listing, field: str) -> list[tuple[str, str]]:
    aliases = _aliases(field)
    return [(label, value) for label, value in item.specs.items() if _fold(label).strip() in aliases]


def _normalized(value: str):
    text = " ".join(_fold(value).strip().split())
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(gb|go|tb|to|hz|inch(?:es)?|pouces?|[\"″])?(?:\s+ssd)?", text)
    if not match:
        return text
    number = Decimal(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit in {"tb", "to"}:
        return (number * 1000, "gb")
    if unit in {"gb", "go"}:
        return (number, "gb")
    if unit and (unit.startswith(("inch", "pouce")) or unit in {'"', "″"}):
        return (number, "inch")
    return (number, unit)


def _spec(line: Item, listing: Listing, constraint) -> Finding:
    values = _values(listing, constraint.field)
    values = [(label, value) for label, value in values
              if not re.search(r"\b(?:maximum|supported|up to|jusqu|extensible|upgrade|optional)\b", _fold(value))]
    normalized = {_normalized(value) for _, value in values}
    expected = _normalized(constraint.value)
    valid = None
    if len(normalized) == 1:
        actual = next(iter(normalized))
        if constraint.comparison == "equals":
            valid = actual == expected
        elif isinstance(actual, tuple) and isinstance(expected, tuple) and actual[1] == expected[1]:
            valid = actual[0] >= expected[0]
    verdict = "unknown" if valid is None else "pass" if valid else "fail"
    return Finding(code=f"{line.id}:{constraint.field}", verdict=verdict,
                   reason=f"{line.id} requires {constraint.field} {constraint.comparison} {constraint.value}.",
                   evidence=[_evidence(listing, name, value) for name, value in values])


def _declared_link_ports(item: Listing, kind: str, end: str):
    evidence = {}
    if kind == "video":
        return _ports(item, "laptop" if end == "source" else "monitor")[0]
    pattern = r"\busb[- ]?(a|c)\b" if kind == "usb" else r"\b(?:rj[- ]?45|ethernet)\b"
    for key, value in item.specs.items():
        if not re.search(r"ports?|connectiv|connectiq|connecteurs?|interfaces?|entr[ée]es?|sorties?", _fold(key)):
            continue
        for segment in re.split(r"[;,\n]| / ", _fold(value)):
            if re.search(r"\b(?:no|not|non|sans|charge only|power only|avoid)\b", segment):
                continue
            for match in re.finditer(pattern, segment):
                connector = "usb_" + match.group(1) if kind == "usb" else "ethernet"
                if connector == "usb_c" and not re.search(r"\b(?:data|donnees|usb\s*[234](?:\.\d)?|gbps)\b", segment):
                    continue
                evidence.setdefault(connector, []).append(_evidence(item, key, segment))
    return evidence


def _count(proof):
    count = 1
    for fact in proof:
        value = fact["value"]
        match = re.match(r"\s*(?:[a-z][a-z ]*:\s*)?(\d+)\s*[x×]\s*([a-z0-9 -]+)", value)
        if match:
            count = max(count, int(match.group(1)))
    return count


def _edge(link: Link, lines: dict[str, Item], items: dict[str, Listing], details: dict) -> Finding:
    source, target = items[link.source], items[link.target]
    first, second = lines[link.source], lines[link.target]
    key = f"{link.source}->{link.target}:{link.kind}"
    if link.kind not in {"video", "usb", "ethernet"}:
        return Finding(code=key, verdict="unknown", reason=f"No approved verifier for {link.kind}")
    if ((link.resolution or link.refresh_hz) and link.kind != "video") or first.quantity != 1:
        return Finding(code=key, verdict="unknown", reason="The requested connection topology or mode is not supported")
    if link.kind == "video" and (first.kind == "dock" or second.kind == "dock"):
        return Finding(code=key, verdict="unknown",
                       reason="Dock display passthrough and simultaneous modes require a separate verification rule")
    outputs = _declared_link_ports(source, link.kind, "source")
    inputs = _declared_link_ports(target, link.kind, "target")
    shared = set(outputs) & set(inputs)
    if link.transport:
        alias = link.transport.strip().lower().replace("-", "_").replace(" ", "_")
        alias = {"dp": "displayport", "usb_c": "usb_c_dp" if link.kind == "video" else "usb_c",
                 "rj45": "ethernet"}.get(alias, alias)
        shared &= {alias}
    if not shared:
        # Explicitly complete role-appropriate video declarations can prove a mismatch.
        complete = (link.kind == "video" and outputs and inputs
                    and _ports(source, "laptop")[1] and _ports(target, "monitor")[1])
        facts = [fact for values in (*outputs.values(), *inputs.values()) for fact in values]
        return Finding(code=key, verdict="fail" if complete else "unknown",
                       reason="Published video connections do not match" if complete else "No shared connection could be verified",
                       evidence=facts)
    for connector in sorted(shared):
        if link.resolution and not (
            _display_mode(outputs[connector], link.resolution, link.refresh_hz)
            and _display_mode(inputs[connector], link.resolution, link.refresh_hz)
            and {re.sub(r"\s+", "", match.group()).replace("×", "x")
                 for _, value in _values(target, "resolution")
                 for match in re.finditer(r"\d{4}\s*[x×]\s*\d{4}", value.lower())} == {link.resolution}
        ):
            continue
        if _count(outputs[connector]) < second.quantity:
            continue
        details[key] = (connector, outputs[connector], inputs[connector])
        return Finding(code=key, verdict="pass", reason=f"Published {connector} connection on both models",
                       evidence=outputs[connector] + inputs[connector])
    return Finding(code=key, verdict="unknown",
                   reason="The requested mode or number of ports could not be confirmed on the exact models",
                   evidence=[fact for port in shared for fact in outputs[port] + inputs[port]])


def verify_setup(plan: SetupPlan, items: dict[str, Listing]) -> list[Finding]:
    lines = {item.id: item for item in plan.items}
    if plan.missing() or set(items) != set(lines):
        return [Finding(code="setup_incomplete", verdict="unknown", reason="The setup or exact listings are incomplete")]
    if len({item.product_id for item in items.values()}) != len(items):
        return [Finding(code="distinct_items", verdict="unknown", reason="Use quantity for duplicate product listings")]
    cost = total(plan, items)
    findings = [Finding(code="total_budget", verdict="unknown" if cost is None else
                        "pass" if cost <= plan.budget_tnd else "fail",
                        reason=f"Total for items to purchase: {cost} TND; limit {plan.budget_tnd} TND",
                        evidence=[_evidence(items[item.id], "price_tnd", items[item.id].price_tnd)
                                  for item in plan.items if not item.owned])]
    for line in plan.items:
        listing = items[line.id]
        if not line.owned:
            capacity = _values(listing, "stock quantity")
            quantities = {int(value) for _, value in capacity if re.fullmatch(r"\d+", value)}
            stock = "fail" if listing.availability == "out_of_stock" else "unknown"
            if listing.availability == "in_stock":
                if line.quantity == 1:
                    stock = "pass"
                elif len(quantities) == 1:
                    stock = "pass" if next(iter(quantities)) >= line.quantity else "fail"
            findings.append(Finding(code=line.id+"_stock", verdict=stock,
                reason=f"Availability for {line.quantity} unit(s): {listing.availability}",
                evidence=[_evidence(listing, "availability", listing.availability)] +
                [_evidence(listing, label, value) for label, value in capacity]))
        for spec in line.specs:
            findings.append(_spec(line, listing, spec))

    details = {}
    findings.extend(_edge(link, lines, items, details) for link in plan.links)
    use = Counter()
    ports = {}
    displays = Counter()
    for link in plan.links:
        result = details.get(f"{link.source}->{link.target}:{link.kind}")
        if result is None:
            continue
        connector, outputs, inputs = result
        for node, number, proof in [(link.source, lines[link.target].quantity, outputs), (link.target, 1, inputs)]:
            use[(node, connector)] += number
            ports[(node, connector)] = max(ports.get((node, connector), 0), _count(proof))
        if link.kind == "video":
            displays[link.source] += lines[link.target].quantity
    for (node, connector), demand in use.items():
        if demand > ports[node, connector]:
            findings.append(Finding(code="port_capacity", verdict="unknown",
                reason=f"{node} needs {demand} separate {connector} ports; the listing does not establish that capacity"))
    for node, count in displays.items():
        if count > 1:
            values = [(k, v) for k, v in items[node].specs.items()
                      if _fold(k) in {"maximum simultaneous displays", "simultaneous displays"}]
            capacities = {int(value) for _, value in values if re.fullmatch(r"\d+", value)}
            if len(capacities) != 1 or next(iter(capacities)) < count:
                findings.append(Finding(code="simultaneous_displays", verdict="unknown",
                    reason=f"{node} has no evidence for {count} external displays at once",
                    evidence=[_evidence(items[node], k, v) for k, v in values]))
            else:
                findings.append(Finding(code="multi_display_modes", verdict="unknown",
                    reason=f"Individual port modes do not establish the requested concurrent display modes for {node}"))
    return findings
