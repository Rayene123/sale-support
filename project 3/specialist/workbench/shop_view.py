"""Render the shopper's search, comparison evidence, and retailer links."""

from decimal import Decimal

from specialist.contracts.purchasing import catalog_image_url
from specialist.workflow.case_state import FOLLOW_UP

from .views import e, form


HERO_MONITOR = "https://www.tunisianet.com.tn/416951-large_default/57900-ecran-xiaomi-gaming-g24i-180hz-noir.jpg"
HERO_LAPTOP = "https://www.tunisianet.com.tn/506112-large_default/pc-portable-chuwi-gemibook-plus-n5030-8-go-256-go-ssd-windows-11-gris.jpg"
EXAMPLES = {
    "A laptop for work": "Find exactly one new laptop for work under 3,000 TND as a standalone purchase. No additional products.",
    "Laptop + monitor": "Find a laptop and a compatible external monitor under 3,000 TND total.",
    "Fit a GPU in my case": "Help me find a graphics card that physically fits my existing PC case.",
}
HEADINGS = {
    "awaiting_clarification": ("A quick question.", "A little more detail will help narrow the search."),
    "verification_blocked": ("Some details need checking.", "These listings came up in the search. Review the gaps below or refine your request."),
    "source_unavailable": ("The retailer is unavailable.", "Try again or change what you’re looking for."),
    "planner_unavailable": ("The assistant is unavailable.", "Start the local model and try the request again."),
    "step_limit_reached": ("Search limit reached.", "Start a fresh search with a narrower request."),
    "research_pending": ("Resume your search.", "Continue checking the listings for this request."),
}
ACTIVITY = {
    "interpret_setup": "Read the request", "ask_clarification": "Identified missing requirements",
    "search_catalog": "Searched product listings", "inspect_listing": "Read an exact product page",
    "check_candidate": "Checked the setup against its listings", "broaden_research": "Tried another search",
    "reuse_evidence": "Reused recent listing evidence",
}


def money(value):
    return f"{Decimal(value):,.2f}".rstrip("0").rstrip(".") if value is not None else "Price unavailable"


def search_form(csrf, *, case=None):
    target = "/shop/" if case is None else f'/shop/{case["case_id"]}'
    prompt = "What are you looking for?" if case is None else "What would you like to change?"
    fields = {"action": "start"} if case is None else {"action": "revise", "revision": case["revision"]}
    return form(
        target, csrf,
        f'<label class="sr-only" for="request">{prompt}</label>'
        f'<div class="composer"><textarea id="request" name="request" rows="2" required maxlength="1200" '
        f'placeholder="{prompt}"></textarea><div class="composer-actions">'
        f'<button type="submit" class="button button-primary" data-search>'
        f'{"Find my setup" if case is None else "Update search"} <span aria-hidden="true">↗</span></button></div></div>'
        '<p class="search-progress" role="status" hidden><span class="spinner" aria-hidden="true"></span>'
        ' Searching and checking listings…</p>', **fields,
    )


def home(csrf, fixture):
    art = "" if fixture else (
        '<figure class="hero-art" aria-label="Laptop and monitor photographs from Tunisianet">'
        '<div class="stage"><span class="orbit orbit-one"></span><span class="orbit orbit-two"></span>'
        f'<img class="hero-monitor" src="{HERO_MONITOR}" alt="" referrerpolicy="no-referrer">'
        f'<img class="hero-laptop" src="{HERO_LAPTOP}" alt="" referrerpolicy="no-referrer"></div>'
        '<figcaption>Product photography · Tunisianet</figcaption></figure>'
    )
    examples = "".join(
        f'<button type="button" class="chip" data-example="{e(request)}">{e(label)} <span aria-hidden="true">↗</span></button>'
        for label, request in EXAMPLES.items()
    )
    return (
        '<section class="hero"><div class="hero-copy">'
        '<p class="eyebrow">IT purchasing assistant</p>'
        '<h1>Find the gear<br> that <em>fits.</em></h1>'
        '<p class="lede">Describe what you need. Get a setup that fits your budget, with the specs checked against the listings.</p>'
        f'{search_form(csrf)}<div class="examples" aria-label="Example requests">{examples}</div>'
        f'</div>{art}</section>'
    )


def product_row(item, quantity, fixture):
    name = e(item["name"])
    image = catalog_image_url(item.get("image_url")) if not fixture else None
    photo = (
        f'<img src="{e(image)}" alt="{name}" loading="lazy" referrerpolicy="no-referrer">'
        if image else '<span>Photo unavailable</span>'
    )
    availability = {"in_stock": "In stock", "available": "Listed as available",
                    "out_of_stock": "Out of stock", "unknown": "Stock unconfirmed"}[item["availability"]]
    price = money(item.get("price_tnd"))
    if item.get("price_tnd") is not None:
        price += " TND"
    listing = "" if fixture else (
        f'<a class="listing-link" href="{e(item["source_url"])}" target="_blank" rel="noopener noreferrer">'
        'View on Tunisianet <span aria-hidden="true">↗</span></a>'
    )
    count = f' · Qty {quantity}' if quantity > 1 else ""
    return (
        '<article class="product-line">'
        f'<div class="product-image">{photo}<span class="photo-fallback" hidden>Photo unavailable</span></div>'
        f'<div><p class="product-availability">{availability}{count}</p><h3>{name}</h3>{listing}</div>'
        f'<strong class="product-price">{price}</strong></article>'
    )


