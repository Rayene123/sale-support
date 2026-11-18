"""Conservative parsing for explicit shopper requests and retailer references."""

from decimal import Decimal
import re
from urllib.parse import urlsplit, urlunsplit

from specialist.contracts.setup import KIND_NAMES, SetupPlan
from specialist.contracts.text import fold_text


_MONEY = r"\d+(?:[ ,.\u202f]\d+)*"
_KINDS = {**KIND_NAMES, "carte_graphique": r"graphics card|carte graphique|gpu",
          "boitier_pc": r"pc case|boitier pc|chassis"}


def price_in_text(value):
    parts = re.split(r"(?<=\d)[,.](?=\d{1,2}$)", value)
    return Decimal(".".join(re.sub(r"[^0-9]", "", part) for part in parts))


def standalone_kind(text):
    """Recognize only plain requests for one product or an explicit single-item limit."""
    text = fold_text(text)
    for kind, aliases in _KINDS.items():
        simple = rf"(?:please\s+)?(?:find(?:\s+me)?|show(?:\s+me)?|recommend(?:\s+me)?|i\s+(?:need|want))\s+(?:a|an|one|1|exactly one)\s+(?:new\s+)?(?:{aliases})\s*(?:(?:under|below|up to|for)\s+{_MONEY}\s+(?:tnd|dt)(?:\s+total)?)?[.!]?"
        if re.fullmatch(simple, text.strip()):
            return kind
    named = {kind for kind, names in _KINDS.items() if re.search(rf"\b(?:{names})s?\b", text)}
    if len(named) == 1 and not re.search(r"\b(?:and|with)\s+(?:a|an|one|another|my)\b", text):
        kind = next(iter(named))
        aliases = _KINDS[kind]
        if (re.search(rf"\b(?:one|1|single)\s+(?:new\s+)?(?:{aliases})\b", text)
                or re.match(rf"(?:please\s+)?(?:find(?:\s+me)?|recommend(?:\s+me)?|i\s+(?:need|want))\s+(?:a|an)\s+(?:new\s+)?(?:{aliases})\b", text.strip())):
            return kind
    return None


def enforce_standalone(plan, text, previous):
    kind = standalone_kind(text) if previous is None else None
    if not kind:
        return plan
    folded = fold_text(text)
    for item in plan.items:
        terms = _KINDS.get(item.kind, re.escape(item.kind.replace("_", " ")))
        if item.kind != kind and re.search(rf"\b(?:{terms})s?\b", folded):
            return plan
    matches = [item for item in plan.items if item.kind == kind]
    if len(matches) != 1:
        return plan
    item = matches[0].model_copy(update={"quantity": 1, "owned": False})
    return plan.model_copy(update={"items": [item], "links": [],
                                  "questions": [] if plan.budget_tnd is not None else plan.questions})


def carry_requirements(plan, previous, text):
    if previous is None:
        return plan
    prior = {item.id: item for item in previous.items}
    folded = fold_text(text)
    items = []
    for item in plan.items:
        old = prior.get(item.id)
        if old and old.kind == item.kind:
            names = {fold_text(spec.field) for spec in item.specs}
            absent = [spec for spec in old.specs if fold_text(spec.field) not in names
                      and not re.search(rf"\b(?:remove|drop|no longer need)\s+(?:the\s+)?{re.escape(fold_text(spec.field))}\b", folded)]
            changes = {"specs": (item.specs + absent)[:8]}
            terms = _KINDS.get(item.kind, re.escape(item.kind.replace("_", " ")))
            if not re.search(rf"\b(?:\d+|one|two|three|four|five|un|une|deux|trois)\s+(?:{terms})s?\b", folded):
                changes["quantity"] = old.quantity
            item = item.model_copy(update=changes)
        items.append(item)
    ids = {item.id for item in items}
    links = {(link.source, link.target, link.kind): link for link in plan.links}
    for link in previous.links:
        if not {link.source, link.target} <= ids:
            continue
        key = (link.source, link.target, link.kind)
        if current := links.get(key):
            links[key] = current.model_copy(update={
                "transport": current.transport or link.transport,
                "resolution": current.resolution or link.resolution,
                "refresh_hz": current.refresh_hz or link.refresh_hz,
                "checks": current.checks or link.checks,
            })
        else:
            links[key] = link
    budget = plan.budget_tnd if re.search(r"\b(?:tnd|dt|dinars?)\b|\b(?:budget|spend|cost)\b", text, re.I) else previous.budget_tnd
    return plan.model_copy(update={"items": items, "links": list(links.values())[:16], "budget_tnd": budget or plan.budget_tnd})


