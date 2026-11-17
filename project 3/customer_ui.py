"""Customer-only product search and sandbox order view for the local demo."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from agent import tools
from agent.graph import run_operator
from agent.tools.mytek import search_tunisianet_products


def _e(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _customer_executor(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "find_customer":
        customer = tools.find_customer(payload.get("customer_id", ""))
        return {"customer_id": customer["customer_id"], "name": customer["name"]}
    if name == "search_tunisianet_products":
        return search_tunisianet_products(payload.get("query", ""), criteria=payload.get("criteria"))
    raise RuntimeError("Trusted sandbox order approval service is not configured for this local demo")


def _criteria(form: dict[str, list[str]]) -> dict[str, Any]:
    value = lambda key: form.get(key, [""])[0].strip()
    if value("criteria_json"):
        parsed = json.loads(value("criteria_json"))
        if not isinstance(parsed, dict):
            raise ValueError("Search criteria are invalid")
        return parsed
    result = {}
    for key in ("name", "price_min_tnd", "price_max_tnd", "color", "weight_min_kg", "weight_max_kg"):
        if value(key):
            result[key] = value(key)
    attributes = {}
    for raw_pair in value("characteristics").replace(",", ";").split(";"):
        if "=" in raw_pair:
            key, item = raw_pair.split("=", 1)
            if key.strip() and item.strip():
                attributes[key.strip()] = item.strip()
    if attributes:
        result["characteristics"] = attributes
    return result


def _request(customer_id: str, query: str, criteria: dict[str, Any], prompt: str | None = None,
             parser: str | None = None) -> dict[str, Any]:
    prompt = prompt if prompt is not None else query
    query = query or "product search"
    request = {"request_type": "product_order", "customer_id": customer_id,
               "product_query": query, "request_text": prompt, "product_criteria": criteria}
    if parser:
        request["product_prompt_parser"] = parser
    return request


def _layout(content: str, notice: str = "") -> str:
    notice_class = " error" if "unavailable" in notice.lower() or "could not" in notice.lower() else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shopline · Customer shop</title><style>
:root{{--ink:#17221e;--muted:#718078;--line:#e6ebe7;--green:#176b50;--canvas:#f4f7f4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}}
header{{height:68px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 max(22px,calc((100vw - 1120px)/2))}}
.brand{{font-weight:760;display:flex;align-items:center;gap:10px}}.mark{{width:34px;height:34px;border-radius:11px;background:var(--green);color:white;display:grid;place-items:center}}
.tag,.muted{{font-size:11px;color:var(--muted)}}main{{width:min(1120px,100%);margin:auto;padding:40px 22px 60px}}.eyebrow{{color:#668174;text-transform:uppercase;font-size:10px;font-weight:760;letter-spacing:1.2px}}
h1{{font-size:32px;line-height:1.15;letter-spacing:-.8px;margin:7px 0}}.intro{{color:var(--muted);margin:0;max-width:700px}}.card{{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 5px 20px #142b1a08;margin-top:18px;overflow:hidden}}
.head{{padding:17px 20px;border-bottom:1px solid #edf0ee;display:flex;align-items:center;justify-content:space-between;gap:10px}}.body{{padding:20px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}}
label{{display:block;font-weight:650;font-size:11px;color:#65736b;margin:0 0 5px}}input,textarea{{width:100%;padding:12px 13px;border:1px solid #dce4de;border-radius:9px;font:inherit;min-width:0}}input:focus,textarea:focus{{outline:3px solid #d6ebdc;border-color:#7db08e}}textarea{{resize:vertical;min-height:118px;line-height:1.5}}
button{{border:0;border-radius:9px;padding:11px 16px;font:inherit;font-size:12px;font-weight:720;background:var(--green);color:#fff;cursor:pointer}}button.secondary{{background:#fff;color:#4d5b53;border:1px solid var(--line)}}
.notice{{padding:13px 16px;background:#eef7f0;border:1px solid #d8e9dc;border-radius:10px;color:#315b43;margin-bottom:17px}}.notice.error{{background:#fff4f1;border-color:#efd8d2;color:#8b4037}}
.products{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.product{{border:1px solid var(--line);border-radius:11px;padding:14px;display:flex;gap:12px}}.product input[type=checkbox]{{width:17px;height:17px;margin-top:3px;accent-color:var(--green)}}.product h3{{font-size:14px;margin:0 0 4px}}.price{{color:var(--green);font-size:17px;font-weight:760}}.bottom{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:17px}}.errors{{color:#8b4037}}.row{{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:10px 0}}
@media(max-width:700px){{main{{padding:28px 15px}}header{{padding:0 15px}}h1{{font-size:27px}}.products{{grid-template-columns:1fr}}.bottom{{align-items:flex-start;flex-direction:column}}}}
</style></head><body><header><div class="brand"><span class="mark">S</span>Shopline <span class="tag">CUSTOMER SHOP</span></div><span class="tag">Product orders</span></header>
<main><div class="eyebrow">Tunisianet catalog · Customer orders</div><h1>Find the right product</h1><p class="intro">Describe what you need in your own words. The shop will identify product details and filters, then show matching items for you to choose.</p>
{f'<div class="notice{notice_class}">{_e(notice)}</div>' if notice else ''}{content}<p class="muted" style="margin-top:20px">Local demo only. No retailer checkout, payment, or customer message is performed.</p></main></body></html>"""