def verification(findings, fixture):
    rows = []
    for finding in findings:
        verdict = {"pass": "Verified", "fail": "Doesn’t fit", "unknown": "Unverified"}[finding["verdict"]]
        facts = []
        for fact in finding.get("evidence", [])[:8]:
            source = "" if fixture else f' · <a href="{e(fact["url"])}" target="_blank" rel="noopener noreferrer">Listing ↗</a>'
            facts.append(f'<li>{e(fact["field"])} · {e(fact["value"])}{source}</li>')
        proof = f'<ul class="facts">{"".join(facts)}</ul>' if facts else ""
        rows.append(
            f'<li class="finding"><span class="verdict {finding["verdict"]}">{verdict}</span>'
            f'<div>{e(finding["reason"])}{proof}</div></li>'
        )
    return (
        f'<details class="disclosure"><summary>What was verified <span>{len(rows)} checks</span></summary><ul>{"".join(rows)}</ul></details>'
        if rows else ""
    )


def alternatives_summary(options):
    entries = []
    for option in options[:4]:
        names = " + ".join(item["name"] for item in option["items"].values())
        reason = next((finding["reason"] for finding in option["findings"] if finding["verdict"] != "pass"), "")
        if reason:
            entries.append(f'<li><strong>{e(names)}</strong><br>{e(reason)}</li>')
    return (
        '<details class="disclosure"><summary>Other setups checked</summary><ul>'
        + "".join(entries) + "</ul></details>"
        if entries else ""
    )


def recommendation(case, csrf, fixture):
    proposal = case.get("proposal")
    selected = proposal and case.get("selected_proposal") == proposal["hash"]
    if proposal:
        heading = "Your selected setup." if selected else "Your recommendation."
        order = proposal["actions"][0]["payload"]
        ordered = {row["product_id"]: row["quantity"] for row in order["items"]}
        items = [(value, ordered[value["product_id"]]) for value in proposal["evidence"].values()
                 if value["product_id"] in ordered]
        total = f'{money(order["total_tnd"])} TND'
        subtitle = "Open the listings to continue at the retailer." if selected and not fixture else "Verified against the product listings."
        choice = "" if selected else form(
            f'/shop/{case["case_id"]}', csrf, '<button class="button button-primary">Choose this setup <span aria-hidden="true">✓</span></button>',
            action="select", revision=case["revision"], proposal_hash=proposal["hash"],
        )
    else:
        heading, subtitle = HEADINGS.get(case["status"], ("Your search.", "Review the findings for this request."))
        if case.get("questions"):
            subtitle = case["questions"][0]
        candidates = {item["product_id"]: item for group in case["evidence"].values() for item in group}
        items = [(item, 1) for item in list(candidates.values())[:6]]
        total, choice = '', ''
    total_view = f'<p class="total"><span>Setup total</span><strong>{total}</strong></p>' if total else ""
    products = "".join(product_row(item, quantity, fixture) for item, quantity in items)
    extra_questions = "".join(f"<li>{e(question)}</li>" for question in case.get("questions", [])[1:])
    questions = f'<ul class="questions">{extra_questions}</ul>' if extra_questions else ""
    actions = f'<div class="result-actions">{choice}<button class="button button-light" type="button" data-listen hidden>Listen</button></div>' if proposal else ""
    evidence = verification(case["findings"], fixture)
    alternatives = alternatives_summary(case["alternatives"]) if proposal and len(items) > 1 else ""
    relationships = [finding for finding in case["findings"] if "->" in finding["code"] or finding["code"] == "direct_video"]
    connections = "".join(
        f'<li><span class="verdict {finding["verdict"]}">'
        f'{ {"pass": "✓ Connection verified", "fail": "Connection mismatch", "unknown": "Connection unverified"}[finding["verdict"]] }'
        f'</span> {e(finding["reason"])}</li>' for finding in relationships
    )
    connections = f'<ul class="connections">{connections}</ul>' if connections else ""
    events = [ACTIVITY[event["action"]] for event in case["trajectory"] if event["action"] in ACTIVITY]
    activity = (
        '<details class="disclosure"><summary>Search activity</summary><ol>'
        + "".join(f"<li>{label}</li>" for label in events[-18:]) + "</ol></details>"
        if events else ""
    )
    if case["status"] == "research_pending":
        followup = form(f'/shop/{case["case_id"]}', csrf, '<button class="button button-primary" data-search>Resume search</button>',
                        action="research")
    elif case["status"] in FOLLOW_UP:
        followup = search_form(csrf, case=case)
    else:
        followup = ""
    spoken = f'{heading} {subtitle} ' + (f'The total is {total}. ' if total else "") + " ".join(
        item["name"] for item, _ in items
    )
    return (
        f'<section class="results" data-spoken="{e(spoken)}">'
        '<div class="result-heading"><div><a class="back" href="/shop/">← New search</a>'
        f'<h1>{heading}</h1><p class="lede">{e(subtitle)}</p></div>{total_view}</div>{questions}'
        f'<div class="products">{products}</div>{connections}{actions}{evidence}{alternatives}{activity}{followup}</section>'
    )


def render_shop(csrf, *, fixture, case=None, error=""):
    body = home(csrf, fixture) if case is None else recommendation(case, csrf, fixture)
    source = "Test catalog" if fixture else "Live Tunisianet catalog"
    message = f'<p class="error" role="alert">{e(error)}</p>' if error else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>The Specialist · Find gear that fits</title>'
        '<link rel="stylesheet" href="/shop/assets/site.css">'
        '<script src="/shop/assets/site.js" defer></script></head>'
        '<body><header class="site-header"><a class="brand" href="/shop/">'
        '<span aria-hidden="true" class="brand-mark">✳</span>The Specialist</a>'
        f'<span class="source"><span class="source-dot"></span>{source}</span></header>'
        f'<main>{message}{body}</main></body></html>'
    )
