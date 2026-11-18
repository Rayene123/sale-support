"""Ground model plans in the current request and earlier requirements."""

from decimal import Decimal
import re

from specialist.contracts.setup import KIND_NAMES, SetupPlan, Spec
from specialist.contracts.text import COLORS, COLOR_FIELDS, color_family, fold_text


_DISPLAY_MODES = {"1920x1080": r"1920\s*[x×]\s*1080|\b1080p\b|\bfull hd\b",
                  "2560x1440": r"2560\s*[x×]\s*1440|\b1440p\b|\bqhd\b",
                  "3840x2160": r"3840\s*[x×]\s*2160|\b4k\b|\b2160p\b"}


def _mentioned(text, label):
    def normalized(value):
        value = re.sub(r"(?<=\d)\s*(go|to|gb|tb|hz)\b",
                       lambda match: {"go": "gb", "to": "tb"}.get(match[1], match[1]), fold_text(value))
        return re.sub(r"[^\w]+|_", " ", value).strip()

    return f" {normalized(label)} " in f" {normalized(text)} "


def _mentions_color(text, color):
    return any(_mentioned(text, alias) for alias in (color, *COLORS[color]))


def ground_plan(plan: SetupPlan, text: str, previous: SetupPlan | None) -> SetupPlan:
    """Keep supported connection checks independent of unstated model preferences."""
    prior_items = {item.id: item for item in previous.items} if previous else {}
    prior_links = {(link.source, link.target, link.kind): link for link in previous.links} if previous else {}
    colors = [color for color in COLORS if _mentions_color(text, color)]
    color_is_required = len(colors) == 1 and not re.search(
        r"\b(?:prefer|preferably|ideally|optional|if possible)\b", text, re.I
    )
    if color_is_required:
        aliases = "|".join((colors[0], *COLORS[colors[0]]))
        color_is_required = not re.search(
            rf"\b(?:not|no|without|avoid|except|sauf|sans)\s+(?:{aliases})\b", fold_text(text)
        )
    items = []
    for item in plan.items:
        prior = prior_items.get(item.id)
        specs = []
        for spec in item.specs:
            color = color_family(spec.value) if fold_text(spec.field) in COLOR_FIELDS else None
            if color:
                if (not colors and prior and spec in prior.specs) or (color_is_required and color in colors):
                    specs.append(Spec(field="color", value=color, comparison="equals"))
            elif (prior and spec in prior.specs) or _mentioned(text, spec.value) or (
                    spec.value.casefold() in {"yes", "oui", "true"} and _mentioned(text, spec.field)):
                specs.append(spec)
        if len(plan.items) == 1 and not item.owned and color_is_required and len(specs) < 8:
            if not any(fold_text(spec.field) in COLOR_FIELDS for spec in specs):
                specs.append(Spec(field="color", value=colors[0], comparison="equals"))
        items.append(item.model_copy(update={"specs": specs}))
    links = []
    for link in plan.links:
        if link.kind not in {"video", "usb", "ethernet"}:
            links.append(link)
            continue
        prior = prior_links.get((link.source, link.target, link.kind))
        explicit_mode = re.search(r"\b(?:hdmi|displayport|usb(?:[- ]?[ac])?)\s*\d", text, re.I)
        checks = [check for check in link.checks if explicit_mode or (prior and check in prior.checks)
                  or _mentioned(text, check.source_field) or _mentioned(text, check.target_field)]
        updates = {"checks": checks}
        if link.kind == "video":
            if (link.resolution and not (prior and link.resolution == prior.resolution)
                    and not re.search(_DISPLAY_MODES[link.resolution], text, re.I)):
                updates["resolution"] = None
            if (link.refresh_hz and not (prior and link.refresh_hz == prior.refresh_hz)
                    and not re.search(rf"\b{link.refresh_hz}\s*hz\b", text, re.I)):
                updates["refresh_hz"] = None
            if link.transport and not (prior and link.transport == prior.transport):
                transport = link.transport.casefold().replace("_", "-")
                forms = {"displayport": ("displayport", "display port", "dp"),
                         "dp": ("displayport", "display port", "dp"),
                         "usb-c": ("usb c", "usb-c"), "usb-c-dp": ("usb c", "usb-c")}
                if not any(_mentioned(text, word) for word in forms.get(transport, (transport,))):
                    updates["transport"] = None
        links.append(link.model_copy(update=updates))
    return plan.model_copy(update={"items": items, "links": links})


def read_plan_findings(plan, text, previous=None):
    """Check a few common omissions independently. The reviewer sees the entire plan."""
    problems = []
    expected = {name for name, expression in KIND_NAMES.items()
                if re.search(rf"\b(?:{expression})(?:s)?\b", text, re.I)
                and not re.search(rf"\b(?:without|remove|drop|sans|no)\s+(?:the\s+)?(?:{expression})(?:s)?\b", text, re.I)}
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
    if any(link.kind == "video" for link in plan.links):
        modes = {name for name, alias in _DISPLAY_MODES.items() if re.search(alias, text, re.I)}
        if modes and not modes.intersection(link.resolution for link in plan.links):
            problems.append("The plan does not preserve the requested display resolution.")
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
