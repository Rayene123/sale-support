"""Independent rules for a directly connected laptop and external display."""
from __future__ import annotations

from decimal import Decimal
import re
import unicodedata

from .contracts import Finding, Listing, Requirements


def _fold(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def _evidence(item: Listing, field: str, value) -> dict[str, str]:
    return {"product_id": item.product_id, "url": item.source_url, "fetched_at": item.fetched_at,
            "field": field, "value": str(value)}


def _fields(item: Listing, labels: str) -> list[tuple[str, str]]:
    return [(key, value) for key, value in item.specs.items() if re.search(labels, _fold(key))]


def _number(values: list[tuple[str, str]], pattern: str) -> Decimal | None:
    found = {Decimal(m.group(1).replace(",", ".")) for _, value in values
             for m in re.finditer(pattern, _fold(value))
             if not re.search(r"maximum|up to|jusqu|upgrade|extensible|supported|supporte", _fold(value))}
    return next(iter(found)) if len(found) == 1 else None


def _minimum(item: Listing, code: str, required: Decimal, labels: str, pattern: str,
             *, exact: bool = False) -> Finding:
    fields = _fields(item, labels)
    actual = _number(fields, pattern)
    evidence = [_evidence(item, key, value) for key, value in fields]
    if actual is None:
        return Finding(code=code, verdict="unknown", reason=f"Required {code} is missing or conflicting", evidence=evidence)
    ok = actual == required if exact else actual >= required
    return Finding(code=code, verdict="pass" if ok else "fail",
                   reason=f"Listed {actual}, required {'exactly ' if exact else 'at least '}{required}", evidence=evidence)


def _ports(item: Listing, role: str):
    fields = _fields(item, r"connectiv|connectiq|connecteurs?|ports?|entrees?|sorties?|interfaces?|video")
    known: dict[str, list] = {}
    explicitly_listed = False
    for key, value in fields:
        label = _fold(key)
        text = _fold(value)
        if (role == "laptop" and re.search(r"inputs?|entrees?", label)
                or role == "monitor" and re.search(r"outputs?|sorties?", label)):
            continue
        explicitly_listed |= bool(re.search(r"video (?:outputs?|inputs?)|(?:sorties?|entrees?) video", label))
        for segment in re.split(r"[;,\n]|\s+/\s+", text):
            if re.search(r"\b(?:no|not|non|sans|pas|none|aucun|data only|charge only|donnees uniquement)\b", segment):
                continue
            matches = []
            usb = re.search(r"usb\s*[- ]?\s*c|type\s*[- ]?\s*c", segment)
            if usb and re.search(r"dp\s+alt(?:ernate)?\s*mode|displayport\s+alt(?:ernate)?\s*mode|displayport\s+over\s+usb", segment):
                matches.append("usb_c_dp")
            if not usb and re.search(r"\b(?:displayport|mini displayport|dp)\b", segment) and "mini " not in segment:
                matches.append("displayport")
            if re.search(r"\bhdmi\b", segment) and not re.search(r"mini hdmi|micro hdmi|adapter|adaptateur", segment):
                matches.append("hdmi")
            for port in matches:
                known.setdefault(port, []).append(_evidence(item, key, segment))
    return known, explicitly_listed, [_evidence(item, k, v) for k, v in fields]


def _display_mode(pieces: list[dict[str, str]], resolution: str, hz: int | None) -> bool:
    alias = {"1920x1080": "1080p", "2560x1440": "1440p", "3840x2160": "2160p"}[resolution]
    a,b = resolution.split("x")
    for proof in pieces:
        value = proof["value"]
        matches = re.findall(rf"(?:{a}\s*[x×]\s*{b}|{alias})\s*(?:@|at|a|up to|jusqu'a)?\s*(?:(\d+)\s*hz)?", value)
        if matches and (hz is None or any(rate and int(rate) >= hz for rate in matches)):
            return True
    return False


def verify_bundle(requirements: Requirements, items: dict[str, Listing], *, check_connection=True) -> list[Finding]:
    """Do not infer compatibility from connector shape, port version, or missing numbers."""
    findings = []
    if len(items) != len(requirements.items) or set(items) != set(requirements.items):
        return [Finding(code="required_items", verdict="unknown", reason="A required product is missing")]
    if (len({item.source_url for item in items.values()}) != len(items)
            or len({item.product_id for item in items.values()}) != len(items)):
        return [Finding(code="distinct_products", verdict="fail", reason="The same listing cannot fill two roles")]
    priced = all(item.price_tnd is not None for item in items.values())
    total = sum((item.price_tnd for item in items.values() if item.price_tnd is not None), Decimal(0))
    budget = requirements.budget_tnd
    findings.append(Finding(code="total_budget", verdict="unknown" if not priced or budget is None else (
        "pass" if total <= budget else "fail"), reason=f"Published total: {total} TND; limit: {budget} TND"
        if priced and budget is not None else "Price or a total budget is missing",
        evidence=[_evidence(item, "price_tnd", item.price_tnd) for item in items.values()]))
    for role, item in items.items():
        stock = item.availability
        findings.append(Finding(code=role+"_stock", verdict="pass" if stock == "in_stock" else (
            "fail" if stock == "out_of_stock" else "unknown"), reason=f"{item.name} stock: {stock}",
            evidence=[_evidence(item, "availability", stock)]))
    laptop, monitor = items.get("laptop"), items.get("monitor")
    if laptop and requirements.ram_gb:
        findings.append(_minimum(laptop, "ram_gb", Decimal(requirements.ram_gb),
                                 r"ram|^memoire$|memoire vive", r"(\d+)\s*(?:go|gb)\b"))
    if laptop and requirements.storage_gb:
        fields = _fields(laptop, r"stockage|storage|ssd|disque dur")
        values = {int(n) * (1000 if unit in {"to", "tb"} else 1)
                  for _, value in fields
                  for n, unit in re.findall(r"(\d+)\s*(go|gb|to|tb)\b", _fold(value))}
        actual = next(iter(values)) if len(values) == 1 else None
        findings.append(Finding(code="storage_gb", verdict="unknown" if actual is None else
            ("pass" if actual >= requirements.storage_gb else "fail"),
            reason="Storage unavailable or ambiguous" if actual is None else f"Listed {actual} GB; minimum {requirements.storage_gb} GB",
            evidence=[_evidence(laptop, k, v) for k, v in fields]))
    if monitor and requirements.monitor_inches:
        findings.append(_minimum(monitor, "monitor_size", requirements.monitor_inches,
                                 r"taille|diagonal|screen size|display size", r"(\d+(?:[.,]\d+)?)\s*(?:inch|pouce|[″\"])", exact=True))
    if monitor and requirements.resolution:
        native = _fields(monitor, r"resolution|definition")
        native_proof = [_evidence(monitor, k, _fold(v)) for k,v in native]
        a,b = requirements.resolution.split("x")
        meets = any(re.search(rf"{a}\s*[x×]\s*{b}", p["value"]) for p in native_proof)
        rate = _number(_fields(monitor, r"refresh|rafraich"), r"(\d+)\s*hz")
        ok = meets and (laptop is not None or requirements.hz is None or rate is not None and rate >= requirements.hz)
        findings.append(Finding(code="monitor_native_mode", verdict="pass" if ok else "unknown",
                                reason="Native mode confirmed" if ok else "Requested display mode could not be verified",
                                evidence=native_proof + [_evidence(monitor,k,v) for k,v in _fields(monitor,r"refresh|rafraich")]))
    if not (laptop and monitor):
        if requirements.connection:
            role, item = next(iter(items.items()))
            ports, complete, evidence = _ports(item, role)
            confirmed = requirements.connection in ports
            findings.append(Finding(code="requested_port", verdict="pass" if confirmed else (
                "fail" if complete and ports else "unknown"),
                reason="The requested video port is listed" if confirmed else "The requested port could not be verified",
                evidence=ports.get(requirements.connection, evidence)))
        return findings
    if not check_connection:
        return findings

    out, out_listed, out_proof = _ports(laptop, "laptop")
    into, in_listed, in_proof = _ports(monitor, "monitor")
    shared = sorted(set(out) & set(into))
    if requirements.connection:
        shared = [port for port in shared if port == requirements.connection]
    if not shared:
        mismatched = bool(out and into and out_listed and in_listed)
        findings.append(Finding(code="direct_video", verdict="fail" if mismatched else "unknown",
            reason="The published video outputs and inputs do not share the requested connection" if mismatched
            else "A compatible video output and input could not be verified",
            evidence=out_proof + in_proof))
        return findings
    if requirements.resolution:
        qualifying = [port for port in shared if _display_mode(out[port], requirements.resolution, requirements.hz)
                      and _display_mode(into[port], requirements.resolution, requirements.hz)]
        if not qualifying:
            findings.append(Finding(code="display_mode", verdict="unknown",
                reason="A common connector is listed, but the desired resolution and refresh rate are not verified on both ends",
                evidence=[piece for port in shared for piece in out[port] + into[port]]))
            return findings
        shared = qualifying
    port = shared[0]
    names = {"hdmi": "a compatible HDMI cable", "displayport": "a compatible DisplayPort cable",
             "usb_c_dp": "a USB-C cable that supports DisplayPort video"}
    findings.append(Finding(code="direct_video", verdict="pass",
        reason=f"Use {names[port]}. Both exact product pages document this video connection.",
        evidence=out[port] + into[port]))
    return findings