def direct_budget_revision(text, previous, proposal):
    if previous is None:
        return None
    explicit = re.fullmatch(
        rf"\s*(?:(?:make\s+(?:it|that|the budget)|(?:my\s+)?(?:total\s+)?budget(?:\s+is|\s+to)?|up to|under)\s+)?({_MONEY})\s*(?:tnd|dt)[.!]?\s*",
        text, re.I,
    )
    cheaper = re.fullmatch(r"\s*(?:can you\s+)?(?:find(?: me)?\s+)?(?:(?:a|something)\s+)?cheaper(?:\s+one|\s+option)?[?.!]?\s*", text, re.I)
    if explicit:
        budget = price_in_text(explicit[1])
    elif cheaper and proposal:
        budget = Decimal(proposal["actions"][0]["payload"]["total_tnd"]) - Decimal("0.01")
        if previous.budget_tnd:
            budget = min(budget, previous.budget_tnd)
    else:
        if re.fullmatch(r"\s*(?:prioriti[sz]e battery life|longer battery life)[.!]?\s*", text, re.I):
            return previous.model_copy(update={"questions": []})
        return None
    if budget <= 0:
        return None
    try:
        return SetupPlan.model_validate({**previous.model_dump(), "budget_tnd": budget, "questions": []})
    except ValueError:
        return None


def retailer_reference(text):
    """Extract one exact Tunisianet listing from the shopper's own message."""
    for raw in re.findall(r"https://[^\s<>]+", text, re.I):
        try:
            url = urlsplit(raw.rstrip(".,!;)"))
            id_match = re.search(r"/(\d+)-[^/]+\.html$", url.path)
            if (url.hostname not in {"www.tunisianet.com.tn", "tunisianet.com.tn"} or
                    url.username is not None or url.password is not None or
                    url.port not in (None, 443) or not id_match):
                continue
            return raw, id_match[1], urlunsplit(("https", url.hostname, url.path, "", ""))
        except ValueError:
            continue
    return None


def reference_kind(listing):
    name = fold_text(listing.name)
    return next((kind for kind, terms in _KINDS.items() if re.search(rf"\b(?:{terms})\b", name)), None)


def lock_requested_items(case, text, previous, proposal):
    if previous is None:
        return
    text = fold_text(text)
    pins = case.setdefault("shopping_pins", {})
    excluded = case.setdefault("shopping_excluded", {})
    evidence = proposal["evidence"] if proposal else {}
    for item in previous.items:
        terms = _KINDS.get(item.kind, re.escape(item.kind.replace("_", " ")))
        if re.search(rf"\b(?:replace|swap|change|remove|drop)\s+(?:(?:the|my)\s+)?(?:{terms})\b", text):
            pins.pop(item.id, None)
            if item.id in evidence:
                excluded[item.id] = evidence[item.id]["product_id"]
        elif re.search(rf"\bkeep\s+(?:(?:the|my|same)\s+)*(?:{terms})\b", text) and item.id in evidence:
            pins[item.id] = evidence[item.id]


def wants_battery(text):
    return bool(re.search(r"\b(?:better (?:for )?battery(?: life)?|prioriti[sz]e battery|longer battery life|long battery life)\b",
                          fold_text(text)))


def requests_checkout(text):
    return bool(re.fullmatch(
        r"\s*(?:(?:please|can you|could you|i want to|i.d like to)\s+)?"
        r"(?:order|buy|place (?:my|the) order(?: for)?)"
        r"(?:\s+(?:it|this|this setup|the setup|these|these items|everything|the laptop))?"
        r"(?:\s+for me)?[?.!]?\s*",
        fold_text(text),
    ))


def battery_hours(item):
    values = []
    for key, value in item.specs.items():
        if not re.search(r"\b(?:battery life|autonomie|duree de la batterie)\b", fold_text(key)):
            continue
        match = re.search(r"\b(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:h\b|hours?\b|heures?\b)", value, re.I)
        if match:
            values.append(Decimal(match[1].replace(",", ".")))
    return min(values) if values else Decimal(0)
