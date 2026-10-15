# Person 2 — Chunking, indexing, and retrieval

## Ownership

Implement and measure the search pipeline: chunking, BM25, vector search,
hybrid fusion, metadata filtering, and reranking.

## Tasks

- Implement article-aware chunking and at least two comparison strategies.
- Keep article and section metadata attached to every chunk.
- Build keyword-only and vector-only retrieval.
- Combine them into hybrid retrieval.
- Add reranking and configurable top-k values.
- Expose a stable retrieval result schema for Person 3.
- Measure recall@k and retrieval latency.
- Produce the keyword-only/vector-only/hybrid/hybrid-plus-reranker ablation.

## Dependencies

This work can start without another person's output by using a checked-in
small fixture or synthetic article-shaped records. It will need Person 1's
processed corpus before final measurements and index generation.

## Handoff

Provide:

- Index-building command
- Retrieval API and result schema
- Chunking experiment table
- Ablation results
- Retrieval failure examples
