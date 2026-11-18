"""Plain-language shopping conversations and product recommendations."""

from decimal import Decimal

from specialist.contracts.purchasing import catalog_image_url
from specialist.workflow.case_state import FOLLOW_UP

from .views import e, form


def amount(value):
    formatted = f"{Decimal(value):,.2f}".rstrip("0").rstrip(".")
    return f"{formatted} TND"


def mark():
    return '<span class="mark" aria-hidden="true"><span></span></span>'


def composer(csrf, case):
    path = f'/shop/{case["case_id"]}' if case else "/shop/"
    fields = {"action": "revise", "revision": case["revision"]} if case else {"action": "start"}
    return form(
        path, csrf,
        '<div class="composer"><label class="sr-only" for="message">Message The Specialist</label>'
        '<textarea id="message" name="request" rows="1" maxlength="1200" required data-message '
        'placeholder="I’m looking for…"></textarea>'
        '<button type="submit" class="send" aria-label="Send message">↑</button></div>', **fields,
    )


def reply_text(case):
    status = case["status"]
    if status == "awaiting_clarification":
        questions = case.get("questions") or case.get("requirements", {}).get("unanswered") or []
        return questions[0] if questions else "What’s your budget in TND?"
    if status == "verification_blocked":
        return "I couldn’t find a setup I’d recommend yet. Is there anything you’re flexible on?"
    if status == "source_unavailable":
        return "I couldn’t reach Tunisianet. Try sending your request again in a moment."
    if status == "step_limit_reached":
        return "I couldn’t finish this search. Try a new chat with a shorter request."
    if status == "research_pending":
        return "I paused partway through. Continue to see what I can find."
    return "I couldn’t finish the search. Try sending your request again."


def product_item(listing, quantity, fixture):
    name = listing["name"].split(" / ", 1)[0]
    image = catalog_image_url(listing.get("image_url")) if not fixture else None
    photo = (
        f'<img src="{e(image)}" alt="{e(name)}" loading="lazy" referrerpolicy="no-referrer">'
        if image else ""
    )
    media = f'<div class="photo">{photo}</div>' if photo else '<div class="photo placeholder" aria-hidden="true"></div>'
    price = amount(listing["price_tnd"])
    count = f'<span class="quantity">× {quantity}</span>' if quantity > 1 else ""
    details = f'{media}<span class="product-name">{e(name)} {count}</span><span class="price">{price}</span>'
    if fixture:
        return f'<li class="product">{details}</li>'
    return (
        '<li><a class="product" '
        f'href="{e(listing["source_url"])}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{e(name)}, {price}, view on Tunisianet">{details}'
        '<span class="external" aria-hidden="true">↗</span></a></li>'
    )


def shopping_list(case, csrf, fixture):
    proposal = case["proposal"]
    order = proposal["actions"][0]["payload"]
    items = order["items"]
    listings = {item["product_id"]: item for item in proposal["evidence"].values()}
    rows = "".join(product_item(listings[row["product_id"]], row["quantity"], fixture) for row in items)
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
    return (
        f'<div class="recommendation" data-spoken="{e(spoken)}"><p>{heading}</p>'
        f'<div class="shortlist"><ul>{rows}</ul><div class="list-foot">{choice}{total}</div></div>'
        '<button type="button" class="quiet-action listen" data-listen hidden>Read aloud</button></div>'
    )


def turn(case, csrf, fixture, *, latest=False):
    message = case.get("customer_message")
    question = f'<p class="user-message" aria-label="You">{e(message)}</p>' if message else ""
    if case.get("proposal") and latest:
        reply = shopping_list(case, csrf, fixture)
    elif case.get("proposal"):
        total = case["proposal"]["actions"][0]["payload"]["total_tnd"]
        reply = f'<p>I found an option for {amount(total)}.</p>'
    else:
        reply = f'<p>{e(reply_text(case))}</p>'
        if latest and case["status"] == "research_pending":
            reply += form(f'/shop/{case["case_id"]}', csrf, '<button class="quiet-action">Continue search</button>', action="research")
    focus = ' data-latest tabindex="-1"' if latest else ""
    return (
        f'<div class="turn">{question}<article class="assistant" aria-label="The Specialist"{focus}>'
        f'{mark()}<div class="answer">{reply}</div></article></div>'
    )


def render_shop(csrf, *, fixture, case=None, error=""):
    source = '<span class="test-source">Test catalog</span>' if fixture else ""
    message = f'<p class="error" role="alert">{e(error)}</p>' if error else ""
    if case is None:
        content = (
            '<section class="welcome"><h1>What are you shopping for?</h1>'
            '<div class="messages" aria-live="polite"></div>'
            f'{message}{composer(csrf, None)}</section>'
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
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>The Specialist</title>'
        '<link rel="stylesheet" href="/shop/assets/site.css">'
        '<script src="/shop/assets/site.js" defer></script></head>'
        f'<body><header class="site-header"><a class="brand" href="/shop/">{mark()}The Specialist</a>'
        f'<div class="header-actions">{source}<a class="new-chat" href="/shop/">＋ New chat</a></div></header>'
        f'<main id="shopping-chat">{content}</main></body></html>'
    )
