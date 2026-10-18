"""Turn cleaned PDF lines into article records.

Three structural facts about this publication drive the parser, and each is
asserted rather than assumed:

1. The file is one document but three regions: the promulgating law (Loi n°
   59-129, articles 1-5), the code itself, and the table of contents. The law's
   articles would collide with the code's articles if the regions were merged.
2. The code's structure is ``LIVRE > TITRE > CHAPITRE > Section >
   Sous-section``. Headings print in upper case and their titles wrap onto the
   following line(s).
3. An article starts with ``Article <n> [suffix] [(amendment note)]``. The
   amendment note may wrap onto the next line, and the 2024 edition prints the
   article body on the same line after a ``.-`` separator
   (``Article premier.- Le présent code ...``). The parser handles both the
   header-only (2014) and inline-body (2024) forms.

If a marker is missing the parser raises instead of guessing, because a
silently mis-split document is worse than a failed build.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .pdf_text import Page, normalize_body
from .schema import ARTICLE_SUFFIXES, ArticleRecord
from .sources import DocumentSpec, Source

# ---------------------------------------------------------------------------
# Structure vocabulary
# ---------------------------------------------------------------------------

_ROMAN_ALTERNATIVES = (
    "XIV|XIII|XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I"
)
# Word numerals are printed masculine ("premier") and feminine ("première") and
# abbreviated ("1er", "1re", "1ère").
_WORD_NUMERAL = r"PREMI(?:ER|ERE|\u00c8RE)|1(?:ER|RE|ERE|\u00c8RE)"
_NUMERAL = rf"(?:{_WORD_NUMERAL}|{_ROMAN_ALTERNATIVES})"
# Sections and sub-sections are also numbered in Arabic in the 2024 edition
# ("Section 2", "Sous-section 2").
_SECTION_NUMERAL = rf"(?:{_WORD_NUMERAL}|{_ROMAN_ALTERNATIVES}|[0-9]{{1,2}})"

LIVRE_RE = re.compile(
    rf"^(?P<label>LIVRE\s+(?P<num>{_NUMERAL}))\b[\s:.\u2013\u2014-]*(?P<title>.*)$", re.I
)
TITRE_RE = re.compile(
    rf"^(?P<label>TITRE\s+(?P<num>{_NUMERAL}))\b[\s:.\u2013\u2014-]*(?P<title>.*)$", re.I
)
CHAPITRE_RE = re.compile(
    rf"^(?P<label>CHAPITRE\s+(?P<num>{_NUMERAL}))\b[\s:.\u2013\u2014-]*(?P<title>.*)$", re.I
)
SECTION_RE = re.compile(
    rf"^(?P<label>SECTION\s+(?P<num>{_SECTION_NUMERAL}))\b[\s:.\u2013\u2014-]*(?P<title>.*)$",
    re.I,
)
SUBSECTION_RE = re.compile(
    rf"^(?P<label>SOUS-?\s?SECTION\s+(?P<num>{_SECTION_NUMERAL}))\b[\s:.\u2013\u2014-]*(?P<title>.*)$",
    re.I,
)

LEVEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("book", LIVRE_RE),
    ("titre", TITRE_RE),
    ("chapitre", CHAPITRE_RE),
    ("sous_section", SUBSECTION_RE),  # must be tested before "section"
    ("section", SECTION_RE),
)
LEVEL_ORDER = ("book", "titre", "chapitre", "section", "sous_section")
LEVEL_TITLES = {
    "book": "Livre",
    "titre": "Titre",
    "chapitre": "Chapitre",
    "section": "Section",
    "sous_section": "Sous-section",
}

ARTICLE_RE = re.compile(
    r"^Article\s+(?P<num>premier|1er|[0-9]{1,4})\s*"
    r"(?P<suffix>" + "|".join(ARTICLE_SUFFIXES) + r")?"
    r"(?P<tail>.*)$",
    re.I,
)

# Both editions separate the article header (and any amendment note) from the
# body with a period, optionally followed by a hyphen: ``Article premier.-``.
# The 2014 edition sometimes wrote ``Article 372. (note)`` where the period
# precedes the note, so the separator is stripped before looking for a note.
HEADER_SEPARATOR_RE = re.compile(r"^[.\u2013\u2014-]+\s*")

LAW_START_RE = re.compile(r"^Loi\s+n\s*[°ºo]?\s*59-129\b", re.I)
TOC_START_RE = re.compile(r"^TABLE\s+DES\s+MATI", re.I)
CODE_TITLE_RE = re.compile(r"^CODE\s+DE\s+COMMERCE\s*(?:\(\s*\d{1,2}\s*\))?\s*$", re.I)

LOI_REF_RE = re.compile(
    r"loi\s+n\s*[°ºo]?\s*([0-9]{2,4})\s*-\s*([0-9]{1,4})", re.I
)
REPEAL_RE = re.compile(r"\babrog", re.I)
FOOTNOTE_MARKER_RE = re.compile(r"\(\s*\d{1,2}\s*\)")
TRAILING_JUNK_RE = re.compile(r"[\s:.\u2013\u2014-]+$")
MAX_TITLE_CONTINUATIONS = 3
MAX_NOTE_CONTINUATIONS = 5

NUMERAL_WORDS = {
    "premier": "I",
    "1er": "I",
    "premiere": "I",
    "premi\u00e8re": "I",
    "1re": "I",
    "1ere": "I",
    "1\u00e8re": "I",
}


class StructureError(RuntimeError):
    """Raised when the document does not have the expected structure."""


@dataclass(frozen=True)
class Line:
    """One line of cleaned source text with its PDF page number (1-based)."""

    pdf_page: int
    text: str


@dataclass(frozen=True)
class Regions:
    law_start: int | None
    code_start: int
    toc_start: int
    total_lines: int

    def bounds(self, name: str) -> tuple[int, int]:
        if name == "law":
            if self.law_start is None:
                raise StructureError("the promulgating law was not found in the source")
            return self.law_start, self.code_start
        if name == "code":
            return self.code_start, self.toc_start
        if name == "toc":
            return self.toc_start, self.total_lines
        raise StructureError(f"unknown region: {name!r}")


def build_stream(pages: list[Page]) -> list[Line]:
    """Flatten cleaned pages into a line stream that keeps page numbers."""
    stream: list[Line] = []
    for page in pages:
        for text in page.body_lines:
            stream.append(Line(pdf_page=page.printed_page, text=text))
    return stream


def detect_regions(stream: list[Line]) -> Regions:
    """Locate the law, code and table-of-contents regions."""
    law_start = None
    livre_start = None
    toc_start = None

    for index, line in enumerate(stream):
        text = line.text.strip()
        if not text:
            continue
        if law_start is None and LAW_START_RE.match(text):
            law_start = index
            continue
        if toc_start is None and TOC_START_RE.match(text):
            toc_start = index
            break
        # The code body starts at the first real LIVRE heading. Table-of-contents
        # lines are eliminated by the TOC break above; the cover title does not
        # match this pattern.
        if livre_start is None and LIVRE_RE.match(text):
            livre_start = index

    if toc_start is None:
        raise StructureError("'TABLE DES MATIERES' was not found; region layout changed")
    if livre_start is None:
        raise StructureError("no LIVRE heading was found; region layout changed")
    if law_start is not None and law_start >= livre_start:
        raise StructureError("the promulgating law was found after the code body starts")

    # The code document starts at its printed title ("CODE DE COMMERCE"), which
    # sits just above the first book heading. Taking the last such line before
    # the body keeps the cover's identical title out of the code region and the
    # code title out of the law region.
    code_start = livre_start
    for index in range(law_start or 0, livre_start):
        if CODE_TITLE_RE.match(stream[index].text.strip()):
            code_start = index

    if code_start >= toc_start:
        raise StructureError("the code region is empty; region layout changed")

    return Regions(
        law_start=law_start,
        code_start=code_start,
        toc_start=toc_start,
        total_lines=len(stream),
    )


def normalize_numeral(numeral: str) -> str:
    """``PREMIER``/``1er`` -> ``I``; roman numerals keep the source's letters."""
    lowered = numeral.strip().lower()
    if lowered in NUMERAL_WORDS:
        return NUMERAL_WORDS[lowered]
    return numeral.strip().upper()


