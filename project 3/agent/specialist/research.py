"""Researcher role: bounded retailer search, exact-page inspection, and evidence."""
from dataclasses import dataclass
import re
from typing import Callable

from pydantic import ValidationError

from agent.tools.mytek import inspect_tunisianet_product, search_specialist_catalog, search_tunisianet_products
from .contracts import Listing, Role

PRODUCT_TYPES = {
    "laptop": r"pc portable|ordinateur portable|laptop|notebook|ultrabook",
    "monitor": r"[eé]cran(?: pc)?|moniteur|monitor",
}


def matches_role(listing: Listing, role: Role) -> bool:
    name = listing.name.casefold()
    return bool(re.search(rf"\b(?:{PRODUCT_TYPES[role]})\b", name)
                and not re.search(r"\b(?:pour|for)\s+(?:un |a |le |the )?(?:pc|laptop|écran|monitor)|^(?:support|câble|cable|adaptateur|adapter|sac|dock|housse)\b", name))


SEARCH = {
    "laptop": ("pc portable", "ordinateur portable"),
    "monitor": ("écran pc", "moniteur"),
}


@dataclass(frozen=True)
class Researcher:
    search: Callable
    inspect: Callable
    general_search: Callable | None = None

    @classmethod
    def tunisianet(cls):
        return cls(search_specialist_catalog, inspect_tunisianet_product, search_tunisianet_products)

    def candidates(self, role: Role, attempt: int, call: Callable) -> list[Listing]:
        query = SEARCH[role][attempt]
        response = call("researcher", "search_catalog", {"role": role, "query": query},
                        lambda: self.search(query, max_results=6))
        if response.get("success") is not True:
            return []
        data = response.get("data")
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            return []
        candidates = {}
        for record in products[:6]:
            listing = normalize_listing(record)
            if listing is not None and matches_role(listing, role):
                candidates.setdefault(listing.product_id, listing)
        return sorted(candidates.values(), key=lambda item: (item.price_tnd is None, item.price_tnd or 0))

    def queries_for(self, line):
        # A category page is a useful second pass when the model's search phrase
        # is narrow. Exact-model requests keep their model-specific searches.
        if self.general_search and not line.exact_model and line.kind in SEARCH:
            first = line.queries[0]
            return (first, next(query for query in SEARCH[line.kind] if query != first))
        return line.queries

    def search_line(self, line, query, call):
        from .setup_research import matches_line
        search = self.general_search or self.search
        if query in {name for options in SEARCH.values() for name in options}:
            search = self.search
        response = call("researcher", "search_catalog", {"line": line.id},
                        lambda: search(query, max_results=6))
        data = response.get("data") if response.get("success") is True else None
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            return []
        found = {}
        for row in products[:6]:
            listing = normalize_listing(row)
            if listing is not None and matches_line(listing, line):
                found.setdefault(listing.product_id, listing)
        return sorted(found.values(), key=lambda row: (row.price_tnd is None, row.price_tnd or 0))

    def detail(self, listing: Listing, call: Callable) -> Listing | None:
        response = call("researcher", "inspect_listing", {"product_id": listing.product_id},
                        lambda: self.inspect(listing.product_id, listing.source_url))
        if response.get("success") is not True:
            return None
        result = normalize_listing(response.get("data"))
        if result and (result.product_id, result.source_url) == (listing.product_id, listing.source_url):
            return result
        return None


def normalize_listing(data) -> Listing | None:
    if not isinstance(data, dict):
        return None
    try:
        specs = data.get("characteristics") or {}
        if not isinstance(specs, dict):
            return None
        return Listing(product_id=data.get("product_id"), name=data.get("name"),
                       source_url=data.get("source_url"), fetched_at=data.get("retrieved_at"),
                       price_tnd=data.get("price_tnd"), availability=data.get("availability", "unknown"),
                       specs={str(k)[:100]: str(v)[:240] for k, v in list(specs.items())[:80]})
    except (ValidationError, ValueError):
        return None
