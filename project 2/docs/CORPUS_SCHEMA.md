# Corpus metadata schema

This document defines the record format written by the ingestion pipeline
(`project 2/src/ingestion`). It is the contract between Person 1 (corpus) and
People 2–4 (chunking, generation, evaluation). The schema itself is enforced in
code by `src/ingestion/schema.py`; a record that fails validation stops the
build.

## Files

| File | What it holds |
|---|---|
| `corpus.jsonl` | One article per line (UTF-8, `\n`-terminated, sorted). |
| `annotations.jsonl` | Editorial matter attached to no single article. |
| `toc_inventory.json` | Article ranges read from the printed table of contents (a reconciliation aid only). |
| `manifest.json` | Source provenance, counts, coverage, limitations, output hashes. |
| `LIMITATIONS.md` | Human-readable rendering of the limitation sections of the manifest. |

`corpus.jsonl` is **newline-delimited JSON**: split on `\n`, parse each line.
Field order in the file is alphabetical (`sort_keys=True`); do not rely on
order, read by key.

## Stable IDs

Every record has a `record_id` of the form:

```text
<document_id>:article-<number>[-<suffix>]
```

For example `code-commerce-tn:article-231-bis`. Rules:

- `<document_id>` is lower-case, hyphenated, chosen by the source registry and
  never reused for a different text.
- `<number>` is the printed article number as an integer (`premier` and `1er`
  are stored as `1`).
- `<suffix>` is present only for lettered variants: `bis`, `ter`, `quater`,
  `quinquies`, `sexies`, `septies`, `octies`, `nonies`, `decies`.

Because the promulgating law and the code print identically numbered articles
(1…5), they are separate `document_id`s, so no `record_id` ever collides.

## Article record fields

| Field | Type | Meaning |
|---|---|---|
| `record_id` | string | Stable unique id, see above. |
| `document_id` | string | Which document this article belongs to. |
| `title` | string | Human title of the document (e.g. "Code de commerce tunisien"). |
| `language` | string | BCP-47-ish code of the article text (`fr`). |
| `book` | string \| null | Chapter of the legal hierarchy, e.g. `"Livre III — DE LA LETTRE DE CHANGE, ..."`; `null` if outside a book. |
| `titre` | string \| null | Titre level label, same format. |
| `chapitre` | string \| null | Chapitre level label. |
| `section` | string \| null | Section level label. |
| `sous_section` | string \| null | Sous-section level label. |
| `heading_path` | string[] | The non-null heading levels above, in order (book → sous-section). |
| `article` | string | The printed article label, e.g. `"Article 231"` or `"Article premier"`. |
| `article_number` | integer | The article number (`>= 1`). |
| `article_suffix` | string \| null | `bis`/`ter`/… or `null` for a plain article. |
| `status` | string | `"published"` or `"repealed"` (see below). |
| `amendment_notes` | string[] | Inline amendment sentence(s), verbatim, e.g. `["(Modifié par la loi n° 96-28 du 3 avril 1996)"]`. Usually `[]` or one item. |
| `amendment_laws` | string[] | Law numbers extracted from the notes, normalised as `"96-28"` (year-number), sorted and de-duplicated. |
| `text` | string | Normalised article body. Empty only when `status` is `"repealed"`. |
| `char_count` | integer | `len(text)`; lets consumers budget context without re-measuring. |
| `source_url` | string | URL of the source PDF. |
| `source_sha256` | string | SHA-256 of the source PDF that produced this record. |
| `source_date` | string | Edition date of the source (`YYYY-MM-DD`). |
| `source_edition` | string | Full edition label (consolidated-through statement). |
| `pdf_page` | integer | 1-based page in the PDF where the article starts. |
| `printed_page` | integer \| null | Page number printed on that page (equals `pdf_page` here; kept separate so a mismatch is visible). |

### `status`: published vs repealed

The 2014 IORT consolidation does not reprint repealed articles. Where the code
used to print one, the edition prints only a repeal note, for example
`Article 6 (Abrogé par la loi n° 2010-39 du 26 juillet 2010).`

- `status: "published"` — a normal article; `text` is non-empty.
- `status: "repealed"` — the edition prints a repeal note and no body; `text`
  is `""` and the record is evidence that the article exists and is repealed,
  **not** article content.

This is why a repealed record is allowed to have empty text while every other
record must have at least 10 characters. Consumers should treat a repealed
record as a citation anchor ("article 6 is repealed") and never as
retrievable body text.

Missing article numbers inside a repealed range are not emitted as records at
all; there is no body to point at. The ranges themselves are recorded in
`manifest.json` and `toc_inventory.json`.

## Annotations

`annotations.jsonl` holds printed matter that belongs to no single article.
Each annotation has an `annotation_id`, a `record_type`, `document_id`,
`title`, `language`, `text` and a `note`. Record types:

| `record_type` | Meaning |
|---|---|
| `front_matter` | Text printed before the document's first article (for the law: the promulgation formula and visas). Id ends `:front-matter`. |
| `unattached_text` | Editorial text printed between articles that belongs to none, e.g. a notice that a whole titre is repealed. Id ends `:unattached-text`. |
| `footnote` | A page-bottom editorial note (rectificatif or cross-reference). Has `label` (e.g. `"(1)"`) and `pdf_page`. Id ends `:footnote-p<page>-<label>`. |

Footnotes are **not** merged into `text`, because they are editorial apparatus
and not part of the enacted article. They are kept so a reader can trace a
rectificatif. A footnote is attributed to the document whose text is actually
printed on its page.

## Determinism

The build writes no timestamps and sorts records by
`(document_id, article_number, suffix-order)`. Two builds from the same
hash-verified PDF produce byte-identical `corpus.jsonl`,
`annotations.jsonl` and `toc_inventory.json`; their SHA-256 digests are
recorded under `manifest.json → outputs`.

## Validation

`validate_record()` enforces the field rules above, including:

- `record_id` matches the stable-id pattern;
- `heading_path` equals the non-null heading fields, in order;
- `article_number >= 1`, `pdf_page >= 1`;
- `status` is one of the known values;
- `status == "repealed"` ⇒ empty text; otherwise `len(text) >= 10`;
- `char_count == len(text)`;
- `source_url` is `http(s)` and `source_sha256` is 64 lowercase hex chars;
- each `amendment_laws` entry matches `^[0-9]{2,4}-[0-9]{1,4}$`.

Any failure raises and aborts the build rather than emitting a partial corpus.
See `project 2/tests/test_schema.py` for the executable form of these rules.
