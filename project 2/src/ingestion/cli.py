"""Command-line interface for the corpus build.

Run from ``project 2/``::

    python -m src.ingestion build
    python -m src.ingestion build --no-download
    python -m src.ingestion verify --corpus data/processed/corpus.jsonl

``build`` downloads what is missing, verifies every source hash, parses the
documents and writes ``data/processed/``. ``verify`` re-checks an already built
corpus without touching the network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .build import build_corpus
from .schema import ArticleRecord, validate_record

DEFAULT_RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


def _load_records(path: Path) -> list[ArticleRecord]:
    records: list[ArticleRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: not valid JSON: {exc}") from exc
            records.append(ArticleRecord(**payload))
    return records


def _cmd_build(args: argparse.Namespace) -> int:
    result = build_corpus(
        raw_dir=Path(args.raw_dir),
        out_dir=Path(args.out_dir),
        allow_download=not args.no_download,
        force_download=args.force,
        timeout=args.timeout,
    )

    print(f"corpus version : {result.manifest['corpus_version']}")
    print(f"records        : {len(result.records)}")
    for document in result.manifest["documents"]:
        coverage = document["coverage"]
        if coverage.get("parsed"):
            print(
                f"  - {document['document_id']}: {coverage['parsed']} articles, "
                f"numbers {coverage['number_min']}–{coverage['number_max']}, "
                f"{len(coverage['missing_explained_as_abrogated'])} missing as repealed, "
                f"{len(coverage['missing_unexplained'])} unexplained"
            )
        else:
            print(f"  - {document['document_id']}: no articles parsed")
    print(f"annotations    : {len(result.annotations)}")
    if result.warnings:
        print(f"warnings       : {len(result.warnings)}")
        for warning in result.warnings:
            print(f"  ! {warning}")
    for name, path in result.outputs.items():
        if name in ("corpus", "annotations", "toc_inventory", "manifest", "limitations"):
            print(f"wrote          : {path}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.corpus)
    if not path.is_file():
        raise SystemExit(f"corpus file not found: {path}")
    records = _load_records(path)
    problems: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.record_id in seen:
            problems.append(f"{record.record_id}: duplicate record id")
        seen.add(record.record_id)
        problems.extend(f"{record.record_id}: {p}" for p in validate_record(record))
    print(f"records checked: {len(records)}")
    if problems:
        for problem in problems[:40]:
            print(f"  ! {problem}")
        print(f"FAILED: {len(problems)} problem(s)")
        return 1
    print("OK: every record matches the schema")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.ingestion", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="download, verify and parse the corpus")
    build.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="where source PDFs live")
    build.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="where artefacts are written")
    build.add_argument(
        "--no-download",
        action="store_true",
        help="never touch the network; require the PDFs to be present and correct",
    )
    build.add_argument("--force", action="store_true", help="re-download even if the file exists")
    build.add_argument("--timeout", type=int, default=60, help="download timeout in seconds")
    build.set_defaults(func=_cmd_build)

    verify = subparsers.add_parser("verify", help="re-validate an existing corpus.jsonl")
    verify.add_argument(
        "--corpus",
        default=str(DEFAULT_OUT_DIR / "corpus.jsonl"),
        help="path to corpus.jsonl",
    )
    verify.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
