"""Parse retailer HTML into structured, bounded product data."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from pydantic import Field

from specialist.contracts.validation import StrictSchema


def _availability(text: str) -> str:
    normalized = text.casefold().replace("-", " ").replace("_", " ")
    if any(term in normalized for term in ("unavailable", "indisponible", "out of stock", "rupture", "not available")):
        return "out_of_stock"
    if any(term in normalized for term in ("in stock", "en stock", "disponible", "available")):
        return "in_stock"
    if "later stock" in normalized:
        return "available"
    return "unknown"


class ProductResult(StrictSchema):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    price_tnd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    availability: str = Field(pattern="^(available|in_stock|out_of_stock|unknown)$")
    retrieved_at: str
    color: str | None = Field(default=None, max_length=80)
    weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=3)
    characteristics: dict[str, str] | None = None


def _product_weight(value: Any) -> Decimal | None:
    unit = "kg"
    amount: Any = value
    if isinstance(value, dict):
        amount = value.get("value")
        unit = str(value.get("unitCode") or value.get("unitText") or "kg").lower()
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|kilograms?|g|grams?)\s*", value, re.I)
        if not match:
            return None
        amount, unit = match.groups()
        unit = unit.lower()
    try:
        weight = Decimal(str(amount).replace(",", "."))
        if not weight.is_finite() or weight < 0:
            return None
        if unit in {"g", "gram", "grams", "GRM".lower()}:
            weight /= Decimal("1000")
        elif unit not in {"kg", "kgs", "kilogram", "kilograms", "kgm"}:
            return None
        return weight.quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _product_characteristics(value: Any) -> dict[str, str] | None:
    if not isinstance(value, list):
        return None
    result: dict[str, str] = {}
    for entry in value[:10]:
        if not isinstance(entry, dict):
            continue
        name, prop_value = entry.get("name"), entry.get("value")
        if isinstance(name, str) and name.strip() and isinstance(prop_value, (str, int, float, bool)):
            result[name.strip()[:80]] = str(prop_value).strip()[:120]
    return result or None


class _JSONLD(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_jsonld = False
        self.parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
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
    """Extract structured Product data; ignore free-form descriptions."""
    parsed_url = urlparse(page_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {"www.tunisianet.com.tn", "tunisianet.com.tn", "www.mytek.tn", "mytek.tn"}:
        raise ValueError("Product source must be an HTTPS approved Tunisian catalog page")
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
            if not isinstance(name, str) or not name.strip() or parsed_product_url.hostname not in {"www.tunisianet.com.tn", "tunisianet.com.tn", "www.mytek.tn", "mytek.tn"}:
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
            normalized = ProductResult(product_id=str(sku or product_url), name=name.strip()[:300],
                source_url=product_url, price_tnd=price, availability=availability,
                retrieved_at=stamp, color=str(item["color"])[:80] if item.get("color") else None,
                weight_kg=_product_weight(item.get("weight")),
                characteristics=_product_characteristics(item.get("additionalProperty")))
            product = normalized.model_dump(mode="json", exclude_none=True)
            product["price_tnd"] = str(price) if price is not None else None
            products.append(product)
    return products


class _CatalogCards(HTMLParser):
    """Small parser for Tunisianet's visible product-card markup."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.capture: tuple[str, int] | None = None
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        if tag == "article" and "product-miniature" in (data.get("class") or ""):
            self.current = {"product_id": data.get("data-id-product", ""), "name": "", "source_url": "", "price_raw": "", "availability": "unknown"}
            self.depth = 1
            return
        if self.current is None:
            return
        self.depth += 1
        itemprop = data.get("itemprop")
        if tag == "a" and data.get("href") and not self.current["source_url"]:
            self.current["source_url"] = data["href"]
        if itemprop in {"name", "price", "availability"}:
            if itemprop == "price" and self.current["price_raw"]:
                return
            if itemprop == "price" and data.get("content"):
                self.current["price_raw"] = data["content"]
            else:
                self.capture = (itemprop, self.depth)
        availability = _availability(data.get("class") or "")
        if availability != "unknown" and self.current["availability"] != "out_of_stock":
            self.current["availability"] = availability

    def handle_data(self, data: str) -> None:
        if not self.current:
            return
        if self.capture:
            field, _ = self.capture
            if field == "name":
                self.current[field] += data
            elif field == "price":
                self.current["price_raw"] += data
            elif field == "availability":
                availability = _availability(data)
                if availability != "unknown" and self.current["availability"] != "out_of_stock":
                    self.current["availability"] = availability

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if self.capture and self.depth == self.capture[1]:
            self.capture = None
        self.depth -= 1
        if tag == "article":
            self.items.append(self.current)
            self.current = None


