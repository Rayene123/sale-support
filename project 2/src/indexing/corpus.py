"""Load and validate processed corpus records for indexing."""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.schema import ArticleRecord, validate_record


class CorpusLoadError(ValueError):
    """Raised when a corpus file cannot be safely used for indexing."""


def load_corpus(
    path: Path | str,
    *,
    include_repealed: bool = False,
) -> list[ArticleRecord]:
    """Load validated article records from a JSONL corpus.

    Repealed records are validated but excluded by default because they have no
    article body to search. Set ``include_repealed=True`` when a caller needs
    repeal-status records for metadata or citation lookup.
    """
    corpus_path = Path(path)
    if not corpus_path.is_file():
        raise CorpusLoadError(f"corpus file not found: {corpus_path}")

    records: list[ArticleRecord] = []
    seen_ids: set[str] = set()
    try:
        handle = corpus_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise CorpusLoadError(f"could not open corpus file {corpus_path}: {exc}") from exc

    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusLoadError(
                    f"{corpus_path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise CorpusLoadError(
                    f"{corpus_path}:{line_number}: expected a JSON object"
                )

            try:
                record = ArticleRecord(**payload)
            except (TypeError, ValueError) as exc:
                raise CorpusLoadError(
                    f"{corpus_path}:{line_number}: invalid article record: {exc}"
                ) from exc

            problems = validate_record(record)
            if problems:
                joined = "; ".join(problems)
                raise CorpusLoadError(
                    f"{corpus_path}:{line_number}: invalid article record: {joined}"
                )
            if record.record_id in seen_ids:
                raise CorpusLoadError(
                    f"{corpus_path}:{line_number}: duplicate record_id "
                    f"{record.record_id!r}"
                )
            seen_ids.add(record.record_id)

            if include_repealed or record.status != "repealed":
                records.append(record)

    return records