def clean_heading_title(title: str) -> str:
    """Drop footnote markers and dangling punctuation from a heading title."""
    text = FOOTNOTE_MARKER_RE.sub(" ", title)
    text = re.sub(r"\s+", " ", text).strip()
    return TRAILING_JUNK_RE.sub("", text).strip()


def heading_label(level: str, numeral: str, title: str) -> str:
    label = f"{LEVEL_TITLES[level]} {normalize_numeral(numeral)}"
    return f"{label} — {title}" if title else label


def is_title_like(text: str) -> bool:
    """Heuristic for a chapter title that sits entirely on its own line.

    Chapter titles are set in sentence case, unlike the upper-case book and
    title headings, so case alone cannot identify them. They are short and are
    not terminated like a sentence.
    """
    if len(text) > 140 or len(text.split()) > 18:
        return False
    return not text.endswith((".", ":", ";"))


def is_continuation_candidate(level: str, text: str, title_so_far: str = "") -> bool:
    """Can ``text`` be the wrapped remainder (or body) of a heading title?"""
    candidate = text.strip()
    if not candidate:
        return False
    if match_heading(candidate) or ARTICLE_RE.match(candidate):
        return False
    first = candidate[0]
    # Parenthetical notices, bullets and new enumerations are not titles.
    if first in "(-\u2013\u2014" or first.isdigit():
        return False
    # Lettered sub-items ("A. - Du contrat ...") are a level this parser does not
    # model; they are not the wrapped title of the heading above them.
    if re.match(r"^[A-Za-z]\s*[.)]\s", candidate):
        return False
    if level in ("book", "titre"):
        # The older books print their titles in upper case; the 2024 edition's
        # new Livre IV prints some in sentence case. Upper-case lines always
        # continue, and a sentence-case line continues only while the title has
        # not started yet (its first line) or when it wraps in lower case -- a
        # capitalised sentence after a title has started is body text, such as
        # the repeal notice printed after "TITRE III / DES SOCIETES".
        if uppercase_ratio(candidate) >= 0.8:
            return True
        if not is_title_like(candidate):
            return False
        return first.islower() or not title_so_far.strip()
    # Chapters, sections and sub-sections are printed in sentence case, but the
    # first word can still be capitalised ("De la vente ...").
    return is_title_like(candidate)


