# Project 2 — The Librarian

Tunisian Commerce RAG is a citation-first research service over the French
2024 IORT edition of the Tunisian Code de commerce. It answers only from the
indexed corpus, cites the article and exact source passage, and abstains when
the retrieved evidence is insufficient. It is an educational research tool,
not legal advice and not a guarantee of current law.

## What is included

- 584 published/repealed article records (579 code articles and 5 promulgating
  law articles) from a 193-page source edition.
- 109 approved evaluation questions: 89 answerable and 20 unanswerable.
- Article-level indexing plus optional 220-word/40-word-overlap windows.
- BM25, multilingual vector, hybrid reciprocal-rank fusion, and deterministic
  reranking implementations.
- A FastAPI `/ask` endpoint and French browser interface.
- Separate retrieval, generation, citation, abstention, latency, and cost
  evaluation harnesses.
- A prepared target-user feedback protocol with French scenarios and an
  anonymized response schema; no participant data is fabricated.

The corpus is committed in processed form so the service runs without the
source PDF. The raw 2024 PDF is intentionally not committed; rebuilding it
requires the verified file described in [data/raw/README.md](data/raw/README.md).

## Quick start from a clean clone

From the repository root, use Python 3.11 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r "project 2/requirements-dev.txt"
```

For the default local provider, install Ollama and pull the configured model:

```powershell
ollama pull qwen3.5:9b
```

Start the service:

```powershell
$env:GENERATION_PROVIDER="ollama"
$env:OLLAMA_MODEL="qwen3.5:9b"
$env:ALLOW_PAID_CALLS="false"
.\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir "project 2/src" --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002`, or call:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/ask -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"Combien de temps conserver les livres de commerce ?"}'
```

The response contains `answer_fr`, `abstain`, `reason`, `citations`,
`timings_ms`, `usage`, resolved `retrieval_queries` and the actual runtime
`configuration`. Optional bounded conversation history resolves follow-up
questions; missing context produces a request for clarification.
No API key is required for the local Ollama mode. Paid requests are blocked
by default. The existing Groq adapter requires `GENERATION_PROVIDER=groq`,
`GROQ_API_KEY` and explicit `ALLOW_PAID_CALLS=true`; never commit the key.
See [Persona 3 service](docs/PERSON_3_SERVICE.md) for calibration, claim-review
exports and demo access protection.
OpenAI is also supported: set `GENERATION_PROVIDER=openai`, `OPENAI_API_KEY`,
`OPENAI_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=none` and explicit
`ALLOW_PAID_CALLS=true` in the ignored `project 2/.env`. Both rewriting and
generation then use OpenAI; retrieval and citation validation stay in the app.

When `project 2/.env` contains the Qdrant variables, the default API backend
loads chunks from Qdrant, runs BM25 locally over those payloads, and combines
it with Qdrant cosine-vector search. Set `RETRIEVAL_BACKEND=local` to force the
committed-corpus BM25 fallback. The current Qdrant collection is dense-only;
adding sparse BM25 vectors would require a separate collection migration.

## Build and evaluate

The processed corpus is already available. With the verified raw PDF, rebuild
it using:

```powershell
.\.venv\Scripts\python.exe "project 2/scripts/build_corpus.py" build --no-download
```

Build the optional semantic index:

```powershell
.\.venv\Scripts\python.exe "project 2/scripts/build_indexes.py"
```

To use Qdrant Cloud instead of the local NumPy index, set `QDRANT_URL` and
`QDRANT_API_KEY` in `.env`, then run
`python "project 2/scripts/upload_qdrant.py" --recreate`. See the
[Qdrant section](docs/PERSON_2_RETRIEVAL.md#qdrant-cloud-vector-index) for the
collection layout and the retrieval example.

Run retrieval ablations on the fixed evaluation set:

```powershell
.\.venv\Scripts\python.exe "project 2/eval/retrieval.py" `
  --questions "project 2/data/eval/questions.jsonl" `
  --method bm25 --output "project 2/data/eval/retrieval_bm25.json" --k 1 3 5 10
```

Use the same command with `--method vector`, `hybrid`, and
`hybrid-reranker` for the ablation. Generation evaluation requires the API
and a running model; see [PERSON_4_EVALUATION.md](docs/PERSON_4_EVALUATION.md).

Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s "project 2/tests" -p "test_*.py"
```

Export the requirements assessment as a PDF:

```powershell
.\.venv\Scripts\python.exe "project 2/scripts/export_assessment_pdf.py"
```

This writes `project 2/requirements_assessment.pdf`.

Export the unfinished Person 2, 3, and 4 task list:

```powershell
.\.venv\Scripts\python.exe "project 2/scripts/export_missing_tasks_pdf.py"
```

This writes `project 2/missing_tasks_persons_2_3_4.pdf`.

## Results and limitations

The fixed-set retrieval results are summarized in
[optimisation.md](optimisation.md) and the full table is in
[PERSON_4_EVALUATION.md](docs/PERSON_4_EVALUATION.md). At k=10, hybrid
retrieval reaches 87.08% macro recall versus 83.15% for BM25, but is slower.
The deterministic reranker did not improve k=10 coverage in this evaluation.

Generation results are deliberately reported with limitations: lexical F1 is
only a proxy, quote occurrence is not entailment, and the evaluation found
unsupported answers and false abstentions. No legal correctness claim is made.
No target-user session has been conducted yet; this is an explicit remaining
external task, not a result inferred from model scores.

The feedback collection package is documented in
[USER_FEEDBACK.md](docs/USER_FEEDBACK.md). It currently reports a sample size
of zero and contains no invented ratings or comments. A separate
`data/feedback/synthetic_responses.csv` fixture exists only to test reporting
code; its `TEST-` participants are not real users and must not be presented as
feedback evidence.

## Deployment

The Docker image includes the pinned MiniLM embedding model, runs without a
host model-cache mount, uses a non-root user, and checks `/health`. Run one
worker. It accepts the hosting platform's `PORT` variable (default `8000`).
Docker packaging, image building and local container execution are complete.
Public API exposure (step 4) is deferred.

Paid calls are disabled by default. With an OpenAI/Groq provider and
`ALLOW_PAID_CALLS=false`, `/ask` returns 503 before any rewrite, retrieval or
generation; `/health` reports this setting without calling the model. Do not
upload the professor's model key while calls are paused. Qdrant's key is separate.

See [Person 3 deployment instructions](docs/PERSON_3_SERVICE.md#credit-protection-and-deployment)
for local run commands, runtime settings and the frozen calibration. The
[Person 3 report](docs/PERSON_3_REPORT.md) summarizes implementation and measured
results. Final evaluation against a future public endpoint remains pending.

## Deliverables

- [design.md](design.md): corpus, chunking, indexing, retrieval, citations,
  and known failures.
- [optimisation.md](optimisation.md): fixed-set measurements and optimization
  gate.
- [postmortem.md](postmortem.md): failures, detection, and next iteration.
- [data/eval/questions.jsonl](data/eval/questions.jsonl): canonical evaluation
  questions with source evidence.
- [eval/retrieval.py](eval/retrieval.py) and
  [eval/generation.py](eval/generation.py): evaluation harnesses.

## Contributions

Person 1 — corpus provenance, PDF parsing, schema, and coverage reconciliation.

Person 2 — chunking, BM25/vector indexes, hybrid retrieval, and reranking.

Person 3 — generation prompt, citation validation, abstention behavior, API,
and browser interface.

Person 4 — evaluation dataset, retrieval ablation, generation metrics, cost
accounting, and optimization analysis.
