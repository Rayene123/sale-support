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
.\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir "project 2/src" --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002`, or call:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/ask -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"Combien de temps conserver les livres de commerce ?"}'
```

The response contains `answer_fr`, `abstain`, `reason`, `citations`,
`timings_ms`, and `usage`. No API key is required for the local Ollama mode.
For a hosted provider, set `GENERATION_PROVIDER=groq` and
`GROQ_API_KEY`; never commit the key.

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

## Deployment

The application is deployable as a single web process. The local default
requires Ollama on the same host. A hosted deployment should use the Groq
provider (or a private Ollama host), set `GENERATION_PROVIDER`, `GROQ_API_KEY`,
and `OLLAMA_MODEL`/`GROQ_MODEL` as appropriate, and expose only `/`, `/ask`,
`/health`, and `/docs`. The repository does not claim a public URL because no
hosting account or secret was supplied in this workspace.

Before publishing a URL, run the fixed generation evaluation against the
deployed endpoint and record the URL, model, configuration, and timestamp in
the evaluation report.

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
