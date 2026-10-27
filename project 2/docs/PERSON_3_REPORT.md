# Person 3 — French answer generation and local Docker delivery

Status: implementation and local Docker execution completed, 27 October 2026.
Public API exposure (step 4) is deferred. Local paid model calls have been
re-enabled with the existing $0.50 spending limit and its preserved ledger;
the repository default remains disabled.

## Implemented

- French, evidence-only generation with local Ollama/Qwen3.5-9B and an optional
  OpenAI provider using strict structured output.
- Question preparation for short queries, contextual follow-ups and multi-part
  questions, preserving the original question in the generation prompt.
- Integration with Qdrant hybrid retrieval: local multilingual MiniLM embeddings,
  Qdrant vector search, local BM25 and reciprocal-rank fusion.
- Validation of returned chunk IDs and verbatim quotations, followed by trusted
  article, page and source metadata supplied by the application.
- Abstention for missing evidence or invalid model output; bounded requests,
  concurrency control, safe errors, latency and token accounting.
- `POST /ask`, `GET /health`, a French browser interface and optional project
  authentication.
- Paid-call opt-in and an optional persistent, transactional spending limit.

For example, a question about keeping commercial books retrieves the relevant
article, supplies it to the generator, and returns a French answer with a
numbered quotation, article identifier, PDF page and source URL. The application
checks the quotation against the actual retrieved text before returning it.

## Calibration and reference evaluation

A separate 24-question development set compared threshold zero with a candidate
retrieval cutoff. The candidate increased false abstentions from 2/12 to 4/12
without reducing unanswerable questions answered. Threshold zero was retained
and frozen before the reference evaluation. Its backend, corpus and actual
index fingerprints are stored in `config/person3-calibration.json` and verified
at startup when that configuration is selected.

The unchanged evaluation set was previously run against a temporary endpoint
using GPT-6 Luna, reasoning effort `none`, and Qdrant hybrid retrieval on
27 October 2026. These results describe that reference run; final evaluation
against a future public service remains pending.

| Measurement | Reference result |
| --- | --- |
| Questions completed / HTTP errors | 109 / 0 |
| Answerable questions answered | 75 / 89 |
| False abstentions on answerable questions | 14 / 89 |
| Unanswerable questions refused | 20 / 20 |
| Returned quotations found in corpus | 148 / 148 |
| Mean gold-article citation precision / recall | 70.13% / 75.84% |
| Server median / p95 latency | 3.47 s / 8.20 s |
| Input / output tokens | 324,614 / 15,574 |

Quotation matching and gold-article agreement measure traceability; they do
not establish legal correctness. The corpus is a fixed 2024 edition.

## Docker verification

The Dockerfile bundles the pinned MiniLM embedding model, runs as a non-root
user and probes `/health`. The image was built and the container was run on
`127.0.0.1:8002` without a host model-cache mount. Initial verification omitted
the model API key and paused generation. Model access was then re-enabled using
private runtime settings and a persistent budget mount, without a paid test call.

Verified: startup and restart, health/configuration, Qdrant/index fingerprints,
authentication, input validation and the paid-call pause. When paused, `/ask`
returns HTTP 503 before rewriting, retrieval or generation. Automated tests:
238 passed, 26 skipped because the raw source PDF is not present.

## Handoff

See [service instructions](PERSON_3_SERVICE.md) for native and Docker commands,
environment settings and API behavior. The fixed evaluation set was not changed.
Pixel-art work, secrets, private access details and local review worksheets are
excluded from this delivery. Public exposure and final evaluation against that
future public endpoint remain deferred.
