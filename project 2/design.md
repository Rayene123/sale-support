# Design

This file documents the final corpus, chunking experiments, index choice,
retrieval and reranking design, generation constraints, citation format, and
known failure cases.

## Corpus (v2) — decided

### Source and permission

- Source of record: the 2024 IORT edition of the Code de commerce
  (`code-commerce-fr-iort-2024`), 193 pages, revised 15 February 2024,
  published by the Imprimerie Officielle de la République Tunisienne.
- Edition horizon: consolidates the code as amended up to at least loi
  n° 2019-47 du 29 mai 2019 (the latest amendment the text cites). The
  publisher landing page is `https://www.justice.gov.tn/index.php?id=289`.
- Permission: official published text, reproduced verbatim for non-commercial
  educational research. The registry records this per source
  (`src/ingestion/sources.py`) and refuses to read a file whose SHA-256 does not
  match the recorded
  `353bca554ab5deaf229648485a271bc6fb65fa514b9785511d38f4e47393e7aa`.
- The earlier **2014** edition is the same legal text with an older horizon; it
  is the same legal text, so ingesting both would duplicate article numbers. It
  is retired to `SUPERSEDED_SOURCES` and shown in `manifest.json →
  superseded_sources`.
- The 2024 bytes are not downloadable: the publisher's URL still serves the
  2014 file. The source is therefore marked `downloadable=False` and the raw PDF
  must be supplied by hand — see the local-only limitation in `LIMITATIONS.md`.

### Scope

- v1 ingests the **French** Code of Commerce only.
- The Arabic twin (`CommerceArabe.pdf`) is **excluded**: its `ToUnicode` map is
  broken and pypdf returns glyph names, not Arabic text. OCR is out of scope.
  It is kept in the manifest under `excluded_sources` with the evidence.
- Related codes are **not** ingested in v1; the README requires instructor
  approval first. They are recorded as `pending_instructor_approval`.

### Documents and stable ids

- The one PDF holds two legal documents, split so identically numbered articles
  cannot collide: the code (`code-commerce-tn`, region `code`) and the
  promulgating law `loi n° 59-129` (`loi-59-129-1959`, region `law`,
  articles 1–5).
- Record ids are `<document_id>:article-<n>[-<suffix>]`, e.g.
  `code-commerce-tn:article-231-bis`. Suffixes (`bis`, `ter`, …) are part of the
  id, so a lettered variant never overwrites its base article.
- `LIVRE PREMIER` is normalised to `Livre I` so book labels sort consistently;
  otherwise headings are reproduced as published, hierarchy included, and every
  record keeps a `heading_path`.

### Text normalisation

- Running header and printed page numbers are stripped; hyphenated line wraps
  are repaired; whitespace and non-breaking spaces are normalised; hard-wrapped
  lines are re-flowed into paragraphs while enumerated items and bullets keep
  their own line.
- Wording, punctuation and article numbering are unchanged, so line breaks do
  not match the printed page. This trade-off is recorded as a limitation.

### Repealed articles

- The consolidation does not reprint repealed articles; it prints a repeal note.
  Such records are emitted with `status: "repealed"` and empty `text` — they are
  citation anchors ("article 6 is repealed"), never retrievable body text.
- Missing numbers inside a repealed range are not emitted at all. The ranges
  the table of contents marks `(abrogés)` are recorded in
  `toc_inventory.json` / `manifest.json`.

### Coverage is measured, not assumed

- The build reconciles the parsed articles against the table of contents. It
  explains every gap as repeal or reports it as a warning; the current build has
  **0 unexplained gaps and 1 warning** (579 code + 5 law records, 175 gaps all
  inside the repealed ranges 14–188 and 461–465; the single warning is the
  article-465 source inconsistency).
- The table of contents is a reconciliation aid only; it never generates a
  record.

### Repository policy

- Raw PDFs are git-ignored and downloaded on demand; the processed corpus,
  manifest and limitations are committed so People 2–4 can work without a
  network round trip.
- The build writes no timestamps and sorts deterministically, so two runs from
  the same verified PDF are byte-identical. Output digests are recorded in
  `manifest.json`.

### Schema and tests

- The record format is defined in `docs/CORPUS_SCHEMA.md` and enforced in
  `src/ingestion/schema.py`; a validation failure aborts the build.
- 111 unit and integration tests cover heading detection, article splitting,
  suffix/amendment parsing, normalisation, that schema, and the real end-to-end
  build.

## Retrieval decisions

- **Chunking** — article-level chunks are the legal-safe baseline; 220-word
  windows with 40-word overlap are available for long-article comparison.
- **Keyword index** — dependency-free Okapi BM25 over normalized article chunks.
- **Semantic index** — Sentence Transformers
  `paraphrase-multilingual-MiniLM-L12-v2`, with normalized 384-dimensional
  vectors and cosine similarity. The current deployment can query the
  `librarian-chunks` Qdrant collection; a local NumPy index remains available.
- **Persistence** — Qdrant stores vectors and citation payloads when configured;
  local NumPy embeddings and the processed corpus remain reproducible fallbacks.
  BM25 is built over the chunk payloads loaded from Qdrant because the current
  collection is dense-only.
- **Hybrid fusion** — Reciprocal Rank Fusion combines local BM25 and Qdrant
  semantic rankings without assuming their scores share a scale.
- **Reranker** — deterministic exact-term coverage, phrase match, and article
  number match are the initial reproducible baseline; a cross-encoder can be
  measured as an optimization.
- **Metadata filters** — exact filters for document, language, article,
  hierarchy, and PDF page are applied before retrieval.
- **Abstention** — the generation layer abstains when retrieval returns no
  candidates. The API also supports the calibrated `MIN_RETRIEVAL_SCORE`
  environment variable to remove weak BM25 matches before generation; it
  defaults to `0` until a development-only threshold is selected.
- **Citation validation** — every generated citation must refer to a returned
  chunk ID and its attached article/page metadata.

## Person 2 measurement handoff

The reproducible index command is:

```powershell
python "project 2/scripts/build_indexes.py"
```

It saves chunk metadata and normalized semantic embeddings under
`data/indexes/`. BM25 is rebuilt from the same chunks in memory; the processed
corpus remains authoritative.

The development evaluation command is:

```powershell
python "project 2/eval/retrieval.py"
```

It reports recall@1/3/5/10 and p50/p95 retrieval latency. The final ablation
must use Person 4's labeled set and compare BM25, semantic vector, hybrid, and
hybrid plus reranker on the same questions.

### Current smoke measurements

The 8-question development smoke run produced:

| Method | Recall@1 | Recall@3 | Recall@5 | Recall@10 | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 25.0% | 37.5% | 50.0% | 75.0% | 2.63 | 3.29 |
| Semantic vector | 25.0% | 37.5% | 50.0% | 75.0% | 23.22 | 23.48 |
| Hybrid | **37.5%** | **50.0%** | 50.0% | 75.0% | 26.87 | 30.74 |
| Hybrid + reranker | 37.5% | 37.5% | 37.5% | 75.0% | 29.81 | 31.66 |

These are development measurements, not final project metrics: the sample has
only 8 questions. The hybrid retriever caches document indexes and embeds only
the query at request time; the earlier approximately 16-second median was
caused by rebuilding document embeddings for every query.

Known failure cases are: missing terminology in the French corpus, post-2019
amendments, repealed wording, long cross-references, ambiguous questions, and
reranking heuristics that are not yet shown to improve quality on a sufficiently
large labeled set.
