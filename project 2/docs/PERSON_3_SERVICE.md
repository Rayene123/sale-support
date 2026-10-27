# Person 3 — Generation, citations, and API

## Ownership

Build the question-to-answer service and enforce grounded, article-level
citations.

## Tasks

- Define the request and response schemas.
- Implement the answer-generation prompt.
- Pass only retrieved passages to the generator.
- Require a citation for every legal claim.
- Implement explicit abstention when evidence is missing.
- Validate citations against returned chunk IDs and article metadata.
- Build the API and a minimal question interface.
- Record request, retrieval, generation, and end-to-end latency.
- Add tests for unsupported questions and fabricated citations.

## Dependencies

This work can start without another person's output by mocking retrieval
results with the agreed schema. It will need Person 2's retrieval interface
for end-to-end integration and Person 1's real article metadata for final
citation checks.

## Handoff

Provide:

- Local run command
- API endpoint and response example
- Prompt and model configuration
- Citation-validation behavior
- Abstention behavior
- API and citation tests

## Local implementation

From the repository root (Python 3.11+, Ollama running):

```powershell
python -m pip install -r "project 2/requirements.txt"
ollama pull qwen3.5:9b
python -m uvicorn api.app:app --app-dir "project 2/src" --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002` for the French interface, or `/docs` for the API.
`POST /ask` accepts `{"question":"Combien de temps conserver les livres de commerce ?"}`.
Optional `history` holds up to four `{role: "user"|"assistant", content: "..."}`
turns, each at most 2000 characters and 6000 characters combined. The browser
keeps this context only in memory and offers a new-conversation button.
It returns `answer_fr`, `abstain`, `citations`, `reason`, `model`, `timings_ms`
and `usage`. Each answer point is numbered `[1]`, `[2]`, etc., corresponding to
its citation, which includes the point text, chunk/record IDs, article, exact
quote, PDF page and publisher URL. URLs come from the corpus; a publisher
landing page is not a direct link to the locally supplied 2024 PDF.

The response also includes `retrieval_queries` and a non-secret `configuration`
snapshot: actual backend/method/model, score threshold, prompt/corpus/source
hashes and revision. These hashes are captured by the running server at startup.
`/health` exposes the same snapshot without making an inference request.

## Question preparation

Clear standalone questions follow the direct search path. The short books
retention phrase has a deterministic expansion. Vague follow-ups without
context return `reason="clarification"`, without retrieval or generation.
Contextual follow-ups and multi-part questions can make one bounded rewrite
call (OpenAI when selected, otherwise local Ollama; 20-second timeout, at most
three queries). Numbers and
explicit negation/exception words are checked; intent preservation still needs
human evaluation. A failed ambiguous rewrite requests clarification. A failed
standalone multi-part rewrite retains the original question.

Search results are merged round-robin and deduplicated, retaining at most ten
chunks. Original user wording and resolved search queries remain distinct in
the generation prompt. `QUESTION_REWRITING=false` provides the direct baseline.
Rewrite time and token usage are recorded separately and included in totals.

## Development calibration

`data/eval/person3_dev.jsonl` is a separate, authored 24-case development
fixture (12 answerable, 12 unanswerable), not expert-approved legal evaluation.
The calibration command rejects exact overlap with the canonical question set:

```powershell
python "project 2/eval/calibrate.py" --backend local --output calibration-local.json
```

Use `--backend qdrant` with the actual configured collection for production
hybrid calibration. The candidate search minimizes unanswerable admission
while keeping at least 90% answerable admission on this small development set.
This measures a retrieval gate, not generated-answer correctness. Validate the
selected rule on development generation before freezing the final evaluation.
BM25, cosine and RRF scales are not interchangeable confidence probabilities.

Set `CALIBRATION_FILE` to the saved file to apply its threshold. Startup rejects
backend/method/corpus/index-payload mismatches or invalid thresholds. The index
fingerprint covers the actual loaded chunks, including Qdrant payloads; the
separate corpus fingerprint describes the committed source file. A fully filtered result
returns `reason="below_threshold"` without a generation call. Without a file,
`MIN_RETRIEVAL_SCORE` remains available and defaults to zero (uncalibrated).

## Semantic support review

The existing evaluation harness exports exact generated claims and full cited
articles for human support review:

```powershell
python "project 2/eval/generation.py" --api-url http://127.0.0.1:8002 --output run.json --review-export claims.jsonl
python "project 2/eval/generation.py" --score-existing run.json --reviews reviewed-claims.jsonl --output reviewed-run.json
```

