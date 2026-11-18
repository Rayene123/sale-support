"""Verify an extensible shopping graph with exact listing evidence."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import re

from specialist.contracts.purchasing import Finding, Listing
from specialist.contracts.setup import Item, Link, SetupPlan, setup_total
from specialist.contracts.text import COLOR_FIELDS, RAM_FIELDS, color_family, fold_text
from .display import _display_mode, _evidence, _ports


def _aliases(field: str) -> set[str]:
    label = fold_text(field).replace("_", " ").strip()
    groups = (
        RAM_FIELDS,
        {"storage", "storage gb", "ssd", "disque dur", "stockage"},
        {"monitor inches", "display size", "screen size", "taille ecran", "diagonale"},
        {"resolution", "native resolution", "listing resolution", "resolution du panneau"},
        {"refresh hz", "refresh rate", "taux de rafraichissement"},
        {"stock quantity", "quantite en stock", "available units"},
        COLOR_FIELDS,
    )
    return next((group for group in groups if label in group), {label})


def _values(item: Listing, field: str) -> list[tuple[str, str]]:
    aliases = _aliases(field)
    return [(label, value) for label, value in item.specs.items() if fold_text(label).replace("_", " ").strip() in aliases]


def _normalized(value: str):
    text = " ".join(fold_text(value).strip().split())
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(gb|go|tb|to|hz|mm|cm|w|kw|v|a|inch(?:es)?|pouces?|[\"″])?(?:\s+ssd)?", text)
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
    if unit == "cm":
        return (number * 10, "mm")
    if unit == "kw":
        return (number * 1000, "w")
    return (number, unit)


def _spec(line: Item, listing: Listing, constraint) -> Finding:
    values = _values(listing, constraint.field)
    values = [(label, value) for label, value in values
              if not re.search(r"\b(?:maximum|supported|up to|jusqu|extensible|upgrade|optional)\b", fold_text(value))]
    def normalize(value):
        if fold_text(constraint.field) in COLOR_FIELDS:
            return color_family(value) or _normalized(value)
        return _normalized(value)

    normalized = {normalize(value) for _, value in values}
    expected = normalize(constraint.value)
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
        if not re.search(r"ports?|connectiv|connectiq|connecteurs?|interfaces?|entr[ée]es?|sorties?", fold_text(key)):
            continue
        for segment in re.split(r"[;,\n]| / ", fold_text(value)):
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


def _link_checks(link, source, target):
    """Evaluate the local model's proposed comparisons using only catalog facts."""
    findings = []
    for i, check in enumerate(link.checks, start=1):
        out = _values(source, check.source_field)
        into = _values(target, check.target_field)
        source_values = {_normalized(v) for _, v in out if v.strip()}
        target_values = {_normalized(v) for _, v in into if v.strip()}
        verdict = "unknown"
        if len(source_values) == 1 and len(target_values) == 1:
            left, right = next(iter(source_values)), next(iter(target_values))
            if check.comparison == "equals":
                if type(left) is type(right) and (not isinstance(left, tuple) or left[1] == right[1]):
                    verdict = "pass" if left == right else "fail"
            elif isinstance(left, tuple) and isinstance(right, tuple) and left[1] == right[1] and left[1]:
                ok = left[0] >= right[0] if check.comparison == "at_least" else left[0] <= right[0]
                verdict = "pass" if ok else "fail"
        findings.append(Finding(
            code=f"{link.source}->{link.target}:{link.kind}:check:{i}", verdict=verdict,
            reason=f"Compare {check.source_field} ({link.source}) {check.comparison} "
                   f"{check.target_field} ({link.target})",
            evidence=[_evidence(source, label, value) for label, value in out]
                     + [_evidence(target, label, value) for label, value in into],
        ))
    return findings


def _exact_compatibility(source, target, source_line, target_line):
    """A generic positive verdict needs an explicit declaration for the other exact model."""
    labels = {"compatible part numbers", "compatible models", "supported models",
              "supported part numbers", "modeles compatibles", "references compatibles"}
    identity = {"mpn", "part number", "reference", "model", "modele"}
    for listing, other, line in ((source, target, target_line), (target, source, source_line)):
        identifiers = {fold_text(value).strip() for key, value in other.specs.items() if fold_text(key) in identity}
        if line.exact_model:
            identifiers.add(fold_text(line.exact_model).strip())
        identifiers = {name for name in identifiers if len(name) >= 4 and any(c.isdigit() for c in name)}
        for key, value in listing.specs.items():
            if fold_text(key) not in labels:
                continue
            # Take complete model tokens. "Not compatible with A200" and
            # "A200 series" must not be interpreted as an exact model match.
            models = {fold_text(model).strip() for model in re.split(r"[,;\n|]", value)}
            if match := identifiers & models:
                return [_evidence(listing, key, value), _evidence(other, "exact model", sorted(match)[0])]
    return []


def _edge(link: Link, lines: dict[str, Item], items: dict[str, Listing], details: dict) -> Finding:
    source, target = items[link.source], items[link.target]
    first, second = lines[link.source], lines[link.target]
    key = f"{link.source}->{link.target}:{link.kind}"
    if link.kind not in {"video", "usb", "ethernet"}:
        proof = _exact_compatibility(source, target, first, second) if (
            first.quantity == second.quantity == 1 and not (link.resolution or link.refresh_hz or link.transport)
        ) else []
        return Finding(code=key, verdict="pass" if proof else "unknown",
                       reason="An exact product listing explicitly names the other compatible model"
                       if proof else f"Could not establish {link.kind}; checked attributes alone do not prove the pairing",
                       evidence=proof)
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
    cost = setup_total(plan, items)
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
    for link in plan.links:
        findings.extend(_link_checks(link, items[link.source], items[link.target]))
        findings.append(_edge(link, lines, items, details))
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
                      if fold_text(k) in {"maximum simultaneous displays", "simultaneous displays"}]
            capacities = {int(value) for _, value in values if re.fullmatch(r"\d+", value)}
            if len(capacities) != 1 or next(iter(capacities)) < count:
                findings.append(Finding(code="simultaneous_displays", verdict="unknown",
                    reason=f"{node} has no evidence for {count} external displays at once",
                    evidence=[_evidence(items[node], k, v) for k, v in values]))
            else:
                findings.append(Finding(code="multi_display_modes", verdict="unknown",
                    reason=f"Individual port modes do not establish the requested concurrent display modes for {node}"))
    return findings
