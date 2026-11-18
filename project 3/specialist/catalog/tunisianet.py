"""Read-only Tunisianet catalog search. Never interacts with a cart."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import threading
import time
from functools import lru_cache
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from .criteria import SearchCriteria
from .html import (
    _CatalogCards, _DetailMetadata, _ExactShortSpecs, _ProductFeatures,
    _product_weight, _tnd_price, parse_product_html,
)

_FETCH_LOCK = threading.Lock()
_LAST_FETCH = 0.0


_HOSTS = {"www.tunisianet.com.tn", "tunisianet.com.tn"}
_MAX_BYTES = 3_000_000


def _bounded_get(url: str, *, timeout: float) -> requests.Response:
    """Stream a bounded body and validate each redirect before requesting it."""
    global _LAST_FETCH
    for hop in range(4):
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise requests.RequestException("Malformed catalog URL") from exc
        if (parsed.scheme != "https" or parsed.hostname not in _HOSTS
                or parsed.username or parsed.password or port not in (None, 443)):
            raise requests.RequestException("Catalog URL outside the HTTPS allowlist")
        with _FETCH_LOCK:
            delay = 1.0 - (time.monotonic() - _LAST_FETCH)
            if delay > 0:
                time.sleep(delay)
            try:
                response = requests.get(url, timeout=timeout, stream=True, allow_redirects=False,
                    headers={"User-Agent": "ShoplineDemo/1.0 (read-only product search)",
                             "Accept": "text/html,application/xhtml+xml,text/plain"})
            finally:
                _LAST_FETCH = time.monotonic()
        try:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise requests.RequestException("Redirect without destination")
                url = urljoin(url, location)
                continue
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > _MAX_BYTES:
                    raise requests.RequestException("Catalog response exceeded size limit")
                chunks.append(chunk)
            response._content = b"".join(chunks)
            response._content_consumed = True
            return response
        finally:
            response.close()
    raise requests.TooManyRedirects("Catalog redirect limit exceeded")


def _catalog_row(card, source, retrieved_at, *, require_exact_id):
    href = urljoin(source, str(card["source_url"]))
    name = re.sub(r"\s+", " ", str(card["name"])).strip()
    product_id = card["product_id"]
    if urlparse(href).hostname not in _HOSTS or not name or (require_exact_id and not product_id):
        return None
    price = _tnd_price(str(card["price_raw"]))
    return {
        "product_id": str(product_id or href),
        "name": name[:300],
        "source_url": href,
        "price_tnd": str(price) if price is not None else None,
        "availability": card["availability"],
        "retrieved_at": retrieved_at,
    }


@lru_cache(maxsize=1)
def _robots_parser() -> RobotFileParser:
    url = "https://www.tunisianet.com.tn/robots.txt"
    response = _bounded_get(url, timeout=5)
    response.raise_for_status()
    parser = RobotFileParser()
    parser.set_url(url)
    parser.parse(response.text.splitlines())
    return parser


def search_tunisianet_products(query: str, *, criteria: dict[str, Any] | None = None,
                               timeout: float = 8.0, max_results: int = 24) -> dict[str, Any]:
    """Fetch one public search-results page, respecting robots.txt and bounds."""
    if not isinstance(query, str) or len(query) > 200:
        return {"success": False, "error": "invalid_input", "message": "Provide a search query of 1 to 200 characters.", "retryable": False}
    try:
        filters = SearchCriteria.model_validate(criteria or {})
    except Exception:
        return {"success": False, "error": "invalid_input", "message": "Product filters are invalid.", "retryable": False}
    query = query.strip() or (filters.name or "").strip()
    if not query:
        return {"success": False, "error": "invalid_input", "message": "Provide a product name or search query.", "retryable": False}
    if timeout <= 0 or timeout > 15 or max_results < 1 or max_results > 24:
        return {"success": False, "error": "invalid_input", "message": "Request bounds exceed the scraper limits.", "retryable": False}
    search_url = "https://www.tunisianet.com.tn/recherche?controller=search&s=" + requests.utils.quote(query, safe="")
    try:
        if not _robots_parser().can_fetch("ShoplineDemo/1.0", search_url):
            return {"success": False, "error": "robots_disallowed", "message": "Tunisianet robots.txt disallows this search URL.", "retryable": False}
        response = _bounded_get(search_url, timeout=timeout)
        if response.status_code in (403, 429):
            return {"success": False, "error": "source_blocked", "message": f"Tunisianet returned HTTP {response.status_code}; search paused without retrying.", "retryable": False}
        response.raise_for_status()
        if len(response.content) > 3_000_000:
            return {"success": False, "error": "response_too_large", "message": "Tunisianet response exceeded the size limit.", "retryable": False}
        response.encoding = response.apparent_encoding or response.encoding
        parser = _CatalogCards()
        parser.feed(response.text)
        stamp = datetime.now(timezone.utc).isoformat()
        rows = []
        for card in parser.items[:max_results]:
            row = _catalog_row(card, search_url, stamp, require_exact_id=False)
            if row is not None and row["price_tnd"] is not None:
                rows.append(row)
        # Product attributes live on detail pages. Fetch only a small bounded
        # candidate set, and only when the customer requested attribute filters.
        if filters.color or filters.weight_min_kg is not None or filters.weight_max_kg is not None or filters.characteristics:
            for product in rows[:8]:
                detail_url = product["source_url"]
                if not _robots_parser().can_fetch("ShoplineDemo/1.0", detail_url):
                    continue
                detail = _bounded_get(detail_url, timeout=timeout)
                if detail.status_code in (403, 429):
                    break
                detail.raise_for_status()
                if len(detail.content) > 3_000_000:
                    continue
                detail.encoding = detail.apparent_encoding or detail.encoding
                feature_parser = _ProductFeatures()
                feature_parser.feed(detail.text)
                if feature_parser.features:
                    product["characteristics"] = feature_parser.features
                    for key, value in feature_parser.features.items():
                        if key.casefold() in {"couleur", "color", "colour"}:
                            product["color"] = value
                        elif key.casefold() in {"poids", "weight", "poids du produit"}:
                            weight = _product_weight(value)
                            product["weight_kg"] = str(weight) if weight is not None else None
        return {"success": True, "data": {"products": rows, "source": "tunisianet", "query": query}}
    except requests.Timeout:
        return {"success": False, "error": "source_timeout", "message": "Tunisianet search timed out.", "retryable": True}
    except requests.RequestException:
        return {"success": False, "error": "source_unavailable", "message": "Tunisianet search is temporarily unavailable.", "retryable": True}


def search_mytek_products(query: str, *, criteria: dict[str, Any] | None = None,
                          timeout: float = 8.0, max_pages: int = 3) -> dict[str, Any]:
    """Compatibility alias; catalog searching now uses approved Tunisianet."""
    if not isinstance(query, str) or len(query) > 200:
        return {"success": False, "error": "invalid_input", "message": "Provide a search query of 1 to 200 characters.", "retryable": False}
    try:
        filters = SearchCriteria.model_validate(criteria or {})
    except Exception:
        return {"success": False, "error": "invalid_input", "message": "Product filters are invalid.", "retryable": False}
    if not query.strip() and not (filters.name or filters.color or filters.characteristics):
        return {"success": False, "error": "invalid_input", "message": "Provide a product name or search query.", "retryable": False}
    if (filters.price_min_tnd is not None and filters.price_max_tnd is not None
            and filters.price_min_tnd > filters.price_max_tnd):
        return {"success": False, "error": "invalid_input", "message": "Minimum price cannot exceed maximum price.", "retryable": False}
    if timeout <= 0 or timeout > 15 or max_pages < 1 or max_pages > 3:
        return {"success": False, "error": "invalid_input", "message": "Request bounds exceed the scraper limits.", "retryable": False}
    return search_tunisianet_products(query, criteria=criteria, timeout=timeout, max_results=max_pages * 8)

_SPECIALIST_LISTS = {
    "pc portable": "/702-ordinateur-portable?order=product.price.asc",
    "ordinateur portable": "/702-ordinateur-portable?order=product.position.asc",
    "écran pc": "/667-ecran-pc-tunisie?order=product.price.asc",
    "moniteur": "/667-ecran-pc-tunisie?order=product.position.asc",
}


def search_specialist_catalog(query: str, *, max_results: int = 6) -> dict[str, Any]:
    """Search inside a published product category, with a fixed result bound."""
    path = _SPECIALIST_LISTS.get(query)
    if not path or not 1 <= max_results <= 6:
        return {"success": False, "error": "invalid_product_source"}
    source = "https://www.tunisianet.com.tn" + path
    try:
        if not _robots_parser().can_fetch("ShoplineDemo/1.0", source):
            return {"success": False, "error": "robots_disallowed"}
        response = _bounded_get(source, timeout=8)
        if response.status_code in (403, 429):
            return {"success": False, "error": "source_blocked"}
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        parser = _CatalogCards()
        parser.feed(response.text)
        stamp = datetime.now(timezone.utc).isoformat()
        rows = []
        for card in parser.items:
            row = _catalog_row(card, source, stamp, require_exact_id=True)
            if row is not None:
                rows.append(row)
                if len(rows) >= max_results:
                    break
        return {"success": True, "data": {"products": rows}}
    except requests.RequestException:
        return {"success": False, "error": "source_unavailable"}


def inspect_tunisianet_product(product_id: str, source_url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    """Read one exact product page and its published offer and structured specs."""
    try:
        parsed = urlparse(source_url)
        if (parsed.scheme != "https" or parsed.hostname not in _HOSTS
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or not parsed.path.endswith(".html")
                or parsed.query or parsed.fragment or not product_id
                or not 0 < timeout <= 15):
            return {"success": False, "error": "invalid_product_source"}
        if not _robots_parser().can_fetch("ShoplineDemo/1.0", source_url):
            return {"success": False, "error": "robots_disallowed"}
        response = _bounded_get(source_url, timeout=timeout)
        if response.status_code in (403, 429):
            return {"success": False, "error": "source_blocked"}
        response.raise_for_status()
        actual = urlparse(response.url)
        if actual.scheme != "https" or actual.hostname not in _HOSTS or actual.path != parsed.path or actual.query:
            return {"success": False, "error": "product_identity_unknown"}
        response.encoding = response.apparent_encoding or response.encoding
        html = response.text
        rows = [row for row in parse_product_html(html, page_url=source_url)
                if (urlparse(row["source_url"]).hostname in _HOSTS
                    and urlparse(row["source_url"]).path == parsed.path)]
        if len(rows) > 1:
            return {"success": False, "error": "product_identity_unknown"}
        metadata = _DetailMetadata()
        metadata.feed(html)
        if rows:
            row = rows[0]
        else:
            row = metadata.row(product_id, source_url)
            if row is None:
                return {"success": False, "error": "product_identity_unknown"}
        if image := row.get("image_url") or metadata.product_image(source_url):
            row["image_url"] = image
        features = _ProductFeatures()
        features.feed(html)
        # Keep both values when independent parts of the page disagree.
        specs = dict(row.get("characteristics") or {})
        for label, value in features.features.items():
            key = label if label not in specs or specs[label] == value else label + " (detail table)"
            specs[key] = value
        short_specs = _ExactShortSpecs(product_id)
        short_specs.feed(html)
        specs.update(short_specs.specs())
        row.update(product_id=product_id, source_url=source_url, characteristics=specs)
        return {"success": True, "data": row}
    except requests.Timeout:
        return {"success": False, "error": "source_timeout"}
    except requests.RequestException:
        return {"success": False, "error": "source_unavailable"}
    except (AttributeError, TypeError, ValueError):
        return {"success": False, "error": "invalid_product_evidence"}