def uppercase_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.isupper() for char in letters) / len(letters)


def match_heading(text: str) -> tuple[str, str, str] | None:
    """Return ``(level, numeral, title)`` when ``text`` is a heading line."""
    stripped = FOOTNOTE_MARKER_RE.sub(" ", text)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    # Headings are printed capitalised. This rejects body references that merely
    # begin with the same word, e.g. "sous-section première de la quatrième
    # section du présent chapitre, ...".
    if stripped[:1].islower():
        return None
    for level, pattern in LEVEL_PATTERNS:
        match = pattern.match(stripped)
        if match:
            return level, match.group("num"), match.group("title")
    return None


def tail_can_start_article(tail: str) -> bool:
    """Is ``tail`` (the text after ``Article <n>``) shaped like a header?

    A real header continues with nothing, with an amendment note ``(`` or with
    the separator before the body (``.`` / ``-``). A cross-reference such as
    ``Article 411 et suivants du présent code`` continues with prose, so it is
    not a header even though it matches :data:`ARTICLE_RE`.
    """
    stripped = tail.strip()
    if not stripped:
        return True
    return stripped[0] == "(" or stripped[0] in ".\u2013\u2014-"


def split_note_body(tail: str) -> tuple[str | None, str] | None:
    """Split a header tail into ``(amendment note, inline body)``.

    Returns ``None`` when the tail is not a valid header continuation (a
    cross-reference parading as an article start). When the note is not closed
    yet, the whole tail is returned as the note so the caller can join the
    following line(s) and call again.
    """
    rest = tail.strip()
    if rest and rest[0] not in "(\u2013\u2014-.":
        return None
    if not rest.startswith("("):
        rest = HEADER_SEPARATOR_RE.sub("", rest)

    note = None
    if rest.startswith("("):
        depth = 0
        end = None
        for position, char in enumerate(rest):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = position
                    break
        if end is None:
            return rest, ""  # note continues on the next line(s)
        note = rest[: end + 1]
        rest = rest[end + 1:].strip()
        if rest and rest[0] not in ".\u2013\u2014-":
            return None
        rest = HEADER_SEPARATOR_RE.sub("", rest)

    return note, rest.strip()


