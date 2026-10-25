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

## Completed implementation

The retrieval implementation is in `src/indexing/` and `src/retrieval/`.

Build the local BM25 and semantic index with:

```powershell
python "project 2/scripts/build_indexes.py"
```

The command writes `data/indexes/chunks.jsonl`, semantic embeddings, chunk IDs,
and an index manifest. The default embedding model is
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

Use the stable facade from `src/retrieval/service.py`:

```python
service.retrieve(
    "Quels biens font partie du fonds de commerce ?",
    method="hybrid",
    top_k=5,
    rerank_results=False,
)
```

The supported methods are `bm25`, `vector`, and `hybrid`. Reranking is
available with `rerank_results=True`, but it is not enabled by default because
it did not improve the current smoke-set Recall@3 or Recall@5.

Results use `models.retrieval.RetrievalResult` and always retain the chunk ID,
article ID, article number, heading path, PDF page, source URL, score, rank,
and retrieval method.

The article strategy produces 582 searchable chunks. The 220-word/40-word
overlap strategy produces 631 chunks. Repealed articles are excluded from
normal text retrieval because the consolidated source contains no article body.

### Qdrant Cloud vector index

The local NumPy semantic index is the default. The same chunks can also be
stored in Qdrant Cloud (or a self-hosted Qdrant) and used for `method="vector"`
or `method="hybrid"`.

1. In the Qdrant Cloud console, create a cluster and copy its endpoint and API
   key. The free tier is sufficient for this corpus (a few hundred vectors at
   384 dimensions).
2. Put the values in the repository `.env` (git-ignored) or the environment:

   ```dotenv
   QDRANT_URL=https://<cluster-id>.cloud.qdrant.io:6333
   QDRANT_API_KEY=<secret>
   QDRANT_COLLECTION=librarian-chunks
   # QDRANT_PREFER_GRPC=true
   ```

3. Install the dependencies (already listed in `requirements.txt`):

   ```powershell
   python -m pip install -r "project 2/requirements.txt"
   ```

4. Chunk, embed, and upload the corpus. Use `--recreate` for the first upload
   and after changing the embedding model or chunking strategy:

   ```powershell
   python "project 2/scripts/upload_qdrant.py" --recreate
   ```

   The script reuses the article-aware chunker and
   `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384
   dimensions), then upserts one point per chunk. Point IDs are derived from
   `chunk_id`, so re-running without `--recreate` overwrites existing points
   instead of duplicating them. The collection uses cosine distance.

   Each point payload carries the citation fields (`chunk_id`, `record_id`,
   `article`, `article_number`, `heading_path`, `pdf_page`, `source_url`) plus
   the flattened heading levels (`book`, `titre`, `chapitre`, `section`,
   `sous_section`).

5. Use it through the normal facade:

   ```python
   from retrieval.qdrant import retriever_from_env
   from retrieval.service import RetrievalService

   service = RetrievalService(chunks, semantic_retriever=retriever_from_env())
   results = service.retrieve(
       "Quels biens font partie du fonds de commerce ?",
       method="vector",
       top_k=5,
   )
   ```

`method="hybrid"` combines Qdrant semantic results with the local BM25 index
using RRF. Metadata filters accepted by the service are pushed down to Qdrant
for the semantic side. `article_suffix` is not stored on chunks, so it is not a
supported Qdrant filter.

The web API in `src/api/app.py` currently calls BM25 directly. To serve
Qdrant-backed answers, construct its `RetrievalService` with
`semantic_retriever=retriever_from_env()` and change the `method=` argument in
the `/ask` route to `"vector"` or `"hybrid"`.

Never commit `.env` or a real API key; the committed `.env.example` contains
placeholders only. Changing the embedding model changes the vector dimension:
recreate the collection instead of mixing dimensions.

### Retrieval ablation

The current development smoke set contains 8 labeled questions. Results are
recorded in `data/eval/retrieval_results.json`:

| Method | Recall@1 | Recall@3 | Recall@5 | Recall@10 | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 25.0% | 37.5% | 50.0% | 75.0% | 2.63 | 3.29 |
| Semantic vector | 25.0% | 37.5% | 50.0% | 75.0% | 23.22 | 23.48 |
| Hybrid | **37.5%** | **50.0%** | 50.0% | 75.0% | 26.87 | 30.74 |
| Hybrid + reranker | 37.5% | 37.5% | 37.5% | 75.0% | 29.81 | 31.66 |

The smoke set is too small for final quality claims: one question changes a
recall percentage by 12.5 points. Person 4 owns the required larger labeled
evaluation set. These numbers establish the Person 2 baseline and the
keyword/vector/hybrid/reranker comparison.

### Performance fix

The first hybrid implementation recreated the semantic index for every query,
including re-embedding all 582 chunks. That produced approximately 16 seconds
median latency. The current implementation caches BM25 and semantic indexes at
retriever construction and embeds only the query at search time. Hybrid
latency is now approximately 26.87 ms median and 30.74 ms p95 on the smoke
run.

The smoke evaluation data is in `data/eval/retrieval_smoke.jsonl`. Run:

```powershell
python "project 2/eval/retrieval.py"
```

This reports recall@1/3/5/10 and p50/p95 retrieval latency. The smoke set is a
development fixture; Person 4 owns the required 100+ labeled evaluation set.

### Known retrieval failures

- Questions use terminology absent from the French source or use a different
  legal paraphrase.
- Questions require amendments later than the 2024 edition's documented
  horizon.
- Questions ask for the wording of repealed articles, which is not present in
  the consolidated source.
- Cross-reference questions require following more than one article.
- Ambiguous questions do not provide enough metadata or legal context.
- The current reranker can lower Recall@3/5, so hybrid without reranking is
  the default until a larger evaluation set justifies a change.
