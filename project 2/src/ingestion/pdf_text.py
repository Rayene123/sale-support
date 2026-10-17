"""PDF text extraction and text normalisation.

The source PDFs are published by the IORT and share a consistent layout, which
this module relies on and documents:

* every page starts with the running header
  ``Imprimerie Officielle de la République Tuinsienne`` (the published typo is
  preserved in the file), followed by the printed page number;
* the printed page number equals the PDF page index plus one, which is checked
  rather than assumed;
* footnotes sit at the bottom of a page under a row of underscores and start
  with ``(N)``;
* body text is hard-wrapped, so words split across line breaks
  (``com-`` / ``merce``) and paragraphs must be re-joined.

Anything this module cannot explain is returned to the caller for a warning;
nothing is silently discarded except the running header, the page number and
the footnote block, which are handled explicitly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

RUNNING_HEADER_RE = re.compile(
    r"^Imprimerie\s+Officielle\s+de\s+la\s+R[ée]publique\s+Tu\w+\s*$"
)
PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
FOOTNOTE_SEPARATOR_RE = re.compile(r"^_{5,}$")
FOOTNOTE_START_RE = re.compile(r"^\((\d{1,2})\)\s*(.*)$")

# A wrapped word: a letter, a hyphen, a line break, then a letter. Digits are
# deliberately excluded so "1-\n2" and page furniture are never joined.
WRAPPED_WORD_RE = re.compile(r"([^\W\d_])-\n([^\W\d_])")

# List items and enumerations that must keep their own line when re-flowing.
ITEM_START_RE = re.compile(r"^(?:\d{1,2}\)|\d{1,2}\s*[-–)]|[a-z]\)|[-–—•]\s|[IVX]{1,4}[.)]\s)")


class PdfTextError(RuntimeError):
    """Raised when a PDF cannot be read as text at all."""


@dataclass
class Footnote:
    label: str
    text: str
    pdf_page: int = 0


@dataclass
class Page:
    """One cleaned PDF page."""

    index: int  # 0-based position in the file
    printed_page: int  # index + 1; the number printed on the page
    printed_number_seen: int | None  # what the page actually printed, if anything
    body_lines: list[str] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return any(line.strip() for line in self.body_lines)


def collapse(text: str) -> str:
    """Normalise non-breaking space and runs of whitespace inside one line."""
    text = text.replace("\u00a0", " ").replace("\u202f", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_footnotes(lines: list[str]) -> tuple[list[str], list[Footnote]]:
    """Split a page into body lines and the numbered footnote block."""
    separator = None
    for position, line in enumerate(lines):
        if FOOTNOTE_SEPARATOR_RE.match(line.strip()):
            separator = position
            break
    if separator is None:
        return lines, []

    body = lines[:separator]
    footnotes: list[Footnote] = []
    for raw in lines[separator + 1:]:
        line = collapse(raw)
        if not line:
            continue
        match = FOOTNOTE_START_RE.match(line)
        if match:
            footnotes.append(Footnote(label=f"({match.group(1)})", text=match.group(2).strip()))
        elif footnotes:
            footnotes[-1].text = collapse(f"{footnotes[-1].text} {line}")
        else:
            footnotes.append(Footnote(label="", text=line))
    return body, footnotes


def clean_page_lines(raw_text: str) -> tuple[list[str], int | None, list[Footnote]]:
    """Strip page furniture from one page of extracted text.

    Returns ``(body_lines, printed_number_seen, footnotes)``.
    """
    text = raw_text.replace("\x0c", "\n").replace("\ufeff", "")
    lines = [line.rstrip() for line in text.split("\n")]
    lines = [line for line in lines if not RUNNING_HEADER_RE.match(line.strip())]

    printed_number = None
    for position, line in enumerate(lines[:3]):
        stripped = line.strip()
        if PAGE_NUMBER_RE.match(stripped):
            printed_number = int(stripped)
            del lines[position]
            break

    body, footnotes = split_footnotes(lines)
    return [line.strip() for line in body], printed_number, footnotes


def dehyphenate(text: str) -> str:
    """Re-join words that the printed layout split across a line break."""
    previous = None
    current = text
    # A single pass cannot fix "a-\nb-\nc"; repeat until stable.
    for _ in range(8):
        if current == previous:
            break
        previous = current
        current = WRAPPED_WORD_RE.sub(r"\1\2", current)
    return current


def reflow(text: str) -> str:
    """Turn hard-wrapped lines into paragraphs.

    Enumerated items (``1)``, ``-``, ``a)``, ``I.``) keep their own line; every
    other continuation is appended to the paragraph above it. Blank lines are
    preserved as paragraph separators.
    """
    paragraphs: list[str] = []
    for raw in text.split("\n"):
        line = collapse(raw)
        if not line:
            paragraphs.append("")
            continue
        if not paragraphs or paragraphs[-1] == "" or ITEM_START_RE.match(line):
            paragraphs.append(line)
        else:
            paragraphs[-1] = f"{paragraphs[-1]} {line}"

    joined = "\n".join(paragraphs).strip()
    return re.sub(r"\n{3,}", "\n\n", joined)


def normalize_body(text: str) -> str:
    """Full body-text normalisation used for every article."""
    return reflow(dehyphenate(text))


def extract_pages(pdf_path: Path | str) -> list[Page]:
    """Read every page of ``pdf_path``, cleaned but not yet re-flowed."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise PdfTextError(
            "pypdf is required to read the source PDFs; "
            "install it with 'python -m pip install -r \"project 2/requirements.txt\"'"
        ) from exc

    path = Path(pdf_path)
    if not path.is_file():
        raise PdfTextError(f"source PDF not found: {path}")

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        # The IORT files carry permissions-only encryption with an empty user
        # password: they open for anyone but pypdf must be told so explicitly.
        if not reader.decrypt(""):
            raise PdfTextError(
                f"source PDF is encrypted with a password: {path}. "
                "Only empty-password (permissions-only) files are supported."
            )

    pages: list[Page] = []
    for index, pdf_page in enumerate(reader.pages):
        try:
            raw = pdf_page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - depends on the PDF
            raise PdfTextError(f"failed to extract text from page {index + 1}: {exc}") from exc

        body_lines, printed_number, footnotes = clean_page_lines(raw)
        page = Page(
            index=index,
            printed_page=index + 1,
            printed_number_seen=printed_number,
            body_lines=body_lines,
            footnotes=footnotes,
        )
        for note in page.footnotes:
            note.pdf_page = index + 1
        pages.append(page)

    if not any(page.has_text for page in pages):
        raise PdfTextError(
            f"no extractable text in {path}; the PDF is probably a scan and would need OCR"
        )
    return pages
