# Person 1 — Corpus and legal data

Status: **implemented** (v2, built from the 2024 IORT edition). Scope
decisions and the plan are in
[`PERSON_1_CORPUS_PLAN.md`](PERSON_1_CORPUS_PLAN.md); the record format is in
[`CORPUS_SCHEMA.md`](CORPUS_SCHEMA.md).

## Ownership

Build a reliable, reproducible corpus for the Tunisian e-commerce legal
assistant.

## Tasks

- Select the Tunisian Code of Commerce and any instructor-approved related
  legal texts.
- Record the source URL, title, language, date, and permission/status for
  every source.
- Download source files into `data/raw/` without committing restricted or
  personal data.
- Extract and clean text while preserving books, chapters, sections, and
  article numbers.
- Record OCR problems, missing pages, amendments, and version uncertainty.
- Export normalized documents to `data/processed/`.
- Define and document the metadata schema.

## What was delivered

One command builds the corpus from the hash-verified source PDF:

```sh
python "project 2/scripts/build_corpus.py" build        # uses the supplied PDF
python "project 2/scripts/build_corpus.py" build --no-download
python "project 2/scripts/build_corpus.py" verify --corpus "project 2/data/processed/corpus.jsonl"
```

The build writes `data/processed/corpus.jsonl`, `annotations.jsonl`,
`toc_inventory.json`, `manifest.json` and `LIMITATIONS.md`. The processed files
are committed; the raw PDF is git-ignored and, for this edition, must be
supplied by hand (see the local-only limitation below).

| Thing | Value |
|---|---|
| Corpus version | 2.0.0 |
| Article records | 584 (579 code + 5 promulgating law) |
| Code coverage | articles 1–746, 175 missing and all explained by repeal, 0 unexplained |
| Annotations | 20 (17 footnotes, 2 front matter, 1 unattached notice) |
| Warnings | 1 (article 465, a known source inconsistency) |
| `corpus.jsonl` SHA-256 | `1db08ef0312f1ce074f98ca20f6c3b1b2eb999927b09d79c003d7bd97be3df5d` |
| Tests | 111, all passing |

Two documents live in the one source PDF and are split into separate
`document_id`s so their articles cannot collide: `code-commerce-tn` (the code,
region `code`) and `loi-59-129-1959` (the promulgating law, articles 1–5,
region `law`). The printed table of contents is **not** a source of records; it
is read into `toc_inventory.json` and used only to prove that every missing
article number sits inside a range the edition marks `(abrogés)`.

The source of record is the **2024 IORT edition**
(`code-commerce-fr-iort-2024`, 193 pages, revised 2024-02-15). The earlier 2014
edition is the same legal text with an older amendment horizon; it is kept in
the registry as `superseded` and recorded in `manifest.json →
superseded_sources`, because ingesting both would duplicate every article
number.

## Handoff

- **Repeatable command** — `python "project 2/scripts/build_corpus.py" build`
  (see above). Rebuilds are byte-identical; run the tests with
  `python -m unittest discover -s "project 2/tests" -p "test_*.py"`.
- **Processed documents with stable IDs** — `data/processed/corpus.jsonl`, one
  article per line. IDs look like `code-commerce-tn:article-231-bis`; the format
  is defined in [`CORPUS_SCHEMA.md`](CORPUS_SCHEMA.md).
- **Source and metadata manifest** — `data/processed/manifest.json` (active and
  `superseded_sources`, SHA-256, edition, coverage, warnings,
  `reconciled_articles`, limitations, output digests) plus
  `src/ingestion/sources.py` for the source registry.
- **Record schema** — [`CORPUS_SCHEMA.md`](CORPUS_SCHEMA.md).
- **Unresolved legal-source limitations** — `data/processed/LIMITATIONS.md`,
  summarised below.

## Unresolved legal-source limitations

1. **Version horizon** — the source is the IORT edition revised 2024-02-15,
   consolidating the code as amended up to at least loi n° 2019-47 du 29 mai
   2019 (the latest amendment the text cites; it also carries 2016-36 and
   2016-71). Later amendments are absent; they would be verified against the
   JORT archive (`https://www.jort.tn/`), which is outside this deliverable.
   The edition's own cover note still cites loi n° 2010-39 and is stale.
2. **Local-only source** — the 2024 edition is not served at the publisher's
   public URL (that URL still returns the 2014 file), so the pipeline cannot
   download it. The raw PDF must be supplied in `data/raw/` and is verified
   against the recorded SHA-256. Because it is git-ignored, a fresh clone
   cannot rebuild without the file being provided again.
3. **Repealed wording is unavailable** — the published text prints only the
   repeal note, so the corpus records *that* an article is repealed, not what it
   used to say.
4. **Article 465 is inconsistent in the source** — the edition prints its
   header and an amendment note but no article text, while the table of contents
   marks it `(article 465 abrogé)`. It is recorded with `status: "repealed"` and
   empty text, keeping the printed note verbatim; the conflict is not resolved
   against the JORT.
5. **Amendment provenance is unverified** — inline notes such as
   `(Modifié par la loi n° 96-28 …)` are parsed and kept verbatim but not
   cross-checked against the JORT.
6. **Arabic text is unavailable** — the ministry's `CommerceArabe.pdf` has a
   broken `ToUnicode` map and extracts as glyph names, not Arabic. OCR is out
   of scope. Arabic *questions* are still possible; the evidence text is French.
7. **Related codes are not ingested** — the Code des droits réels and the
   société-related texts are recorded as `pending_instructor_approval` and are
   not in the corpus.
8. **Line breaks are not the printed ones** — article text is re-flowed
   (wrapped words rejoined, enumerated items kept on their own lines). Wording,
   punctuation and numbering are unchanged.

## Proposed metadata

The schema grew past the first sketch (it now also carries `status`,
`heading_path`, `amendment_notes`/`amendment_laws` and page pointers). The
sketch below is kept for history; [`CORPUS_SCHEMA.md`](CORPUS_SCHEMA.md) is the
authoritative description.

```json
{
  "document_id": "code-commerce-tn",
  "title": "Code de commerce tunisien",
  "language": "fr",
  "book": "Livre II",
  "section": "Des sociétés commerciales",
  "article": "Article 12",
  "article_number": 12,
  "source_url": "https://example.invalid/source",
  "source_date": "YYYY-MM-DD",
  "text": "..."
}
```

## Dependencies

This work does not require output from another person. People 2 and 3 may use
the committed `data/processed/corpus.jsonl` directly; it is ready to consume.
