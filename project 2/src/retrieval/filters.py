"""Metadata filtering for retrieval candidates."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from indexing.chunking import ArticleChunk, chunk_metadata


def filter_chunks(
    chunks: Iterable[ArticleChunk],
    filters: Mapping[str, object] | None = None,
) -> list[ArticleChunk]:
    """Return chunks matching exact supported metadata filters."""
    if not filters:
        return list(chunks)
    supported = {
        "chunk_id",
        "record_id",
        "document_id",
        "language",
        "article_number",
        "article_suffix",
        "book",
        "titre",
        "chapitre",
        "section",
        "sous_section",
        "pdf_page",
    }
    unknown = set(filters) - supported
    if unknown:
        raise ValueError(f"unsupported metadata filters: {sorted(unknown)}")

    matches: list[ArticleChunk] = []
    for chunk in chunks:
        values = {
            "chunk_id": chunk.chunk_id,
            "record_id": chunk.record_id,
            "document_id": chunk.document_id,
            "language": chunk.language,
            "article_number": chunk.article_number,
            **chunk_metadata(chunk),
            "pdf_page": chunk.pdf_page,
        }
        if all(
            values.get(key) in expected if isinstance(expected, (list, tuple, set, frozenset))
            else values.get(key) == expected
            for key, expected in filters.items()
        ):
            matches.append(chunk)
    return matches
