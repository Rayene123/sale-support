"""Build the Project 2 corpus from the verified source PDFs.

The build is deterministic and refuses to guess:

* every source is hash-verified before it is read,
* every region of the publication must be located or the build fails,
* every record is validated before it is written,
* every article number the table of contents promises is accounted for -- it is
  either in the corpus or inside a range the table marks ``(abrogés)``.
  Anything else is reported as a warning.

The build writes no timestamps, so two runs from the same PDF produce
byte-identical output.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .download import ensure_sources
from .pdf_text import Footnote, extract_pages
from .schema import SHORT_TEXT_CHARS, ArticleRecord, validate_record
from .sources import (
    DOCUMENTS,
    PENDING_TEXTS,
    REJECTED_SOURCES,
    SOURCES,
    DocumentSpec,
    source_by_id,
)
from .structure import (
    Line,
    ParseResult,
    StructureError,
    build_stream,
    detect_regions,
    parse_region,
)

CORPUS_VERSION = "1.0.0"

# Ranges as printed in the table of contents: "14 à 188", "191 et 192",
# "189 bis à 240".
TOC_RANGE_RE = re.compile(
    r"(\d{1,4})\s*(?:bis|ter|quater)?\s*(?:à|et)\s*(\d{1,4})\s*(?:bis|ter|quater)?"
)
ABROGATED_RE = re.compile(r"abrog", re.I)

KNOWN_LIMITATIONS: tuple[str, ...] = (
    "Version horizon: the source consolidates amendments up to loi n° 2010-39 "
    "du 26 juillet 2010 (IORT edition dated 2014-02-15). Amendments adopted "
    "after that date are absent. The official JORT archive at "
    "https://www.jort.tn/ is where they would be verified; that reconciliation "
    "is not part of v1.",
    "Repealed articles are absent from the published consolidated text (the "
    "table of contents marks them '(abrogés)'). The corpus therefore does not "
    "contain the repealed wording either.",
    "Amendment provenance is what the edition prints inline, for example "
    "'(Modifié par la loi n° 96-28 du 3 avril 1996)'. It is reproduced "
    "faithfully but not independently verified against the JORT.",
    "Footnotes (rectificatifs and editorial notes printed at page bottoms) are "
    "kept in annotations.jsonl, not merged into article text, because they are "
    "not part of the enacted article.",
    "The Arabic version of the same code is not machine-readable: its PDF has a "
    "broken ToUnicode map and extracts as glyph names, not Arabic text. See "
    "excluded_sources in manifest.json.",
    "Article text is re-flowed for readability: hard line breaks are joined, "
    "hyphenated word wraps are repaired, and enumerated items keep their own "
    "line. Wording, punctuation and article numbering are unchanged, but the "
    "line breaks do not match the printed page.",
    "Heading titles are reproduced as published, including upper-case "
    "typography, and renumbered words: the published 'LIVRE PREMIER' is "
    "recorded as 'Livre I' so book labels sort consistently.",
)


class BuildError(RuntimeError):
    """Raised when the corpus cannot be built without losing or faking content."""


@dataclass
class BuildResult:
    records: list[ArticleRecord]
    annotations: list[dict]
    toc_inventory: dict
    manifest: dict
    warnings: list[str]
    outputs: dict[str, Path] = field(default_factory=dict)


def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _page_span(records: list[ArticleRecord]) -> list[int]:
    pages = sorted({record.pdf_page for record in records})
    return [pages[0], pages[-1]] if pages else []


def extract_toc_inventory(toc_lines: list[Line]) -> dict:
    """Read the printed table of contents as a set of promised article ranges.

    This is a reconciliation aid, not a source of truth: it exists to prove that
    every article the table promises is either in the corpus or in a range the
    table itself marks as repealed.
    """
    text = _normalise_ws(" ".join(line.text for line in toc_lines))

    ranges: list[dict] = []
    for match in TOC_RANGE_RE.finditer(text):
        start, end = int(match.group(1)), int(match.group(2))
        if start <= end:
            ranges.append({"start": start, "end": end})

    abrogated: list[dict] = []
    for marker in ABROGATED_RE.finditer(text):
        preceding = text[: marker.start()]
        nearest = None
        for match in TOC_RANGE_RE.finditer(preceding):
            if marker.start() - match.end() <= 60:
                nearest = match
        if nearest is not None:
            start, end = int(nearest.group(1)), int(nearest.group(2))
            if start <= end and {"start": start, "end": end} not in abrogated:
                abrogated.append({"start": start, "end": end})

    def expand(items: list[dict]) -> set[int]:
        numbers: set[int] = set()
        for item in items:
            numbers.update(range(item["start"], item["end"] + 1))
        return numbers

    covered = expand(ranges)
    repealed = expand(abrogated)
    return {
        "ranges": sorted(ranges, key=lambda item: (item["start"], item["end"])),
        "abrogated_ranges": sorted(abrogated, key=lambda item: (item["start"], item["end"])),
        "numbers_covered": sorted(covered),
        "numbers_abrogated": sorted(repealed),
        "note": (
            "Derived from the printed table of contents by pattern matching, so it is "
            "approximate. It is used to explain missing article numbers, never to "
            "generate corpus records."
        ),
    }


def _coverage_for(
    document_id: str,
    records: list[ArticleRecord],
    toc_numbers: set[int],
    abrogated_numbers: set[int],
) -> dict:
    numbers = {record.article_number for record in records}
    if not numbers:
        return {
            "document_id": document_id,
            "parsed": 0,
            "numbers": [],
            "missing": [],
            "missing_explained_as_abrogated": [],
            "missing_unexplained": [],
        }
    highest = max(numbers)
    missing = sorted(set(range(1, highest + 1)) - numbers)
    explained = [number for number in missing if number in abrogated_numbers]
    unexplained = [number for number in missing if number not in abrogated_numbers]
    return {
        "document_id": document_id,
        "parsed": len(records),
        "distinct_numbers": len(numbers),
        "number_min": min(numbers),
        "number_max": highest,
        "missing": missing,
        "missing_explained_as_abrogated": explained,
        "missing_unexplained": unexplained,
        "not_in_table_of_contents": sorted(number for number in numbers if number not in toc_numbers),
    }


def _validate_all(records: list[ArticleRecord], warnings: list[str]) -> None:
    problems: list[str] = []
    seen: dict[str, int] = {}
    for record in records:
        seen[record.record_id] = seen.get(record.record_id, 0) + 1
        for problem in validate_record(record):
            problems.append(f"{record.record_id}: {problem}")
        if len(record.text.strip()) < SHORT_TEXT_CHARS and record.status != "repealed":
            warnings.append(
                f"{record.record_id} is unusually short "
                f"({len(record.text.strip())} chars); check it against page {record.pdf_page}"
            )
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    if duplicates:
        problems.append(
            "duplicate record ids (the parser found the same article twice): "
            + ", ".join(duplicates)
        )
    if problems:
        preview = "\n  ".join(problems[:20])
        more = "" if len(problems) <= 20 else f"\n  ... and {len(problems) - 20} more"
        raise BuildError(f"{len(problems)} record problem(s):\n  {preview}{more}")


def _annotations_from_parse(
    parse: ParseResult,
    spec: DocumentSpec,
    footnotes: list[Footnote],
) -> list[dict]:
    annotations: list[dict] = []
    if parse.front_matter.strip():
        annotations.append(
            {
                "record_type": "front_matter",
                "annotation_id": f"{spec.document_id}:front-matter",
                "document_id": spec.document_id,
                "title": spec.title,
                "language": spec.language,
                "text": parse.front_matter,
                "note": "Text printed before the first article of this document (for the law: the visas).",
            }
        )
    if parse.unattached.strip():
        annotations.append(
            {
                "record_type": "unattached_text",
                "annotation_id": f"{spec.document_id}:unattached-text",
                "document_id": spec.document_id,
                "title": spec.title,
                "language": spec.language,
                "text": parse.unattached,
                "note": (
                    "Editorial text printed between articles and belonging to no article, "
                    "for example a notice that a whole title is repealed. Not article text."
                ),
            }
        )
    for footnote in footnotes:
        annotations.append(
            {
                "record_type": "footnote",
                "annotation_id": f"{spec.document_id}:footnote-p{footnote.pdf_page}-{footnote.label or 'x'}",
                "document_id": spec.document_id,
                "title": spec.title,
                "language": spec.language,
                "label": footnote.label,
                "text": footnote.text,
                "pdf_page": footnote.pdf_page,
                "note": "Editorial footnote printed at the bottom of the page; not part of the enacted article.",
            }
        )
    return annotations


def build_corpus(
    *,
    raw_dir: Path,
    out_dir: Path,
    allow_download: bool = True,
    force_download: bool = False,
    timeout: int = 60,
    documents: tuple[DocumentSpec, ...] = DOCUMENTS,
) -> BuildResult:
    """Build the corpus and write every artefact into ``out_dir``."""
    warnings: list[str] = []
    resolved = ensure_sources(
        SOURCES, raw_dir, allow_download=allow_download, force=force_download, timeout=timeout
    )

    pages_by_source = {}
    for source in SOURCES:
        pages_by_source[source.source_id] = extract_pages(resolved[source.source_id])
        for page in pages_by_source[source.source_id]:
            if page.printed_number_seen is not None and page.printed_number_seen != page.printed_page:
                warnings.append(
                    f"{resolved[source.source_id].name} page {page.printed_page}: printed page "
                    f"number reads {page.printed_number_seen}; the two are expected to match"
                )

    all_records: list[ArticleRecord] = []
    annotations: list[dict] = []
    toc_inventory: dict = {}
    documents_manifest: list[dict] = []

    for spec in documents:
        source = source_by_id(spec.source_id)
        pages = pages_by_source[spec.source_id]
        stream = build_stream(pages)
        regions = detect_regions(stream)
        bounds = regions.bounds(spec.region)
        parse = parse_region(stream, bounds, spec, source)
        warnings.extend(f"{spec.document_id}: {warning}" for warning in parse.warnings)

        # Only pages that actually carry a line of this region count. The law
        # region ends with blank lines that spill onto the code's first page
        # (the cover title "CODE DE COMMERCE(1)"), so counting blank lines would
        # attribute the code's footnote to the law as well.
        region_pages = {
            line.pdf_page for line in stream[bounds[0]: bounds[1]] if line.text.strip()
        }
        footnotes = [
            note
            for page in pages
            if page.printed_page in region_pages
            for note in page.footnotes
        ]

        annotations.extend(_annotations_from_parse(parse, spec, footnotes))
        all_records.extend(parse.records)

        if spec.region == "code":
            toc_inventory = extract_toc_inventory(stream[regions.bounds("toc")[0]: regions.total_lines])

        documents_manifest.append(
            {
                "document_id": spec.document_id,
                "title": spec.title,
                "language": spec.language,
                "source_id": spec.source_id,
                "source_url": source.url,
                "source_sha256": source.sha256,
                "law_number": spec.law_number,
                "law_date": spec.law_date,
                "notes": spec.notes,
                "article_count": len(parse.records),
                "pdf_page_range": _page_span(parse.records),
                "footnote_count": len(footnotes),
            }
        )

    all_records.sort(key=lambda record: record.sort_key)
    _validate_all(all_records, warnings)

    toc_numbers = set(toc_inventory.get("numbers_covered", []))
    abrogated_numbers = set(toc_inventory.get("numbers_abrogated", []))

    coverage = []
    for entry in documents_manifest:
        doc_records = [r for r in all_records if r.document_id == entry["document_id"]]
        doc_coverage = _coverage_for(
            entry["document_id"], doc_records, toc_numbers, abrogated_numbers
        )
        coverage.append(doc_coverage)
        entry["coverage"] = doc_coverage
        for number in doc_coverage["missing_unexplained"]:
            warnings.append(
                f"{entry['document_id']}: article {number} is promised by the table of "
                "contents, is not marked '(abrogés)' and was not parsed; check the PDF page"
            )

    annotations.sort(key=lambda item: item["annotation_id"])
    digests = write_corpus_files(
        out_dir=out_dir,
        records=all_records,
        annotations=annotations,
        toc_inventory=toc_inventory,
    )
    coverage_by_doc = {item["document_id"]: item for item in coverage}

    manifest = {
        "corpus_version": CORPUS_VERSION,
        "generator": "project 2/src/ingestion (python -m src.ingestion build)",
        "record_file": "corpus.jsonl",
        "annotation_file": "annotations.jsonl",
        "toc_file": "toc_inventory.json",
        "record_count": len(all_records),
        "annotation_count": len(annotations),
        "documents": documents_manifest,
        "sources": [
            {
                "source_id": source.source_id,
                "url": source.url,
                "title": source.title,
                "language": source.language,
                "publisher": source.publisher,
                "edition": source.edition,
                "edition_date": source.edition_date,
                "amendment_horizon": source.amendment_horizon,
                "permission": source.permission,
                "permission_note": source.permission_note,
                "sha256": source.sha256,
                "bytes": source.expected_bytes,
            }
            for source in SOURCES
        ],
        "excluded_sources": [
            {
                "source_id": item.source_id,
                "url": item.url,
                "title": item.title,
                "language": item.language,
                "reason": item.reason,
                "evidence": item.evidence,
            }
            for item in REJECTED_SOURCES
        ],
        "pending_instructor_approval": [
            {"title": item.title, "url": item.url, "language": item.language, "status": item.status}
            for item in PENDING_TEXTS
        ],
        "coverage": coverage_by_doc,
        "toc_inventory_summary": {
            "ranges": len(toc_inventory.get("ranges", [])),
            "abrogated_ranges": toc_inventory.get("abrogated_ranges", []),
        },
        "known_limitations": list(KNOWN_LIMITATIONS),
        "warnings": sorted(warnings),
        "outputs": {
            "corpus.jsonl": digests["corpus"],
            "annotations.jsonl": digests["annotations"],
            "toc_inventory.json": digests["toc_inventory"],
            "manifest.json": "self; not hashed",
            "LIMITATIONS.md": "rendered from this manifest",
        },
    }

    paths = {
        "corpus": out_dir / "corpus.jsonl",
        "annotations": out_dir / "annotations.jsonl",
        "toc_inventory": out_dir / "toc_inventory.json",
        "manifest": out_dir / "manifest.json",
        "limitations": out_dir / "LIMITATIONS.md",
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths["limitations"].write_text(render_limitations(manifest), encoding="utf-8", newline="\n")

    return BuildResult(
        records=all_records,
        annotations=annotations,
        toc_inventory=toc_inventory,
        manifest=manifest,
        warnings=sorted(warnings),
        outputs=paths,
    )


def _sha256_of_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_corpus_files(
    *,
    out_dir: Path,
    records: list[ArticleRecord],
    annotations: list[dict],
    toc_inventory: dict,
) -> dict:
    """Write the deterministic data files and return their digests."""
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = out_dir / "corpus.jsonl"
    corpus_path.write_text(
        "".join(record.to_json() + "\n" for record in records), encoding="utf-8", newline="\n"
    )

    annotations_path = out_dir / "annotations.jsonl"
    annotations_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in annotations
        ),
        encoding="utf-8",
        newline="\n",
    )

    toc_path = out_dir / "toc_inventory.json"
    toc_path.write_text(
        json.dumps(toc_inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "corpus": _sha256_of_text(corpus_path),
        "annotations": _sha256_of_text(annotations_path),
        "toc_inventory": _sha256_of_text(toc_path),
    }


def render_limitations(manifest: dict) -> str:
    """Render the human-readable handoff document."""
    lines: list[str] = [
        "# Corpus limitations",
        "",
        "Generated by the build in `project 2/src/ingestion`. Do not edit by hand:",
        "change the pipeline or the source registry and rebuild.",
        "",
        f"Corpus version: {manifest['corpus_version']} — "
        f"{manifest['record_count']} article records, "
        f"{manifest['annotation_count']} annotations.",
        "",
        "## Sources",
        "",
        "| Document | Source | Edition | SHA-256 |",
        "|---|---|---|---|",
    ]
    for document in manifest["documents"]:
        lines.append(
            f"| {document['document_id']} | {document['title']} | "
            f"{document['source_url']} | ...{document['source_sha256'][-12:]} |"
        )

    lines += ["", "## Coverage", "", "| Document | Articles | Range | Missing | Explained as repealed | Unexplained |", "|---|---|---|---|---|---|"]
    for document in manifest["documents"]:
        coverage = document["coverage"]
        if not coverage.get("parsed"):
            lines.append(f"| {document['document_id']} | 0 | - | - | - | - |")
            continue
        lines.append(
            f"| {document['document_id']} | {coverage['parsed']} | "
            f"{coverage['number_min']}–{coverage['number_max']} | "
            f"{len(coverage['missing'])} | {len(coverage['missing_explained_as_abrogated'])} | "
            f"{len(coverage['missing_unexplained'])} |"
        )
    abrogated = manifest.get("toc_inventory_summary", {}).get("abrogated_ranges", [])
    if abrogated:
        rendered = ", ".join(f"{item['start']}–{item['end']}" for item in abrogated)
        lines += [
            "",
            f"Ranges the table of contents marks `(abrogés)`: {rendered}.",
            "Missing article numbers inside those ranges are explained by repeal.",
        ]

    lines += ["", "## Known limitations", ""]
    for index, limitation in enumerate(manifest["known_limitations"], start=1):
        lines.append(f"{index}. {limitation}")

    lines += ["", "## Build warnings", ""]
    if manifest["warnings"]:
        for warning in manifest["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("None.")

    lines += ["", "## Excluded sources", ""]
    for item in manifest["excluded_sources"]:
        lines.append(f"- **{item['title']}** ({item['language']}): {item['reason']}")
        lines.append(f"  - {item['evidence']}")

    lines += ["", "## Awaiting instructor approval", ""]
    for item in manifest["pending_instructor_approval"]:
        lines.append(f"- {item['title']} ({item['language']}, {item['status']}): {item['url']}")
    return "\n".join(lines) + "\n"