Review labels are `supported`, `partially_supported`, `unsupported`, or `unclear`;
a reviewer identifier, reason and exact claim fingerprint are required. Blank
exported labels are pending, never automatic approvals. Different reviewers
may label one claim; disagreements stay unclear rather than being silently
resolved. Reports show reviewed/unreviewed counts, disagreement and strict
support rate. Rescoring makes no API calls and checks question/corpus hashes.
Semantic support and independent legal correctness remain separate judgments.

## Credit protection and deployment

OpenAI is available with `GENERATION_PROVIDER=openai`, `OPENAI_API_KEY`,
`OPENAI_MODEL=gpt-6-luna` and explicit `ALLOW_PAID_CALLS=true` in the ignored
`project 2/.env`. It uses the Responses API with strict structured output,
`store=false`, `OPENAI_REASONING_EFFORT=none`, a 640-token generation limit
and the same local citation validator. Contextual rewriting uses that provider
with a 256-token limit and a 20-second timeout; it does not require Ollama.
Incomplete/refused/malformed output fails closed. Provider errors expose only
safe status messages, with no automatic retries or paid fallback.

The default provider remains Ollama. API credentials and Qdrant credentials
are separate. A successful `/models` listing does not prove inference permission,
remaining credit or previous usage. Output limits bound response size; they
are not an account-wide dollar cap. Track actual token usage and consult the
professor's account dashboard for the shared balance. Model prices and access
must be checked before a larger evaluation.

For a bounded GPT-6 Luna run, configure both `OPENAI_BUDGET_FILE` (a persistent
SQLite path) and `OPENAI_BUDGET_USD`. The service reserves a conservative cost
before sending each request; concurrent processes share that ledger. Known usage
settles at the cache-write input ceiling and standard output rate; failed or
unmeasured calls keep their reservation. Exhaustion or invalid accounting blocks
the call. This guards calls using this ledger, not other teammates or services
using the same account. The guard currently rejects other models rather than
guessing their prices. Prices must be refreshed if the provider changes them.

Paid Groq requests are blocked unless `ALLOW_PAID_CALLS=true`, even when a key
exists. There is no automatic paid fallback. Identify a provider only after its
credentials and endpoint have been verified; never send a key to a guessed
third-party gateway.
Before enabling paid calls, agree on the provider and a run allowance; the flag
alone is not a dollar spending cap. Groq uses `GROQ_API_KEY`. OpenAI uses
`OPENAI_API_KEY`; neither key belongs in source control. The optional OpenAI
SQLite ledger limits calls made through that ledger, not other applications
using the same account. Existing automated provider tests use mocked HTTP.

An optional `DEMO_PASSWORD` protects the interface, `/ask` and API docs with
HTTP Basic authentication (username `librarian`); `/health` remains a free
liveness/configuration endpoint. Use HTTPS for an external demo. Keep the
provider key and Ollama private. Retrieval outages return a recoverable 503;
malformed retrieval payloads return 502 rather than an unsupported-answer claim.

Docker preparation stops at step 3: build the image and run the container
locally. Step 4, exposing the API publicly, is deferred.

Build from the repository root:

```powershell
docker build -t librarian-project2:latest "project 2"
docker run -d --name librarian-project2 --restart unless-stopped --memory=2g --cpus=2 --env-file "path/to/project2-docker.env" -p 127.0.0.1:8002:8000 librarian-project2:latest
```

The image installs CPU-only PyTorch and bundles MiniLM at revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Build-time public model downloads
do not use the professor's API key. Runtime embedding loading is offline and
does not need a PC cache mount. The image runs as UID 10001, responds on
`0.0.0.0:${PORT:-8000}`, handles container stop signals directly, and probes
`/health`. Run one API worker. Open `http://127.0.0.1:8002/` after startup.
The port binding is local; these commands do not create a public URL or upload
the image to a registry. `APP_REVISION` may be supplied as a build argument;
the health response also fingerprints the actual Python source files.

Keep source and corpus private under the existing course permission. A Docker
Hub upload is not required for local execution.

Create the runtime file outside Git using unquoted `KEY=value` lines.
Do not pass a dotenv file containing quoted values directly to Docker's
`--env-file`. The current paused Qdrant configuration uses:

