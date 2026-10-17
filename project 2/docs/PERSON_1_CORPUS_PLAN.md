# Person 1 — Corpus implementation plan

Status: approved for implementation (scope decisions recorded below).
This plan is the working document for the Week 5 corpus milestone.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Corpus scope, v1 | French Code de Commerce, single document | Only text with a clean, verifiable text layer. |
| Source | Ministry of Justice PDF, `CommerceFr.pdf` | Official government publisher; reachable from this machine. |
| Arabic twin | Excluded from v1, kept in the manifest as a rejected source | Broken ToUnicode map: extraction yields glyph names (`/tehmarbutafinal/`), not Arabic text. OCR is out of scope for v1. |
| Related codes | Not ingested in v1 | README requires instructor approval before adding texts. List is recorded, not implemented. |
| Raw PDFs in git | Ignored; downloaded by the build command and verified by SHA-256 | Avoids committing binaries while keeping builds reproducible. |
| Processed corpus in git | Committed | People 2, 3 and 4 need the corpus without a network round trip. |
| Chunking | Not done here | Person 2 owns chunking. This layer emits article-level records. |

## Source of record

- URL: `https://www.justice.gov.tn/fileadmin/medias/references_juridiques/codes_juridiques/CommerceFr.pdf`
- Title: *Code de commerce* (République Tunisienne)
- Edition: Imprimerie Officielle, "Edition revue et corrigée le 15 février 2014",
  conforme à la dernière révision prévue par la loi n° 2010-39 du 26 juillet 2010
- Promulgating law: loi n° 59-129 du 5 octobre 1959
- Language: fr; permission: official publication of the Tunisian Ministry of
  Justice, reproduced for non-commercial educational research
- SHA-256 of the downloaded file is recorded in `data/processed/manifest.json`
  and re-checked on every build.

## Known limitations carried into v1

1. **Version horizon**: the text consolidates amendments up to loi n° 2010-39
   (edition date 2014-02-15). Amendments after that date are **not** in this
   text. The JORT archive (`https://www.jort.tn/`) is the place to verify them;
   that verification is not done in v1.
2. **Per-article amendment provenance** is present in the text as inline notes
   (`(Modifié par la loi n° ...)`, `(Ajouté par la loi n° ...)`). These are
   parsed into a structured field so the retrieval layer can reason about them,
   but they are not independently verified against the JORT.
3. **Arabic text is unavailable** at machine-readable quality (see above).
   Arabic-language *questions* remain possible; the evidence text is French.
4. **Coverage is measured, not assumed**: the manifest reports how many
   articles were parsed, the article-number range, and every gap. A gap means
   the parser or the source page needs human review; it is reported, never
   silently dropped.

## Build pipeline

```text
data/raw/*.pdf  --(verify sha256)-->  extract text  -->  normalize  -->  parse structure  -->  data/processed/corpus.jsonl
                                                                                              data/processed/manifest.json
```

1. **Download** — fetch into `data/raw/`, refuse to overwrite unless `--force`,
   verify SHA-256 against the source registry.
2. **Extract** — `pypdf` page-by-page text, keeping the PDF page number so every
   record can point back to its page.
3. **Normalize** — drop the running header (`Imprimerie Officielle de la
   République Tuinsienne`) and page numbers, repair hyphenated line breaks,
   normalize whitespace and non-breaking spaces.
4. **Parse structure** — detect `Livre` / `Titre` / `Chapitre` / `Section`
   headings and `Article N [suffix] [(amendment note)]` starts; split the
   document into one record per article with its heading path.
5. **Validate** — every record must carry a document id, an article number, a
   non-empty body and a source pointer. Violations fail the build.
6. **Emit** — sorted, stable JSONL plus a manifest with counts, coverage, hash
   and limitations.

## Deliverables

- `data/processed/corpus.jsonl` — one article per line, stable ids
- `data/processed/manifest.json` — sources, hashes, counts, coverage, limitations
- `data/processed/LIMITATIONS.md` — human-readable version of the same
- `src/ingestion/` — the pipeline, runnable as one command
- `tests/` — parser and normalization tests against a synthetic fixture
- `docs/PERSON_1_CORPUS.md` — updated with the real state and the handoff

## Verification

- The build is deterministic: two runs from the same raw PDF produce identical
  JSONL bytes.
- Unit tests cover heading detection, article splitting, suffix and amendment
  parsing, normalization, and record validation.
- A coverage report is printed by the build so a human can eyeball the gaps.

## Out of scope for v1

OCR, Arabic ingestion, post-2014 amendment reconciliation, related codes,
chunking, embeddings, and any evaluation data (Person 4).