def parse_article_start(text: str) -> tuple[int, str | None, str, str] | None:
    """Return ``(number, suffix, label, tail)`` when ``text`` starts an article.

    ``tail`` is everything after ``Article <n> [suffix]`` and still carries the
    separator and any inline body, because the 2024 edition prints the body on
    the header line (``Article premier.- Le présent code ...``).
    """
    match = ARTICLE_RE.match(text.strip())
    if not match or not tail_can_start_article(match.group("tail")):
        return None
    raw_number = match.group("num").lower()
    number = 1 if raw_number in ("premier", "1er") else int(raw_number)
    suffix = match.group("suffix")
    suffix = suffix.lower() if suffix else None
    label = f"Article {match.group('num').strip()}"
    if suffix:
        label = f"{label} {suffix}"
    return number, suffix, label, match.group("tail")


def parse_article_header(text: str) -> tuple[int, str | None, str | None, str] | None:
    """Return ``(number, suffix, note, inline_body)`` for a one-line header.

    A note that wraps onto the next line is returned as an incomplete note with
    an empty body; :func:`parse_region` joins the lines and re-splits.
    """
    start = parse_article_start(text)
    if start is None:
        return None
    number, suffix, _label, tail = start
    split = split_note_body(tail)
    if split is None:
        return None
    note, body = split
    return number, suffix, note, body


def extract_law_references(note: str) -> list[str]:
    """Pull ``loi n° 96-28``-style references out of an amendment note.

    The edition is inconsistent about spacing ("n° 2000 - 61"), so references
    are normalised before they are stored.
    """
    return sorted({f"{year}-{number}" for year, number in LOI_REF_RE.findall(note)})


def note_is_complete(note: str) -> bool:
    """A note is complete once its parentheses balance.

    Testing for a trailing ")" is not enough: the edition writes
    "(Abrogé par la loi n° 95-35 du 17 avril 1995)." with a full stop after the
    closing bracket.
    """
    return note.count(")") >= note.count("(")


def record_id_for(document_id: str, number: int, suffix: str | None) -> str:
    base = f"{document_id}:article-{number}"
    if suffix:
        return f"{base}-{suffix.lower()}"
    return base


def status_from_note(note: str | None) -> str:
    """The edition prints a repeal note instead of text for repealed articles."""
    if note and REPEAL_RE.search(note):
        return "repealed"
    return "published"


@dataclass
class ParseResult:
    records: list[ArticleRecord]
    front_matter: str
    unattached: str
    warnings: list[str]


