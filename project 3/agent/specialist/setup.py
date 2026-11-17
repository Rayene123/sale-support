"""Strict, provider-independent plan returned by the purchasing model."""
from decimal import Decimal
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agent.tools.schemas import StrictSchema


KIND_NAMES = {
    "laptop": r"pc portable|ordinateur portable|laptop|notebook|ultrabook",
    "monitor": r"[eé]cran|moniteur|monitor|display",
    "desktop": r"pc de bureau|ordinateur de bureau|desktop",
    "keyboard": r"clavier|keyboard",
    "mouse": r"souris|mouse",
    "router": r"routeur|router",
    "switch": r"switch|commutateur",
    "dock": r"dock|station d.accueil",
}


class Spec(StrictSchema):
    field: str = Field(min_length=1, max_length=45)
    value: str = Field(min_length=1, max_length=100)
    comparison: Literal["equals", "at_least"]


class Item(StrictSchema):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    quantity: int = Field(ge=1, le=10)
    owned: bool
    exact_model: str | None = Field(default=None, max_length=90)
    queries: list[str] = Field(min_length=1, max_length=2)
    specs: list[Spec] = Field(default_factory=list, max_length=8)

    @field_validator("kind")
    @classmethod
    def canonical_kind(cls, kind: str) -> str:
        name = re.sub(r"[_-]+", " ", kind)
        return next((key for key, aliases in KIND_NAMES.items()
                     if re.fullmatch(rf"(?:{aliases})(?:s)?", name)), kind)

    @model_validator(mode="after")
    def safe_queries(self):
        if any(not query.strip() or len(query) > 120 or "://" in query for query in self.queries):
            raise ValueError("Use short catalog search terms")
        return self


class LinkCheck(StrictSchema):
    source_field: str = Field(min_length=1, max_length=65)
    target_field: str = Field(min_length=1, max_length=65)
    comparison: Literal["equals", "at_least", "at_most"]


class Link(StrictSchema):
    source: str
    target: str
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    transport: str | None = Field(default=None, max_length=25)
    resolution: Literal["1920x1080", "2560x1440", "3840x2160"] | None = None
    refresh_hz: int | None = Field(default=None, ge=24, le=540)
    checks: list[LinkCheck] = Field(default_factory=list, max_length=6)


class SetupPlan(StrictSchema):
    budget_tnd: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    items: list[Item] = Field(default_factory=list, max_length=10)
    links: list[Link] = Field(default_factory=list, max_length=16)
    questions: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def valid_graph(self):
        ids = {item.id for item in self.items}
        if len(ids) != len(self.items):
            raise ValueError("Setup item IDs must be unique")
        relationships = set()
        for link in self.links:
            key = (link.source, link.target, link.kind)
            if link.source == link.target or link.source not in ids or link.target not in ids or key in relationships:
                raise ValueError("Each relationship needs two distinct, existing items")
            relationships.add(key)
        if any(not q.strip() or len(q) > 240 for q in self.questions):
            raise ValueError("Clarification questions must be concise")
        return self

    def missing(self) -> list[str]:
        questions = list(self.questions)
        if not self.items:
            questions.append("What should the setup include?")
        if self.budget_tnd is None:
            questions.append("What is your total budget in TND?")
        if any(item.owned and not item.exact_model for item in self.items):
            questions.append("What are the exact models of the items you already own?")
        if self.items and all(item.owned for item in self.items):
            questions.append("Which items should I find for you to buy?")
        if any(link.refresh_hz and not link.resolution for link in self.links):
            questions.append("At what resolution do you need that refresh rate?")
        if len(self.items) > 1:
            connected = {end for link in self.links for end in (link.source, link.target)}
            if connected != {item.id for item in self.items}:
                questions.append("Which items need to work together? Some are missing a verified relationship.")
        return questions
