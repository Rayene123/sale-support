"""Stable result contract for Person 2 retrieval and Person 3 citations."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Literal

RetrievalMethod = Literal["bm25", "vector", "hybrid", "reranked"]
RETRIEVAL_METHODS: tuple[str, ...] = ("bm25", "vector", "hybrid", "reranked")


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked chunk returned by a retrieval method.

    The article and source fields are deliberately carried with the result so
    later components can cite the result without reopening the corpus.
    """

    chunk_id: str
    record_id: str
    text: str
    score: float
    rank: int
    article_number: int
    article: str
    heading_path: tuple[str, ...]
    pdf_page: int
    source_url: str
    retrieval_method: RetrievalMethod

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("chunk_id must not be empty")
        if not self.record_id.strip():
            raise ValueError("record_id must not be empty")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        if not math.isfinite(self.score):
            raise ValueError("score must be finite")
        if self.rank < 1:
            raise ValueError("rank must be at least 1")
        if self.article_number < 1:
            raise ValueError("article_number must be at least 1")
        if not self.article.strip():
            raise ValueError("article must not be empty")
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("heading_path must not contain empty headings")
        if self.pdf_page < 1:
            raise ValueError("pdf_page must be at least 1")
        if not self.source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        if self.retrieval_method not in RETRIEVAL_METHODS:
            raise ValueError(
                f"retrieval_method must be one of {RETRIEVAL_METHODS}, "
                f"got {self.retrieval_method!r}"
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation of this result."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize this result with stable key ordering."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