def parse_region(
    stream: list[Line],
    bounds: tuple[int, int],
    spec: DocumentSpec,
    source: Source,
) -> ParseResult:
    """Parse one region of the stream into article records."""
    start, end = bounds
    lines = stream[start:end]
    warnings: list[str] = []
    records: list[ArticleRecord] = []

    headings: dict[str, str | None] = {level: None for level in LEVEL_ORDER}
    front_matter_lines: list[str] = []
    unattached_lines: list[str] = []
    seen_article = False

    open_article: dict | None = None
    index = 0

    def finalize() -> None:
        nonlocal open_article
        if open_article is None:
            return
        body = normalize_body("\n".join(open_article["body"]))
        number = open_article["number"]
        suffix = open_article["suffix"]
        note = open_article["note"]
        record = ArticleRecord(
            record_id=record_id_for(spec.document_id, number, suffix),
            document_id=spec.document_id,
            title=spec.title,
            language=spec.language,
            book=headings["book"],
            titre=headings["titre"],
            chapitre=headings["chapitre"],
            section=headings["section"],
            sous_section=headings["sous_section"],
            heading_path=[headings[level] for level in LEVEL_ORDER if headings[level]],
            article=open_article["label"],
            article_number=number,
            article_suffix=suffix,
            status=status_from_note(note),
            amendment_notes=[note] if note else [],
            amendment_laws=extract_law_references(note) if note else [],
            text=body,
            char_count=len(body),
            source_url=source.url,
            source_sha256=source.sha256,
            source_date=source.edition_date,
            source_edition=source.edition,
            pdf_page=open_article["pdf_page"],
            printed_page=open_article["pdf_page"],
        )
        records.append(record)
        open_article = None

    while index < len(lines):
        line = lines[index]
        text = line.text.strip()

        if not text:
            if open_article is not None:
                open_article["body"].append("")
            index += 1
            continue

        heading = match_heading(text)
        if heading is not None:
            finalize()
            level, numeral, title = heading
            consumed = index
            title = clean_heading_title(title)
            # Headings print their title on the following line(s).
            lookahead = index + 1
            continuations = 0
            while lookahead < len(lines) and continuations < MAX_TITLE_CONTINUATIONS:
                candidate = lines[lookahead].text.strip()
                lookahead += 1
                if not candidate:
                    continue
                if not is_continuation_candidate(level, candidate, title):
                    break
                part = clean_heading_title(candidate)
                if not part:
                    continue
                title = f"{title} {part}".strip() if title else part
                consumed = lookahead - 1
                continuations += 1
            index = consumed + 1

            headings[level] = heading_label(level, numeral, title)
            for deeper in LEVEL_ORDER[LEVEL_ORDER.index(level) + 1:]:
                headings[deeper] = None
            continue

        start = parse_article_start(text)
        if start is not None:
            number, suffix, label, tail = start
            # The header line carries the body in the 2024 edition and may carry
            # a note that wraps onto the next line; join until the note closes.
            combined = tail
            consumed = index
            note, inline_body = split_note_body(combined) or (None, "")
            while (
                note is not None
                and not note_is_complete(note)
                and consumed < len(lines) - 1
            ):
                if consumed - index >= MAX_NOTE_CONTINUATIONS:
                    warnings.append(
                        f"article {number} on page {line.pdf_page}: amendment note "
                        "did not close; keeping what was read"
                    )
                    break
                consumed += 1
                combined = f"{combined} {lines[consumed].text.strip()}".strip()
                note, inline_body = split_note_body(combined) or (note, "")
            finalize()
            seen_article = True
            open_article = {
                "number": number,
                "suffix": suffix,
                "label": re.sub(r"\s+", " ", label).strip(),
                "note": re.sub(r"\s+", " ", (note or "")).strip() or None,
                "body": [inline_body] if inline_body else [],
                "pdf_page": line.pdf_page,
            }
            index = consumed + 1
            continue

        if open_article is not None:
            open_article["body"].append(text)
        elif seen_article:
            # Printed between articles: repeal notices for whole titles and
            # similar editorial blocks. Kept, but never attached to an article.
            unattached_lines.append(text)
        else:
            front_matter_lines.append(text)
        index += 1

    finalize()

    return ParseResult(
        records=records,
        front_matter=normalize_body("\n".join(front_matter_lines)),
        unattached=normalize_body("\n".join(unattached_lines)),
        warnings=warnings,
    )
