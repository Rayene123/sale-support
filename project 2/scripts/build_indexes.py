"""Build reproducible local retrieval indexes.

Run from the repository root:

    python "project 2/scripts/build_indexes.py"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from indexing.chunking import chunk_records
from indexing.corpus import load_corpus
from retrieval.bm25 import BM25Retriever
from retrieval.semantic import SemanticRetriever, SentenceTransformerEmbedder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        default=str(PROJECT_DIR / "data" / "processed" / "corpus.jsonl"),
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_DIR / "data" / "indexes"),
    )
    parser.add_argument(
        "--strategy",
        choices=("article", "window"),
        default="article",
    )
    parser.add_argument("--max-words", type=int, default=220)
    parser.add_argument("--overlap-words", type=int, default=40)
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    args = parser.parse_args()

    records = load_corpus(args.corpus)
    chunks = chunk_records(
        records,
        strategy=args.strategy,
        max_words=args.max_words,
        overlap_words=args.overlap_words,
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    (output / "chunks.jsonl").write_text(
        "\n".join(
            json.dumps(chunk.__dict__, ensure_ascii=False, sort_keys=True)
            for chunk in chunks
        )
        + "\n",
        encoding="utf-8",
    )
    BM25Retriever(chunks)
    embedder = SentenceTransformerEmbedder(args.model)
    semantic = SemanticRetriever(chunks, embedder=embedder)
    semantic.save(output / "semantic")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "corpus": str(Path(args.corpus)),
                "chunk_strategy": args.strategy,
                "chunk_count": len(chunks),
                "embedding_model": args.model,
                "embedding_dimension": int(semantic.embeddings.shape[1]),
                "files": ["chunks.jsonl", "semantic/embeddings.npy", "semantic/chunk_ids.txt"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"records: {len(records)}")
    print(f"chunks: {len(chunks)}")
    print(f"embedding dimension: {semantic.embeddings.shape[1]}")
    print(f"index: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
