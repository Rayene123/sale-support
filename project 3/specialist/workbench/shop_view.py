"""Plain-language shopping conversations and product recommendations."""

from decimal import Decimal
import re

from specialist.contracts.purchasing import Listing, catalog_image_url
from specialist.contracts.text import COLOR_FIELDS, RAM_FIELDS, color_family, fold_text
from specialist.workflow.case_state import FOLLOW_UP
from specialist.workflow.shopping_intent import battery_hours

from .views import e, form


def amount(value):
    formatted = f"{Decimal(value):,.2f}".rstrip("0").rstrip(".")
    return f"{formatted} TND"


def mark():
    return '<span class="mark" aria-hidden="true"><span></span></span>'


def composer(csrf, case):
    path = f'/shop/{case["case_id"]}' if case else "/shop/"
    fields = {"action": "revise", "revision": case["revision"]} if case else {"action": "start"}
    placeholder = "Ask for a change…" if case else "I’m looking for…"
    return form(
        path, csrf,
        '<div class="composer"><label class="sr-only" for="message">Message The Specialist</label>'
        '<textarea id="message" name="request" rows="1" maxlength="1200" required data-message '
        f'placeholder="{placeholder}"></textarea>'
        '<button type="button" class="stop-search" data-stop hidden aria-label="Stop search">Stop</button>'
        '<button type="submit" class="send" aria-label="Send message">↑</button></div>', **fields,
    )


def reply_text(case):
    status = case["status"]
    if status == "awaiting_clarification":
        questions = case.get("questions") or case.get("requirements", {}).get("unanswered") or []
        return questions[0] if questions else "What’s your budget in TND?"
    if status == "verification_blocked":
        options = [option["findings"] for option in case.get("alternatives", [])]
        findings = min(options, key=lambda facts: sum(f["verdict"] != "pass" for f in facts),
                       default=case.get("findings", []))
        blockers = [fact for fact in findings if fact["verdict"] != "pass"]
        if len(blockers) == 1:
            fact = blockers[0]
            if fact["code"] == "total_budget" and fact["verdict"] == "fail":
                return "I couldn’t find a setup I’d recommend yet. A match I checked was over your budget."
            field = fold_text(fact["code"].partition(":")[2])
            if field in COLOR_FIELDS:
                return "I couldn’t confirm a match in the requested color within your budget."
            if field in RAM_FIELDS:
                value = next((ev["value"] for ev in fact["evidence"]), "")
                capacity = re.fullmatch(r"(\d+)\s*(?:GB|Go)", value, re.I)
                if capacity and fact["verdict"] == "fail":
                    return f"A listing that met your other requirements had only {capacity[1]} GB of RAM. I couldn’t confirm a full match."
                return "I couldn’t confirm that a listing meeting your other requirements had enough RAM."
        return "I couldn’t find a setup I’d recommend yet. Is there anything you’re flexible on?"
    if status == "source_unavailable":
        return "I couldn’t reach Tunisianet. Try sending your request again in a moment."
    if status == "step_limit_reached":
        return "I couldn’t finish this search. Try a new chat with a shorter request."
    if status == "research_pending":
        return "I paused partway through. Continue to see what I can find."
    return "I couldn’t finish the search. Try sending your request again."


def product_item(listing, quantity, fixture, *, single):
    name = listing["name"].split(" / ", 1)[0]
    image = catalog_image_url(listing.get("image_url")) if not fixture else None
    photo = (
        f'<button type="button" class="photo" data-photo="{e(image)}" data-name="{e(name)}" aria-label="Enlarge photo of {e(name)}">'
        f'<img src="{e(image)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>'
        if image else ""
    )
    price = amount(listing["price_tnd"])
    count = f'<span class="quantity">× {quantity}</span>' if quantity > 1 else ""
    link = "" if fixture else (
        f'<a class="retailer {"primary-retailer" if single else ""}" href="{e(listing["source_url"])}" '
        'target="_blank" rel="noopener noreferrer">View on Tunisianet <span aria-hidden="true">↗</span></a>'
    )
    return (f'<li class="product {"with-photo" if photo else ""}">{photo}'
            f'<div class="product-info"><span class="product-name">{e(name)}{count}</span>'
            f'<span class="price">{price}</span></div>{link}</li>')


