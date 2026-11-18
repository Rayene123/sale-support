"""Researcher role: bounded retailer search, exact-page inspection, and evidence."""
from dataclasses import dataclass
import re
from typing import Callable

from pydantic import ValidationError

from specialist.catalog.tunisianet import inspect_tunisianet_product, search_specialist_catalog, search_tunisianet_products
from specialist.contracts.purchasing import Listing, Role
from specialist.contracts.setup import KIND_NAMES
from specialist.contracts.text import COLORS, COLOR_FIELDS, RAM_FIELDS, color_family, fold_text

PRODUCT_TYPES = {
    "laptop": r"pc portable|ordinateur portable|laptop|notebook|ultrabook",
    "monitor": r"[eé]cran(?: pc)?|moniteur|monitor",
}


def matches_role(listing: Listing, role: Role) -> bool:
    name = listing.name.casefold()
    return bool(re.search(rf"\b(?:{PRODUCT_TYPES[role]})\b", name)
                and not re.search(r"\b(?:pour|for)\s+(?:un |a |le |the )?(?:pc|laptop|écran|monitor)|^(?:support|câble|cable|adaptateur|adapter|sac|dock|housse)\b", name))


_ACCESSORY = re.compile(r"^(?:support|c[aâ]ble|adaptateur|adapter|chargeur|charger|housse|sac)\b", re.I)


def matches_line(listing, line):
    kind = "[-\\s]+".join(re.escape(word) for word in re.split(r"[_-]+", line.kind))
    subject = KIND_NAMES.get(line.kind, kind)
    if not re.search(rf"\b(?:{subject})\b", fold_text(listing.name)):
        return False
    if line.kind in KIND_NAMES and _ACCESSORY.match(listing.name):
        return False
    if line.exact_model:
        expected = re.findall(r"[a-z0-9]+", line.exact_model.lower())
        actual = re.findall(r"[a-z0-9]+", (listing.name + " " + " ".join(
            value for key, value in listing.specs.items()
            if key.casefold() in {"mpn", "sku", "reference", "model", "modèle"}
        )).lower())
        if not expected or not any(actual[i:i+len(expected)] == expected for i in range(len(actual))):
            return False
    return True


SEARCH = {
    "laptop": ("pc portable", "ordinateur portable"),
    "monitor": ("écran pc", "moniteur"),
}


def _search_specs(line):
    color = None
    ram = None
    for spec in line.specs:
        field = fold_text(spec.field).replace("_", " ").strip()
        if field in COLOR_FIELDS:
            color = color_family(spec.value)
        if line.kind in {"laptop", "desktop"} and field in RAM_FIELDS:
            size = re.fullmatch(r"(\d+)\s*(?:gb|go)", fold_text(spec.value).strip())
            if size:
                ram = (int(size[1]), spec.comparison)
    return color, ram


def _title_score(listing, color, ram):
    # Titles only prioritize which pages to read. The verifier uses exact-page specs.
    title = fold_text(listing.name)
    score = 0
    if color:
        pattern = "|".join(re.escape(alias) for alias in (color, *COLORS[color]))
        score += bool(re.search(rf"\b(?:{pattern})\b", title))
    if ram:
        size, comparison = ram
        capacities = {int(n) for n in re.findall(r"/\s*(\d+)\s*(?:gb|go)\b(?=\s*(?:ddr\d|/|$))", title)}
        score += size in capacities if comparison == "equals" else any(n >= size for n in capacities)
    return score


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
        return _listings(response, lambda listing: matches_role(listing, role))

    def queries_for(self, line):
        # A category page is a useful second pass when the model's search phrase
        # is narrow. Exact-model requests keep their model-specific searches.
        if self.general_search and not line.exact_model and line.kind in SEARCH:
            first = line.queries[0]
            return (first, next(query for query in SEARCH[line.kind] if query != first))
        return line.queries

    def broader_queries(self, line):
        queries = self.queries_for(line)
        if self.general_search and not line.exact_model:
            general = SEARCH.get(line.kind, (line.kind.replace("_", " "),))
            color, ram = _search_specs(line)
            attributes = [f"{ram[0]} Go" if ram else "", COLORS[color][0] if color else ""]
            focused = (" ".join(part for part in (general[0], *attributes) if part),) if color or ram else ()
            return tuple(dict.fromkeys((*focused, *line.queries, *queries, *general)))[:3]
        return queries

    def search_line(self, line, query, call, *, shopper=False, budget=None):
        search = self.general_search or self.search
        category = query in {name for options in SEARCH.values() for name in options}
        if category:
            search = self.search
        color, ram = _search_specs(line) if shopper else (None, None)
        limit = 12 if (color or ram) and self.general_search and not category else 6
        response = call("researcher", "search_catalog", {"line": line.id},
                        lambda: search(query, max_results=limit))
        rows = _listings(response, lambda listing: matches_line(listing, line), limit=limit)
        if color or ram:
            rows.sort(key=lambda item: (
                not line.owned and item.availability != "in_stock",
                not line.owned and budget is not None and (
                    item.price_tnd is None or item.price_tnd * line.quantity > budget),
                -_title_score(item, color, ram),
            ))
        return rows

    def inspect_candidates(self, listings, matches, seen, limit, call):
        unseen = [listing for listing in listings if listing.product_id not in seen]
        for seed in unseen[:limit]:
            seen.add(seed.product_id)
            listing = self.detail(seed, call)
            if listing is not None and matches(listing):
                yield listing

    def detail(self, listing: Listing, call: Callable) -> Listing | None:
        return self.exact_listing(listing.product_id, listing.source_url, call)

    def exact_listing(self, product_id, source_url, call):
        response = call("researcher", "inspect_listing", {"product_id": product_id},
                        lambda: self.inspect(product_id, source_url))
        if response.get("success") is not True:
            return None
        result = normalize_listing(response.get("data"))
        if result and (result.product_id, result.source_url) == (product_id, source_url):
            return result
        return None


def _listings(response, matches, *, limit=6):
    data = response.get("data") if response.get("success") is True else None
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        return []
    found = {}
    for record in products[:limit]:
        listing = normalize_listing(record)
        if listing is not None and matches(listing):
            found.setdefault(listing.product_id, listing)
    return sorted(found.values(), key=lambda item: (item.price_tnd is None, item.price_tnd or 0))


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
                       image_url=data.get("image_url"),
                       specs={str(k)[:100]: str(v)[:240] for k, v in list(specs.items())[:80]})
    except (ValidationError, ValueError):
        return None
