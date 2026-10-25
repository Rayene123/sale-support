"""Upload the processed corpus chunks to Qdrant Cloud or a local Qdrant.

Set ``QDRANT_URL`` and ``QDRANT_API_KEY`` (and optionally
``QDRANT_COLLECTION``) in the environment or in the repository ``.env`` file,
then run from the repository root:

    python "project 2/scripts/upload_qdrant.py" --recreate

Point ids are derived from ``chunk_id``, so a later upload without
``--recreate`` overwrites the same points instead of duplicating them. Use
``--recreate`` after changing the embedding model (the vector dimension
changes) or the chunking strategy (stale chunks would otherwise remain).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _load_dotenv() -> None:
    """Load the repository ``.env`` without making python-dotenv mandatory."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_DIR.parent / ".env")
    load_dotenv()


def main() -> int:
    _load_dotenv()

    from indexing.chunking import chunk_records
    from indexing.corpus import load_corpus
    from retrieval.qdrant import (
        DEFAULT_MODEL,
        QdrantConfig,
        create_client,
        upload_chunks,
    )
    from retrieval.semantic import SentenceTransformerEmbedder

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        default=str(PROJECT_DIR / "data" / "processed" / "corpus.jsonl"),
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="collection name; defaults to QDRANT_COLLECTION",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--strategy",
        choices=("article", "window"),
        default="article",
    )
    parser.add_argument("--max-words", type=int, default=220)
    parser.add_argument("--overlap-words", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="delete and recreate the collection before uploading",
    )
    args = parser.parse_args()

    try:
        config = QdrantConfig.from_env()
    except ValueError as exc:
        parser.error(str(exc))

    collection = args.collection or config.collection
    records = load_corpus(args.corpus)
    chunks = chunk_records(
        records,
        strategy=args.strategy,
        max_words=args.max_words,
        overlap_words=args.overlap_words,
    )

    embedder = SentenceTransformerEmbedder(args.model)
    embeddings = embedder.encode(
        [chunk.text for chunk in chunks],
        normalize_embeddings=True,
    )

    client = create_client(config)
    summary = upload_chunks(
        client,
        chunks,
        embeddings,
        collection=collection,
        batch_size=args.batch_size,
        recreate=args.recreate,
    )
    stored = client.count(collection_name=collection, exact=True).count

    print(f"records: {len(records)}")
    print(f"chunks: {len(chunks)}")
    print(f"embedding model: {args.model}")
    print(f"embedding dimension: {summary['dimension']}")
    print(
        f"collection: {collection} "
        f"({'created' if summary['created'] else 'reused'})"
    )
    print(f"uploaded: {summary['uploaded']}")
    print(f"stored points: {stored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