def recommendation_reason(case, items, listings):
    prompt = " ".join(row.get("customer_message", "") for row in [*case["history"], case]).lower()
    if case.get("shop_rank_battery"):
        best = max((battery_hours(Listing.model_validate(listings[row["product_id"]])) for row in items), default=0)
        if best:
            return f"Tunisianet lists up to {best:g} hours of battery life."
    if len(items) > 1 and any("->" in fact["code"] and fact["verdict"] == "pass" for fact in case.get("findings", [])):
        return "These items work together and come in within your budget."
    if len(items) == 1:
        confirmed = {
            fold_text(fact["code"].partition(":")[2]): fact["evidence"][0]["value"]
            for fact in case.get("findings", []) if fact["verdict"] == "pass" and fact["evidence"]
        }
        color = next((color_family(value) for field, value in confirmed.items() if field in COLOR_FIELDS), None)
        ram = next((value for field, value in confirmed.items() if field in RAM_FIELDS), "")
        capacity = re.fullmatch(r"(\d+)\s*(?:GB|Go)", ram, re.I)
        if color and capacity:
            return f"It’s {color}, has {capacity[1]} GB of RAM, and is in stock within your budget."
    for row in items:
        listing = listings[row["product_id"]]
        ram = [value for field, value in listing.get("specs", {}).items()
               if re.search(r"\b(?:ram|mémoire vive|installed memory)\b", field, re.I)
               and not re.search(r"\b(?:max(?:imum)?|supported|up to|extensible|jusqu)\b", f"{field} {value}", re.I)]
        sizes = {int(n) for value in ram for n in re.findall(r"\b(\d+)\s*(?:GB|Go)\b", value, re.I)}
        if len(sizes) == 1 and any(word in prompt for word in ("coding", "programming", "tabs", "multitask", "vs code")):
            capacity = next(iter(sizes))
            if capacity >= 16:
                return f"The listing shows {capacity} GB of RAM, which gives you room for coding with other apps open."
    return "It’s in stock and fits your budget." if len(items) == 1 else "These are in stock and fit your budget."


def shopping_list(case, csrf, fixture):
    proposal = case["proposal"]
    order = proposal["actions"][0]["payload"]
    items = order["items"]
    listings = {item["product_id"]: item for item in proposal["evidence"].values()}
    rows = "".join(product_item(listings[row["product_id"]], row["quantity"], fixture, single=len(items) == 1) for row in items)
    total = f'<strong>{amount(order["total_tnd"])} total</strong>' if sum(row["quantity"] for row in items) > 1 else ""
    selected = case.get("selected_proposal") == proposal["hash"]
    if selected:
        choice = '<span class="saved">✓ Kept for this chat</span>'
    else:
        choice = form(
            f'/shop/{case["case_id"]}', csrf, '<button class="quiet-action">Keep this setup</button>',
            action="select", revision=case["revision"], proposal_hash=proposal["hash"],
        )
    heading = "Here’s what I’d get."
    spoken = heading + " " + " ".join(
        f'{listings[row["product_id"]]["name"].split(" / ", 1)[0]} for {amount(row["unit_price_tnd"])}.'
        for row in items
    )
    refresh = form(f'/shop/{case["case_id"]}', csrf, '<button class="quiet-action">Recheck price and stock</button>',
                   action="refresh", revision=case["revision"], proposal_hash=proposal["hash"])
    shortcuts = '<button type="button" class="shortcut" data-suggest="Find a cheaper one">Find a cheaper one</button>'
    if case.get("setup") and any(item["kind"] == "laptop" and not item["owned"] for item in case["setup"]["items"]):
        shortcuts += '<button type="button" class="shortcut" data-suggest="Prioritize battery life">Prioritize battery life</button>'
    reason = recommendation_reason(case, items, listings)
    notice = f'<p role="status">{e(case["shop_notice"])}</p>' if case.get("shop_notice") else ""
    return (
        f'<div class="recommendation" data-spoken="{e(spoken + " " + reason)}">{notice}<p>{heading} {e(reason)}</p>'
        f'<div class="shortlist"><ul>{rows}</ul><div class="list-total">{total}</div></div>'
        f'<div class="reply-actions">{choice}{refresh}'
        '<button type="button" class="quiet-action listen" data-listen hidden>Read aloud</button></div>'
        f'<div class="shortcuts">{shortcuts}</div></div>'
    )