def _tnd_price(value: str) -> Decimal | None:
    raw = re.sub(r"[^0-9,.]", "", value.replace("\xa0", "").replace("\u202f", ""))
    if not raw:
        return None
    # Tunisianet shows prices as 1 299,000 DT: comma is the decimal marker.
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


class _ProductFeatures(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.capture: tuple[str, int] | None = None
        self.label = ""
        self.value = ""
        self.features: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        self.depth += 1
        classes = data.get("class") or ""
        if tag == "dt" and "name" in classes.split():
            self.capture = ("label", self.depth)
            self.label = ""
        elif tag == "dd" and "value" in classes.split():
            self.capture = ("value", self.depth)
            self.value = ""

    def handle_data(self, data: str) -> None:
        if self.capture:
            target = self.capture[0]
            if target == "label":
                self.label += data
            else:
                self.value += data

    def handle_endtag(self, tag: str) -> None:
        if self.capture and self.depth == self.capture[1]:
            if self.capture[0] == "value" and self.label.strip() and self.value.strip():
                self.features[self.label.strip()[:80]] = re.sub(r"\s+", " ", self.value).strip()[:120]
            self.capture = None
        self.depth = max(0, self.depth - 1)


class _DetailMetadata(HTMLParser):
    """Read exact-page offer facts when the retailer uses microdata instead of JSON-LD."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        key = data.get("property") or data.get("itemprop") or data.get("rel")
        value = data.get("content") or data.get("href")
        accepted = {"canonical", "og:title", "product:price:amount", "product:price:currency",
                    "price", "priceCurrency", "availability"}
        if key in accepted and isinstance(value, str):
            self.values.setdefault(key, set()).add(value.strip())

    def row(self, product_id, source_url):
        names = self.values.get("og:title", set())
        canonicals = self.values.get("canonical", set())
        prices = self.values.get("product:price:amount", set()) | self.values.get("price", set())
        currencies = self.values.get("product:price:currency", set()) | self.values.get("priceCurrency", set())
        statuses = self.values.get("availability", set())
        path = urlparse(source_url).path
        if (canonicals != {source_url} or len(names) != 1
                or not re.search(r"/" + re.escape(product_id) + r"-[^/]+\.html$", path)):
            return None
        normalized = {_tnd_price(value) for value in prices}
        price = next(iter(normalized)) if len(normalized) == 1 and currencies == {"TND"} else None
        availability = "unknown"
        if len(statuses) == 1:
            slug = next(iter(statuses)).rsplit("/", 1)[-1].lower()
            availability = {"instock": "in_stock", "outofstock": "out_of_stock"}.get(slug, "unknown")
        return {"product_id": product_id, "name": next(iter(names))[:300], "source_url": source_url,
                "price_tnd": str(price) if price is not None else None, "availability": availability,
                "retrieved_at": datetime.now(timezone.utc).isoformat()}


class _ExactShortSpecs(HTMLParser):
    """Keep only recognized specification fragments in this product's own summary."""

    def __init__(self, product_id):
        super().__init__(convert_charrefs=True)
        self.target_id = "product-description-short-" + product_id
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "div" and (self.depth or dict(attrs).get("id") == self.target_id):
            self.depth += 1
        if self.depth and tag in {"li", "br", "p"}:
            self.parts.append(" - ")

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and len(self.parts) < 120:
            self.parts.append(data[:500])

    def specs(self):
        result = {}
        ports = []
        for segment in re.split(r"\s+[–—-]\s+|[\r\n]+", " ".join(self.parts)):
            segment = " ".join(segment.split()).strip()
            if not segment or len(segment) > 240:
                continue
            if re.fullmatch(
                r"(?:(?:ports? vid[ée]o|connectique|ports?|entr[ée]es?|sorties?)\s*:\s*)?"
                r"\d+\s*[x×]\s*(?:ports?\s+)?(?:HDMI|DisplayPort|\bDP\b|(?:USB[- ]?C|type[- ]?c).*(?:DP|DisplayPort)\s+Alt Mode).*",
                segment, re.I,
            ):
                ports.append(segment)
            match = re.match(
                r"(?:r[ée]solution(?:\s+(?:du panneau|native))?|d[ée]finition)"
                r"\s*:?\s*(?:Full HD|FHD|QHD|UHD|4K)?\s*\(?([0-9]{4}\s*[x×]\s*[0-9]{4})\b",
                segment, re.I,
            )
            if match:
                result["Listing resolution"] = match.group(1).strip()
        if ports:
            result["Listing video ports"] = "; ".join(ports)[:240]
        return result
