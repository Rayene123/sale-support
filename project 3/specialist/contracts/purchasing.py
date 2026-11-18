"""Typed purchasing requirements and evidence for the Specialist workflow."""
from __future__ import annotations

from decimal import Decimal
import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator

from specialist.contracts.validation import StrictSchema

Role = Literal["laptop", "monitor"]
Verdict = Literal["pass", "fail", "unknown"]
Transport = Literal["hdmi", "displayport", "usb_c_dp"]
Mode = Literal["fixed", "adaptive", "adaptive_verifier"]
Money = Decimal


class Requirements(StrictSchema):
    items: list[Role] = Field(default_factory=list, max_length=2)
    budget_tnd: Money | None = Field(default=None, gt=0, max_digits=9, decimal_places=2)
    ram_gb: int | None = Field(default=None, ge=1, le=256)
    storage_gb: int | None = Field(default=None, ge=1, le=8192)
    monitor_inches: Decimal | None = Field(default=None, ge=10, le=100)
    resolution: Literal["1920x1080", "2560x1440", "3840x2160"] | None = None
    hz: int | None = Field(default=None, ge=24, le=540)
    connection: Transport | None = None
    unanswered: list[str] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def distinct_items(cls, items):
        if len(items) != len(set(items)):
            raise ValueError("Each product role may only occur once")
        return items


class Listing(StrictSchema):
    product_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(max_length=2048)
    fetched_at: str
    price_tnd: Money | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    availability: Literal["in_stock", "available", "unknown", "out_of_stock"]
    specs: dict[str, str] = Field(default_factory=dict, max_length=80)

    @field_validator("source_url")
    @classmethod
    def product_source(cls, url):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"tunisianet.com.tn", "www.tunisianet.com.tn"}
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment
                or not parsed.path.endswith(".html")):
            raise ValueError("Expected an exact Tunisianet product page")
        return url


class Finding(StrictSchema):
    code: str
    verdict: Verdict
    reason: str
    evidence: list[dict[str, str]] = Field(default_factory=list)


