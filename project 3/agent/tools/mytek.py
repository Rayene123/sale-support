"""Read-only MYTEK catalog parser and bounded scraper interface.

MYTEK's current product listing markup has not yet been verified. The parser
supports schema.org Product JSON-LD so fixtures and future verified markup can
be tested deterministically; the network entry point fails closed until its
public listing URL and markup are verified. It never interacts with a cart.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from agent.tools.schemas import StrictSchema
from pydantic import Field


class ProductResult(StrictSchema):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    price_tnd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    availability: str = Field(pattern="^(available|in_stock|out_of_stock|unknown)$")
    retrieved_at: str


class _JSONLD(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_jsonld = False
        self.parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.in_jsonld = True
            self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_jsonld:
            self.documents.append("".join(self.parts))
            self.in_jsonld = False

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.parts.append(data)


def _walk_products(value: Any):
    if isinstance(value, dict):
        kind = value.get("@type", [])
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(item).casefold() == "product" for item in kinds):
            yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_products(graph)
        for key in ("itemListElement", "mainEntity", "hasVariant"):
            if key in value:
                yield from _walk_products(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from _walk_products(item)


def parse_product_html(html: str, *, page_url: str, retrieved_at: str | None = None) -> list[dict[str, Any]]:
    """Extract Product JSON-LD only; ignore all free-form descriptions."""
    parsed_url = urlparse(page_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {"www.mytek.tn", "mytek.tn"}:
        raise ValueError("Product source must be an HTTPS MYTEK page")
    if not isinstance(html, str) or len(html) > 2_000_000:
        raise ValueError("Invalid or oversized HTML document")
    parser = _JSONLD()
    parser.feed(html)
    stamp = retrieved_at or datetime.now(timezone.utc).isoformat()
    products: list[dict[str, Any]] = []
    for document in parser.documents:
        try:
            root = json.loads(document)
        except (json.JSONDecodeError, ValueError):
            continue
        for item in _walk_products(root):
            name = item.get("name")
            raw_url = item.get("url") or item.get("@id")
            product_url = page_url if not raw_url else urljoin(page_url, str(raw_url))
            parsed_product_url = urlparse(product_url)
            if not isinstance(name, str) or not name.strip() or parsed_product_url.hostname not in {"www.mytek.tn", "mytek.tn"}:
                continue
            sku = item.get("sku") or item.get("productID") or item.get("mpn") or re.sub(r"[^A-Za-z0-9_-]", "", parsed_product_url.path.rsplit("/", 1)[-1])
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict) and offers.get("priceCurrency") not in (None, "TND"):
                offers = {**offers, "price": None}
            raw_price = offers.get("price") if isinstance(offers, dict) else None
            price: Decimal | None = None
            if raw_price is not None:
                try:
                    candidate = Decimal(str(raw_price).replace(",", "."))
                    if candidate >= 0 and candidate.is_finite():
                        price = candidate.quantize(Decimal("0.01"))
                except (InvalidOperation, ValueError):
                    pass
            availability_raw = str(offers.get("availability", "")).rsplit("/", 1)[-1].casefold() if isinstance(offers, dict) else ""
            availability = ({"instock": "in_stock", "limitedavailability": "available", "onlineonly": "available", "outofstock": "out_of_stock"}.get(availability_raw, "unknown"))
            products.append(ProductResult(product_id=str(sku or product_url), name=name.strip()[:300],
                source_url=product_url, price_tnd=price, availability=availability,
                retrieved_at=stamp).model_dump(mode="json"))
    return products


def search_mytek_products(query: str, *, timeout: float = 8.0, max_pages: int = 3) -> dict[str, Any]:
    """Fail closed until MYTEK's public listing route/markup is verified.

    `timeout` and `max_pages` are bounded now so future networking cannot
    become unbounded. Ordinary execution performs no network request.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        return {"success": False, "error": "invalid_input", "message": "Provide a search query of 1 to 200 characters.", "retryable": False}
    if timeout <= 0 or timeout > 15 or max_pages < 1 or max_pages > 3:
        return {"success": False, "error": "invalid_input", "message": "Request bounds exceed the scraper limits.", "retryable": False}
    return {"success": False, "error": "scraper_unverified", "message": "MYTEK's public listing route and product markup are not verified; no request was made.", "retryable": False}