def turn(case, csrf, fixture, *, latest=False):
    message = case.get("customer_message")
    question = f'<p class="user-message" aria-label="You">{e(message)}</p>' if message else ""
    if latest and case.get("shop_checkout_request"):
        question += f'<p class="user-message" aria-label="You">{e(case["shop_checkout_request"])}</p>'
    if case.get("proposal") and latest:
        reply = shopping_list(case, csrf, fixture)
    elif case.get("proposal"):
        total = case["proposal"]["actions"][0]["payload"]["total_tnd"]
        reply = f'<p>I found an option for {amount(total)}.</p>'
    else:
        line = case.get("shop_notice") if latest else None
        reply = f'<p>{e(line or reply_text(case))}</p>'
        if latest and case["status"] == "research_pending":
            reply += form(f'/shop/{case["case_id"]}', csrf, '<button class="quiet-action">Continue search</button>', action="research")
    focus = ' data-latest tabindex="-1"' if latest else ""
    return (
        f'<div class="turn">{question}<article class="assistant" aria-label="The Specialist"{focus}>'
        f'{mark()}<div class="answer">{reply}</div></article></div>'
    )


def render_shop(csrf, *, fixture, case=None, error="", recent=()):
    source = '<span class="test-source">Test catalog</span>' if fixture else ""
    message = f'<p class="error" role="alert">{e(error)}</p>' if error else ""
    if case is None:
        content = (
            f'<section class="welcome"><div class="welcome-mark">{mark()}</div><h1>What are you shopping for?</h1>'
            '<div class="messages" aria-live="polite"></div>'
            f'<div class="composer-dock">{message}{composer(csrf, None)}</div></section>'
        )
    else:
        prior = "".join(turn(snapshot, csrf, fixture) for snapshot in case["history"] if snapshot.get("customer_message"))
        input_area = (
            f'<div class="composer-dock">{message}{composer(csrf, case)}</div>'
            if case["status"] in FOLLOW_UP else message
        )
        content = (
            '<div class="conversation"><h1 class="sr-only">Shopping conversation</h1>'
            f'<section class="messages" aria-label="Conversation" aria-live="polite">'
            f'{prior}{turn(case, csrf, fixture, latest=True)}</section>{input_area}</div>'
        )
    entries = "".join(
        f'<li><a href="/shop/{e(identifier)}">{e(" ".join(label.split())[:70])}</a></li>'
        for identifier, label in recent
    )
    menu = f'<details class="recent"><summary>Recent chats</summary><ul>{entries}</ul></details>' if entries else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">'
        '<title>The Specialist</title>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400..700&amp;display=swap">'
        '<link rel="stylesheet" href="/shop/assets/site.css">'
        '<script src="/shop/assets/site.js" defer></script></head>'
        f'<body><header class="site-header" id="shop-header"><a class="brand" href="/shop/">{mark()}The Specialist</a>'
        f'<div class="header-actions">{source}{menu}<a class="new-chat" href="/shop/">＋ New chat</a></div></header>'
        f'<main id="shopping-chat">{content}<dialog class="photo-dialog" aria-label="Product photo">'
        '<form method="dialog"><button class="quiet-action" aria-label="Close photo">Close</button></form>'
        '<img alt="" referrerpolicy="no-referrer"></dialog></main></body></html>'
    )
