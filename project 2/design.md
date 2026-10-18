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

## Decisions still to record

- Chunk size and overlap, or article-aware chunking
- BM25 implementation
- Vector store and embedding model
- Hybrid fusion method
- Reranker and cutoff
- Metadata filters
- Abstention rule
- Citation validation strategy
