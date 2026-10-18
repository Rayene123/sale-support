# Person 1 — Corpus implementation plan

Status: **implemented** (v2, 2024 edition).
This plan is the working document for the Week 5 corpus milestone.

> **v2 revision.** The corpus was first built from the 2014 IORT edition
> (`CommerceFr.pdf`). A newer **2024 IORT edition** was then supplied, and the
> decision (recorded below) was to make it the source of record and retire the
> 2014 edition. The two are the same legal text; ingesting both would duplicate
> article numbers, so only the 2024 edition is ingested.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Corpus scope, v1 | French Code de Commerce, single document | Only text with a clean, verifiable text layer. |
| Source of record | 2024 IORT edition (`code-commerce-fr-iort-2024`) | Newer consolidation; includes amendments through loi n° 2019-47. |
| Superseded source | 2014 IORT edition (`code-commerce-fr-iort-2014`) retired | Same text, older horizon; keeping both duplicates article numbers. Kept in the registry as `superseded`. |
| Arabic twin | Excluded, kept in the manifest as a rejected source | Broken ToUnicode map: extraction yields glyph names (`/tehmarbutafinal/`), not Arabic text. OCR is out of scope. |
| Related codes | Not ingested | README requires instructor approval before adding texts. List is recorded, not implemented. |
| Raw PDFs in git | Ignored; the 2024 file is a supplied local source, hash-verified on every build | The 2024 file has no public download URL, so the build cannot fetch it. The SHA-256 in the registry is the guarantee of the bytes. |
| Processed corpus in git | Committed | People 2, 3 and 4 need the corpus without a network round trip. |
| Chunking | Not done here | Person 2 owns chunking. This layer emits article-level records. |

## Source of record (2024)

- File: `data/raw/code-commerce-fr-iort-2024.pdf`
- Title: *Code de commerce* (République Tunisienne), 2024
- Edition: Imprimerie Officielle de la République Tunisienne,
  "Edition revue et corrigée le 15 février 2024"
- Promulgating law: loi n° 59-129 du 5 octobre 1959
- Language: fr; permission: official publication of the IORT, reproduced for
  non-commercial educational research
- Latest amendment referenced in the text: loi n° 2019-47 du 29 mai 2019
- Provenance: supplied as a file (SHA-256
  `353bca554ab5deaf229648485a271bc6fb65fa514b9785511d38f4e47393e7aa`, 1 527 869
  bytes, 193 pages). It is not downloadable from the pipeline; a build requires
  the file to be present in `data/raw/`.

## Known limitations carried into v2

1. **Version horizon**: the 2024 edition consolidates amendments to at least
   loi n° 2019-47 (29 mai 2019). Later amendments are not in this text. The JORT
   archive (`https://www.jort.tn/`) is where they would be verified; that
   reconciliation is not done.
2. **Per-article amendment provenance** is printed inline
   (`(Modifié par la loi n° ...)`, `(Ajouté par la loi n° ...)`). It is parsed
   into a structured field but not independently verified against the JORT.
3. **Arabic text is unavailable** at machine-readable quality. Arabic-language
   *questions* remain possible; the evidence text is French.
4. **Coverage is measured, not assumed**: the manifest reports how many
   articles were parsed, the article-number range, and every gap. A gap means
   the parser or the source page needs human review; it is reported, never
   silently dropped.
5. **Reproducibility of the raw file**: because the 2024 PDF is not fetched by
   the pipeline, a fresh clone can only rebuild the corpus if the file is
   supplied again; the recorded SHA-256 detects any substitution.

## Build pipeline

```text
data/raw/code-commerce-fr-iort-2024.pdf
        --(verify sha256)--> extract text --> normalize
        --> parse structure --> data/processed/corpus.jsonl
                                data/processed/manifest.json
```

1. **Resolve** — locate the raw file, verify size and SHA-256 against the source
   registry (no network: the source is supplied, not downloaded).
2. **Extract** — `pypdf` page-by-page text, keeping the PDF page number so every
   record can point back to its page.
3. **Normalize** — drop the running header (`Imprimerie Officielle de la
   République Tunisienne`) and page numbers, repair hyphenated line breaks,
   normalize whitespace and non-breaking spaces.
4. **Parse structure** — detect `Livre` / `Titre` / `Chapitre` / `Section`
   headings and article starts. The 2024 edition prints the body on the header
   line (`Article premier.- Le présent code ...`), so the parser splits the
   header, the optional amendment note and the inline body.
5. **Validate** — every record must carry a document id, an article number, a
   non-empty body (unless repealed) and a source pointer. Violations fail the
   build.
6. **Emit** — sorted, stable JSONL plus a manifest with counts, coverage, hash
   and limitations.

## Deliverables

- `data/processed/corpus.jsonl` — one article per line, stable ids
- `data/processed/manifest.json` — sources, hashes, counts, coverage, limitations
- `data/processed/LIMITATIONS.md` — human-readable version of the same
- `src/ingestion/` — the pipeline, runnable as one command
- `tests/` — parser, normalization and end-to-end tests against the real PDF
- `docs/PERSON_1_CORPUS.md` — updated with the real state and the handoff
- `docs/CORPUS_SCHEMA.md` — the record schema

## Verification

- The build is deterministic: two runs from the same raw PDF produce identical
  JSONL bytes.
- Unit tests cover heading detection, article splitting (including the inline
  header form), suffix and amendment parsing, normalization, and validation.
- A coverage report is printed by the build so a human can eyeball the gaps.

## Out of scope for v2

OCR, Arabic ingestion, post-2019 amendment reconciliation, related codes,
chunking, embeddings, and any evaluation data (Person 4).
