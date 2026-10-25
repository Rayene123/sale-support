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
It returns `answer_fr`, `abstain`, `citations`, `reason`, `model`, `timings_ms`
and `usage`. Each answer point is numbered `[1]`, `[2]`, etc., corresponding to
its citation, which includes the point text, chunk/record IDs, article, exact
quote, PDF page and publisher URL. URLs come from the corpus; a publisher
landing page is not a direct link to the locally supplied 2024 PDF.

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
