"""Article-aware chunking for the processed legal corpus."""
from __future__ import annotations

from dataclasses import dataclass

from ingestion.schema import ArticleRecord

ChunkStrategy = str
CHUNK_STRATEGIES: tuple[str, ...] = ("article", "window")


@dataclass(frozen=True)
class ArticleChunk:
    """A searchable passage with the source article metadata attached."""

    chunk_id: str
    record_id: str
    text: str
    chunk_index: int
    chunk_count: int
    article: str
    article_number: int
    heading_path: tuple[str, ...]
    document_id: str
    language: str
    pdf_page: int
    printed_page: int | None
    source_url: str
    source_sha256: str
    source_date: str
    source_edition: str


def _validate_options(strategy: ChunkStrategy, max_words: int, overlap_words: int) -> None:
    if strategy not in CHUNK_STRATEGIES:
        raise ValueError(f"strategy must be one of {CHUNK_STRATEGIES}, got {strategy!r}")
    if max_words < 1:
        raise ValueError("max_words must be at least 1")
    if overlap_words < 0:
        raise ValueError("overlap_words must not be negative")
    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words")


def _windows(words: list[str], max_words: int, overlap_words: int) -> list[str]:
    if len(words) <= max_words:
        return [" ".join(words)]

    step = max_words - overlap_words
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return chunks


def _make_chunks(record: ArticleRecord, texts: list[str]) -> list[ArticleChunk]:
    count = len(texts)
    return [
        ArticleChunk(
            chunk_id=f"{record.record_id}:chunk-{index}",
            record_id=record.record_id,
            text=text,
            chunk_index=index,
            chunk_count=count,
            article=record.article,
            article_number=record.article_number,
            heading_path=tuple(record.heading_path),
            document_id=record.document_id,
            language=record.language,
            pdf_page=record.pdf_page,
            printed_page=record.printed_page,
            source_url=record.source_url,
            source_sha256=record.source_sha256,
            source_date=record.source_date,
            source_edition=record.source_edition,
        )
        for index, text in enumerate(texts)
    ]


def chunk_article(
    record: ArticleRecord,
    *,
    strategy: ChunkStrategy = "article",
    max_words: int = 220,
    overlap_words: int = 40,
) -> list[ArticleChunk]:
    """Create searchable chunks for one published article record."""
    _validate_options(strategy, max_words, overlap_words)
    if record.status == "repealed":
        return []
    if not record.text.strip():
        raise ValueError(f"{record.record_id}: published article has empty text")

    if strategy == "article":
        texts = [record.text.strip()]
    else:
        texts = _windows(record.text.split(), max_words, overlap_words)
    return _make_chunks(record, texts)


def chunk_records(
    records: list[ArticleRecord] | tuple[ArticleRecord, ...],
    *,
    strategy: ChunkStrategy = "article",
    max_words: int = 220,
    overlap_words: int = 40,
) -> list[ArticleChunk]:
    """Chunk records in input order using one consistent strategy."""
    _validate_options(strategy, max_words, overlap_words)
    chunks: list[ArticleChunk] = []
    for record in records:
        chunks.extend(
            chunk_article(
                record,
                strategy=strategy,
                max_words=max_words,
                overlap_words=overlap_words,
            )
        )
    return chunks
