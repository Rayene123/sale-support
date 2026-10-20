# Project 2 — The Librarian

## Working title

**Tunisian Commerce RAG: a citation-based legal assistant for e-commerce**

The service will answer practical Tunisian commercial-law questions using a
verified corpus of the Tunisian Code of Commerce and approved related legal
texts. Answers must cite the relevant article and must abstain when the
corpus does not support an answer.

## Team roles

| Person | Main area | Can start independently? |
|---|---|---|
| 1 | Corpus and legal data | Yes |
| 2 | Chunking, indexing, and retrieval | Yes, with sample data or a local fixture |
| 3 | Generation, citations, and API | Yes, with a mocked retrieval response |
| 4 | Evaluation, metrics, and optimization | Yes |

People 2 and 3 should use temporary fixtures until Person 1 provides the
cleaned corpus. Their interfaces should be designed so the fixtures can be
replaced without changing the rest of the pipeline.

## Planned structure

Person 3's local French question interface and API are implemented. See
[local run instructions](docs/PERSON_3_SERVICE.md#local-implementation) for
Qwen3.5-9B setup, response format and tests.

```text
project 2/
├── README.md
├── design.md
├── optimisation.md
├── postmortem.md
├── data/
│   ├── raw/
│   ├── processed/
│   └── eval/
├── src/
│   ├── ingestion/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── api/
│   └── models/
├── eval/
├── scripts/
├── tests/
└── docs/
    ├── PERSON_1_CORPUS.md
    ├── CORPUS_SCHEMA.md
    ├── PERSON_2_RETRIEVAL.md
    ├── PERSON_3_SERVICE.md
    └── PERSON_4_EVALUATION.md
```

## Initial milestones

1. Week 5: approve and ingest the corpus; define interfaces.
2. Week 6: run the complete question-to-citation pipeline locally.
3. Week 7: deploy the working baseline and record measurements.
4. Week 8: reduce cost or p95 latency by at least 50%, with no more than
   two percentage points of accuracy loss.

## Scope rules

- Preserve article numbers and legal hierarchy in every chunk.
- Do not put API keys, personal data, or unverified legal text in the
  repository.
- Treat the service as an educational research tool, not legal advice.
- Record source URLs, language, publication/amendment information, and known
  OCR or version limitations.