def _text_number(value: str) -> Decimal:
    normalized = value.replace(" ", "").replace("\u202f", "").replace("\xa0", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", normalized):
        normalized = normalized.replace(",", "").replace(".", "")
    else:
        normalized = normalized.replace(",", ".")
    return Decimal(normalized)


def read_requirements(text: str, previous: Requirements | None = None) -> Requirements:
    """Extract supported constraints. A follow-up only changes what it states."""
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise ValueError("Enter a purchasing request of 1 to 600 characters")
    text = text.casefold()
    data = previous.model_dump() if previous else {}
    aliases = {"laptop": r"laptops?|notebooks?|pc portable|ordinateur portable", "monitor": r"monitors?|écrans?|moniteurs?"}
    items = list(data.get("items", []))
    for role, alias in aliases.items():
        if re.search(rf"\b(?:remove|drop|without|no|sans|enlève)\s+(?:the |a |le |un )?(?:{alias})\b", text):
            items = [item for item in items if item != role]
        elif re.search(rf"\b(?:{alias})\b", text) and role not in items:
            items.append(role)
    data["items"] = items

    number = r"(\d+(?:[ ,.\u202f\xa0]\d+)*)"
    budget = re.search(rf"(?:under|up to|budget(?:\s+(?:of|is|to))?|below|moins de|au plus|make (?:that|it))\s*(?:[:=]\s*)?{number}", text)
    foreign_budget = re.search(r"[$€£]|\b(?:usd|eur|gbp)\b", text)
    budget = budget or re.search(rf"{number}\s*(?:tnd|dt|dinars?)\b", text)
    if foreign_budget:
        data["budget_tnd"] = None
    elif budget:
        data["budget_tnd"] = _text_number(budget.group(1))
    elif previous and previous.budget_tnd is None and re.fullmatch(rf"\s*{number}\s*", text):
        data["budget_tnd"] = _text_number(text)

    for field, pattern in {
        "ram_gb": r"\b(\d+)\s*(?:gb|go)\s+ram\b",
        "monitor_inches": r"(\d+(?:[.,]\d+)?)\s*-?\s*(?:inch(?:es)?\b|pouces?\b|[″\"])",
        "hz": r"\b(\d+)\s*hz\b",
    }.items():
        if match := re.search(pattern, text):
            data[field] = _text_number(match.group(1))
    if match := re.search(r"\bram\s*(?:of\s*)?:?\s*(\d+)\s*(?:gb|go)\b", text):
        data["ram_gb"] = int(match.group(1))
    if storage := re.search(r"\b(\d+)\s*(gb|go|tb|to)\s+(?:ssd|storage|stockage)\b", text):
        data["storage_gb"] = int(storage.group(1)) * (1000 if storage.group(2) in {"tb", "to"} else 1)
    elif storage := re.search(r"\b(?:ssd|storage|stockage)\s*(?:of\s*)?:?\s*(\d+)\s*(gb|go|tb|to)\b", text):
        data["storage_gb"] = int(storage.group(1)) * (1000 if storage.group(2) in {"tb", "to"} else 1)
    if "laptop" not in items:
        data.update(ram_gb=None, storage_gb=None)
    if "monitor" not in items:
        data.update(monitor_inches=None, resolution=None, hz=None)
    if not re.search(r"\b(?:ssd|storage|stockage|ram)\b", text) and "laptop" in items:
        if match := re.search(r"\b(\d+)\s*(?:gb|go)\b", text):
            data["ram_gb"] = int(match.group(1))
    for pattern, resolution in [(r"3840\s*[x×]\s*2160|\b(?:4k|2160p)\b", "3840x2160"),
                                (r"2560\s*[x×]\s*1440|\b(?:qhd|1440p)\b", "2560x1440"),
                                (r"1920\s*[x×]\s*1080|\b(?:1080p|full hd)\b", "1920x1080")]:
        if re.search(pattern, text):
            data["resolution"] = resolution
            break
    if re.search(r"\b(?:via|over|with|using|en|par)\s+hdmi\b", text):
        data["connection"] = "hdmi"
    elif re.search(r"\b(?:via|over|with|using|en|par)\s+usb[ -]?c\b", text):
        data["connection"] = "usb_c_dp"
    elif re.search(r"\b(?:via|over|with|using|en|par)\s+displayport\b", text):
        data["connection"] = "displayport"

    unanswered = []
    if not items:
        unanswered.append("Are you looking for a laptop, a monitor, or both?")
    if data.get("budget_tnd") is None:
        unanswered.append("What is your total budget in TND?")
    if data.get("hz") is not None and data.get("resolution") is None:
        unanswered.append("At what resolution do you need that refresh rate?")
    unsupported = re.search(r"\b(?:thunderbolt|usb4|daisy.chain|hdr|gsync|g-sync|freesync|oled|touchscreen|rtx|core i[3579]|ryzen|battery life|printers?|scanners?|keyboards?|mice|webcams?|cameras?|projectors?|speakers?|docks?)\b", text)
    if "monitor" not in items and any(data.get(k) for k in ("hz", "resolution")):
        unanswered.append("Should I add a monitor? This workflow verifies resolution and refresh rate for external displays.")
    if re.search(r"\b(?:two|three|deux|trois|[2-9])\s+(?:laptops?|monitors?|moniteurs?)\b", text):
        unsupported = True
    if unsupported:
        unanswered.append("I cannot verify that extra requirement in this workflow. Can we limit the request to price, RAM, storage, display size, resolution, refresh rate, and direct video connection?")
    elif previous and len(previous.unanswered) and previous.unanswered[-1].startswith("I cannot verify") and not re.search(r"\b(?:ignore|drop|remove|skip|omit|fine without)\b", text):
        unanswered.append(previous.unanswered[-1])
    data["unanswered"] = unanswered
    return Requirements.model_validate(data)