def _search_form(prompt: str = "") -> str:
    return f"""<section class="card"><div class="head"><div><div class="eyebrow">Product finder</div><strong>Tell us what you’re looking for</strong></div><span class="tag">Natural language search</span></div><div class="body"><form method="post" action="/shop"><input type="hidden" name="action" value="search"><input type="hidden" name="customer_id" value="CUST-001">
<label for="prompt">Product request</label><textarea id="prompt" name="prompt" required maxlength="1000" placeholder="For example: Find a white 12000 BTU air conditioner under 1,800 TND with inverter">{_e(prompt)}</textarea><p class="muted">Include any details you care about, such as price, color, weight, capacity, or features.</p><button type="submit">Find products →</button></form></div></section>"""


def _error_card(result: dict) -> str:
    errors = "<br>".join(_e(error) for error in result.get("errors", [])) or "No matching products are available right now."
    return f"<section class='card'><div class='body'><div class='eyebrow'>Search status</div><strong>{_e(str(result.get('status','failed')).replace('_',' ').title())}</strong><p class='errors'>{errors}</p></div></section>"


def _render(result: dict, request: dict) -> str:
    status = result.get("status")
    content = _search_form(str(result.get("request_text") or request.get("request_text") or ""))
    parser_mode = result.get("product_prompt_parser")
    if parser_mode == "llm":
        content += f"<div class='notice'>AI interpreted this as <strong>{_e(result.get('product_query'))}</strong> and applied the requested filters.</div>"
    elif parser_mode == "rules_fallback":
        content += "<div class='notice error'>The AI parser is temporarily unavailable, so basic prompt parsing was used for this search.</div>"
    if status == "awaiting_customer_selection":
        cards = []
        for product in result.get("products", []):
            pid = str(product.get("product_id", ""))
            stock = product.get("availability") in {"available", "in_stock", "in stock"}
            price = product.get("price_tnd")
            disabled = "disabled" if not stock or price is None else ""
            source = str(product.get("source_url", ""))
            link = f"<a href='{_e(source)}' target='_blank' rel='noopener'>Tunisianet source ↗</a>" if source.startswith(("https://tunisianet.com.tn/", "https://www.tunisianet.com.tn/")) else ""
            attrs = product.get("characteristics") or {}
            details = [f"{_e(k)}: {_e(v)}" for k, v in attrs.items()]
            for key in ("color", "weight_kg"):
                if product.get(key) is not None:
                    details.append(f"{_e(key)}: {_e(product[key])}")
            cards.append(f"<div class='product'><input type='checkbox' name='product_id' value='{_e(pid)}' {disabled}><div><h3>{_e(product.get('name'))}</h3><div class='price'>{_e(price if price is not None else 'Price unavailable')} TND</div><p class='muted'>{_e(product.get('availability'))} · {' · '.join(details)}</p>{link}<label>Quantity</label><input type='number' name='qty_{_e(pid)}' value='1' min='1' max='10' {disabled}></div></div>")
        criteria = _e(json.dumps(result.get("product_criteria", request.get("product_criteria", {})), ensure_ascii=False))
        prompt = _e(result.get("request_text") or request.get("request_text", ""))
        query = _e(result.get("product_query") or request.get("product_query", ""))
        hidden = f"<input type='hidden' name='action' value='select'><input type='hidden' name='run_id' value='{_e(result.get('run_id'))}'><input type='hidden' name='customer_id' value='{_e(request['customer_id'])}'><input type='hidden' name='product_query' value='{query}'><input type='hidden' name='request_text' value='{prompt}'><input type='hidden' name='criteria_json' value='{criteria}'><input type='hidden' name='product_prompt_parser' value='{_e(parser_mode)}'>"
        content += f"<section class='card'><div class='head'><div><div class='eyebrow'>Matching products</div><strong>Choose products and quantities</strong></div><span class='tag'>{len(cards)} result(s)</span></div><div class='body'><form method='post' action='/shop'>{hidden}<div class='products'>{''.join(cards) or 'No matching products.'}</div><div class='bottom'><span class='muted'>Selected items are validated again by the agent.</span><button type='submit'>Review order →</button></div></form></div></section>"
    elif status == "awaiting_approval":
        draft = result.get("draft") or {}
        lines = "".join(f"<div class='row'><span>{_e(item.get('name'))} × {_e(item.get('quantity'))}</span><strong>{_e(item.get('line_total_tnd'))} TND</strong></div>" for item in draft.get("items", []))
        criteria = _e(json.dumps(result.get("product_criteria", request.get("product_criteria", {})), ensure_ascii=False))
        prompt = _e(result.get("request_text") or request.get("request_text", ""))
        query = _e(result.get("product_query") or request.get("product_query", ""))
        hidden = f"<input type='hidden' name='run_id' value='{_e(result.get('run_id'))}'><input type='hidden' name='customer_id' value='{_e(request['customer_id'])}'><input type='hidden' name='product_query' value='{query}'><input type='hidden' name='request_text' value='{prompt}'><input type='hidden' name='criteria_json' value='{criteria}'><input type='hidden' name='product_prompt_parser' value='{_e(parser_mode)}'><input type='hidden' name='operation_id' value='{_e(draft.get('operation_id'))}'>"
        content += f"<section class='card'><div class='head'><div><div class='eyebrow'>Order review</div><strong>Confirm the exact sandbox order</strong></div><span class='tag'>Your confirmation is required</span></div><div class='body'>{lines}<div class='bottom'><strong>Total: {_e(draft.get('total_tnd'))} TND</strong><div><form method='post' action='/shop' style='display:inline'>{hidden}<input type='hidden' name='action' value='decline'><button type='submit' class='secondary'>Decline</button></form> <form method='post' action='/shop' style='display:inline'>{hidden}<input type='hidden' name='action' value='confirm'><button type='submit'>Confirm sandbox order</button></form></div></div></div></section>"
    elif status not in {None, ""}:
        content += _error_card(result)
    return _layout(content)


