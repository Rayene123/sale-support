# Person 1 — Corpus and legal data

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

## Proposed metadata

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

This work does not require output from another person. People 2 and 3 may
start with a small local fixture while this work is in progress.

## Handoff

Provide:

- A repeatable ingestion/cleaning command
- Processed documents with stable IDs
- Source and metadata manifest
- A short list of unresolved legal-source limitations
