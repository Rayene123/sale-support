# Design

This file will document the final corpus, chunking experiments, index choice,
retrieval and reranking design, generation constraints, citation format, and
known failure cases.

## Decisions to record

- Corpus scope and permission/source verification
- Supported languages
- Chunk size and overlap or article-aware chunking
- BM25 implementation
- Vector store and embedding model
- Hybrid fusion method
- Reranker and cutoff
- Metadata filters
- Abstention rule
- Citation validation strategy