| Variable | Runtime value |
| --- | --- |
| `GENERATION_PROVIDER` | `openai` (generation remains paused) |
| `OPENAI_MODEL` | `gpt-6-luna` |
| `OPENAI_REASONING_EFFORT` | `none` |
| `ALLOW_PAID_CALLS` | `false` |
| `RETRIEVAL_BACKEND` | `qdrant` |
| `QDRANT_URL` | Existing cluster's HTTPS URL |
| `QDRANT_COLLECTION` | `librarian-chunks` |
| `QDRANT_API_KEY` | Qdrant secret, never the model key |
| `CALIBRATION_FILE` | `/app/config/person3-calibration.json` |
| `DEMO_PASSWORD` | Strong course-access secret; username `librarian` |

`DEMO_PASSWORD` is the existing setting name for HTTP Basic authentication;
it protects the browser, `/ask` and API docs. `/health` is public. Use HTTPS.
Omit `OPENAI_API_KEY` while paid requests are paused. `/ask` returns
503 immediately without rewriting, retrieval or provider calls in this mode;
`/health.paid_calls_allowed` is false. This explicitly pauses answers instead
of pretending that a running API means its generation backend is available.

The bundled calibration is the previously selected, development-validated
threshold zero. Startup verifies its corpus and actual Qdrant payload hashes.
Do not silently recalibrate when a deployment encounters a mismatch.

Before enabling paid calls later, obtain an explicit run allowance, mount
persistent storage at `/state` writable by UID 10001, and set
`OPENAI_BUDGET_FILE=/state/budget.sqlite` with `OPENAI_BUDGET_USD`. Preserve the
ledger across restarts and redeployments; an ephemeral file resets protection.
Keep previously recorded spending when reusing an existing allowance.

Local checks while paid calls are paused: `/health`, startup fingerprints,
authentication, interface, invalid-input 422 and paused `/ask` 503. A successful
health check does not verify generation. Public endpoint verification and final
generation evaluation remain deferred with step 4; they are not prerequisites
for building and running the local container.

Example response, abbreviated to the answer and one citation:

```json
{"answer_fr":"Les livres de commerce doivent être conservés pendant dix ans. [1]",
 "abstain":false,"citations":[{"chunk_id":"code-commerce-tn:article-10:chunk-0",
 "article":"Article 10","pdf_page":9,"quote":"Ils seront conservés pendant dix ans."}]}
```

With `RETRIEVAL_BACKEND=qdrant`, the application loads chunk payloads from the
configured Qdrant collection once at startup. BM25 is built over those Qdrant
payloads, while the semantic leg queries the collection's 384-dimensional
cosine vectors; the API therefore uses Qdrant-backed hybrid retrieval. The
current collection is dense-only, so BM25 scoring is computed locally over the
text loaded from Qdrant rather than pretending that a dense vector is BM25.
Without Qdrant configuration, the committed corpus and local BM25 fallback are
used. No raw PDF, embedding rebuild, or generation API key is needed in local
Ollama mode. Set `MIN_RETRIEVAL_SCORE` to
a positive value calibrated on a development split to reject weak lexical
matches before generation. The default is `0`, preserving the measured
baseline until a threshold is selected without test-set leakage.
`/health` reports application liveness and the configured model; it does not
check Ollama readiness.

The default is `qwen3.5:9b`, thinking disabled, temperature 0, seed 101,
8192-token context and 640-token output limit. `OLLAMA_MODEL` and `OLLAMA_URL`
can be set before startup; the default Ollama address is `http://127.0.0.1:11434`.
Up to ten retrieved passages are sent, limited to 6000 characters per
passage and 12000 total. Citation checks use the actual supplied text, including
any clipping. Quotes allow whitespace differences only; words, accents and case
are not repaired. Article/page metadata is supplied by the server, never the model.

Missing evidence or invalid/truncated generation produces an abstention with
no citations. An absent model/Ollama gives HTTP 503; timeout (90 seconds) gives
504; unreadable provider JSON gives 502. One question runs at a time; a concurrent
request receives 429 with `Retry-After`. The interface displays these errors and
allows retry. Run a single server worker for this local GPU baseline.

The server logs timings, model, token counts and outcome without question text.
`timings_ms.total` measures retrieval through validation inside the server;
network/browser latency is not included. Generation time includes cold model
loading when applicable. Citation identity and quotation checks do not prove
semantic support: choosing the correct legal procedure still requires evaluation.
The ten-result baseline includes article 10 for the short books-retention
question where the five-result keyword baseline missed it; a regression test
checks this retrieval-to-generation handoff.

Tests run without Ollama or downloading models:

```powershell
python -m pip install -r "project 2/requirements-dev.txt"
python -m unittest discover -s "project 2/tests" -p "test_*.py"
```