def handle_shop(form: dict[str, list[str]]) -> tuple[str, int]:
    value = lambda key: form.get(key, [""])[0].strip()
    action = value("action")
    try:
        if action == "search":
            customer_id = value("customer_id") or "CUST-001"
            prompt = value("prompt")
            if not prompt or len(prompt) > 1000:
                return _layout(_search_form(prompt), "Enter a product request up to 1,000 characters."), 400
            request = _request(customer_id, prompt, {}, prompt)
            result = run_operator(request, tool_executor=_customer_executor)
            return _render(result, request), 200

        criteria = _criteria(form)
        prompt = value("request_text")
        request = _request(value("customer_id"), value("product_query"), criteria, prompt,
                           value("product_prompt_parser"))
        if action == "select":
            items = []
            for product_id in form.get("product_id", []):
                raw_qty = value(f"qty_{product_id}") or "1"
                items.append({"product_id": product_id, "quantity": int(raw_qty)})
            result = run_operator(request, run_id=value("run_id"), selection={"items": items}, tool_executor=_customer_executor)
        elif action in {"confirm", "decline"}:
            decision = "approve" if action == "confirm" else "reject"
            result = run_operator(request, {"decision": decision, "operation_id": value("operation_id")}, run_id=value("run_id"), tool_executor=_customer_executor)
        else:
            return _layout(_search_form(prompt), "Could not process the product request."), 400
        return _render(result, request), 200
    except Exception as exc:
        return _layout(_search_form(value("prompt") or value("request_text")), f"Could not process the request: {_e(exc)}"), 400
