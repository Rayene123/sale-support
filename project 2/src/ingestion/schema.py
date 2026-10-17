"""Corpus record schema and validation.

One published article is one record. The schema keeps every field agreed in
``docs/PERSON_1_CORPUS.md`` (``document_id``, ``title``, ``language``,
``book``, ``section``, ``article``, ``article_number``, ``source_url``,
``source_date``, ``text``) and adds the structure and provenance the retrieval
and citation layers need:

* an explicit ``heading_path`` so a chunk can never lose its legal hierarchy,
* parsed ``amendment_notes``/``amendment_laws`` so an answer can say *which*
  amendment it is reading,
* ``pdf_page``/``printed_page`` so a human can check any record against the
  published PDF.

Records are validated before writing. A validation error stops the build rather
than producing a corpus that quietly lost an article.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

# Article suffixes used by Tunisian legal drafting, in the order they take when
# sorting (231, 231 bis, 231 ter, ...).
ARTICLE_SUFFIXES: tuple[str, ...] = (
    "bis",
    "ter",
    "quater",
    "quinquies",
    "sexies",
    "septies",
    "octies",
    "nonies",
    "decies",
)

SUFFIX_ORDER = {suffix: i for i, suffix in enumerate(ARTICLE_SUFFIXES, start=1)}

HEADING_FIELDS: tuple[str, ...] = ("book", "titre", "chapitre", "section", "sous_section")

RECORD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:article-[0-9]+(?:-[a-z]+)?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Records shorter than this are almost always a parser mistake (a heading
# swallowed as body text, or an empty article left behind by a page break).
MIN_TEXT_CHARS = 10
SHORT_TEXT_CHARS = 40


VALID_STATUSES = ("published", "repealed")


@dataclass
class ArticleRecord:
    """One article of one document."""

    record_id: str
    document_id: str
    title: str
    language: str

    # Legal hierarchy. Values are labels such as "Livre III — De la lettre de
    # change, du billet à ordre et du chèque"; None when the document has no
    # such level at that point.
    book: str | None
    titre: str | None
    chapitre: str | None
    section: str | None
    sous_section: str | None
    heading_path: list[str] = field(default_factory=list)

    article: str = ""
    article_number: int = 0
    article_suffix: str | None = None

    # "repealed" when the edition itself prints a repeal note instead of text.
    # Such a record may legitimately have empty text, and it is evidence of
    # repeal rather than article content.
    status: str = "published"

    # "Modifié par la loi n° 96-28 du 3 avril 1996" -> keep the sentence and the
    # law references separately: the sentence for display, the references for
    # filtering and for cross-checking against the JORT.
    amendment_notes: list[str] = field(default_factory=list)
    amendment_laws: list[str] = field(default_factory=list)

    text: str = ""
    char_count: int = 0

    source_url: str = ""
    source_sha256: str = ""
    source_date: str = ""
    source_edition: str = ""
    pdf_page: int = 0
    printed_page: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @property
    def sort_key(self) -> tuple:
        return (
            self.document_id,
            self.article_number,
            SUFFIX_ORDER.get(self.article_suffix or "", 0),
        )


def validate_record(record: ArticleRecord) -> list[str]:
    """Return a list of human-readable problems. Empty list means valid."""
    problems: list[str] = []

    if not RECORD_ID_RE.match(record.record_id):
        problems.append(f"record_id does not match the stable-id pattern: {record.record_id!r}")
    if not record.document_id:
        problems.append("document_id is empty")
    if not record.title:
        problems.append("title is empty")
    if not record.language:
        problems.append("language is empty")

    if record.heading_path:
        if any(not isinstance(part, str) or not part.strip() for part in record.heading_path):
            problems.append("heading_path contains an empty part")
        expected = [
            value
            for value in (
                record.book,
                record.titre,
                record.chapitre,
                record.section,
                record.sous_section,
            )
            if value
        ]
        if expected != record.heading_path:
            problems.append(
                f"heading_path {record.heading_path!r} does not match the heading fields {expected!r}"
            )

    if record.article_number < 1:
        problems.append(f"article_number must be >= 1, got {record.article_number}")
    if record.article_suffix and record.article_suffix not in ARTICLE_SUFFIXES:
        problems.append(f"unknown article_suffix: {record.article_suffix!r}")
    if not record.article:
        problems.append("article label is empty")
    if record.status not in VALID_STATUSES:
        problems.append(f"unknown status: {record.status!r}")

    body = record.text.strip()
    if record.status == "repealed":
        # The edition prints a repeal note instead of article text.
        if body:
            problems.append("a repealed article must not carry article text")
    elif len(body) < MIN_TEXT_CHARS:
        problems.append(
            f"text is shorter than {MIN_TEXT_CHARS} characters ({len(body)}): {body[:60]!r}"
        )
    if record.char_count != len(record.text):
        problems.append("char_count does not match len(text)")

    if not record.source_url.startswith("http"):
        problems.append(f"source_url is not an http(s) URL: {record.source_url!r}")
    if not SHA256_RE.match(record.source_sha256):
        problems.append("source_sha256 is not a 64-character lowercase hex digest")
    if not record.source_date:
        problems.append("source_date is empty")
    if record.pdf_page < 1:
        problems.append(f"pdf_page must be >= 1, got {record.pdf_page}")
    if record.printed_page is not None and record.printed_page < 1:
        problems.append(f"printed_page must be >= 1 when set, got {record.printed_page}")

    for note in record.amendment_notes:
        if not note.strip():
            problems.append("amendment_notes contains an empty entry")
    for law in record.amendment_laws:
        if not re.match(r"^[0-9]{2,4}-[0-9]{1,4}$", law):
            problems.append(f"amendment_laws entry is not a law number: {law!r}")

    return problems
