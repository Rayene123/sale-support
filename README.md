# Sale Support

This repository contains a FastAPI product-search application and a separate CS496 Project 0 sentiment benchmark. The benchmark classifies 75 short texts as `positive`, `negative`, `neutral`, or `mixed`. It does not use the product database or the earlier SQL evaluation questions.

## Setup

Use Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -r requirements.txt -r benchmark/requirements.txt
```

An isolated virtual environment is recommended. Copy `.env.example` to `.env` if you want file-based settings; existing OS environment variables take precedence. Never commit `.env` or actual API keys. The benchmark itself uses standard-library HTTP; Ollama/OpenAI Python SDK packages are not required.

## Run a local model

Install and start Ollama, then download the model you intend to test (for example, `ollama pull qwen2.5:14b`). Model installation is separate from this repository's Python setup.

```powershell
python benchmark/src/run.py --provider ollama --model qwen2.5:14b --results-dir benchmark/results/my-local-run
python benchmark/src/score.py --results-dir benchmark/results/my-local-run
```

The default Ollama endpoint is `http://localhost:11434`. Set `--base-url` for another local or remote Ollama server. Each results directory can hold multiple different models. Use a new directory for a repeat run of the same model; raw results are never overwritten automatically.

## Run a hosted API

Set the provider's key in your environment or untracked `.env` first. Commands below reference variable names, not literal secrets.

```powershell
python benchmark/src/run.py --provider groq --model openai/gpt-oss-20b --results-dir benchmark/results/my-api-run
python benchmark/src/score.py --results-dir benchmark/results/my-api-run
```

Groq uses `GROQ_API_KEY`. OpenAI uses `OPENAI_API_KEY` and defaults to the Responses API. A model that requires reasoning and does not accept temperature can be configured explicitly:

```powershell
python benchmark/src/run.py --provider openai --model gpt-6-astra --temperature omit --reasoning-effort low --max-tokens 256 --results-dir benchmark/results/my-astra-api-run
```

The 256-token budget includes reasoning where the API counts it that way; a truncated response is wrong. If a pilot indicates this budget is inadequate, agree on a new shared budget before running all models. Omitting temperature is a recorded deviation from the assignment's temperature-0 setup and must be disclosed. Provider availability, permissions, billing and accepted parameters depend on your account and model. The code never silently changes settings or retries failed requests.

## OpenAI-compatible servers and other providers

Use `compatible` for an endpoint implementing Chat Completions, including appropriately configured LM Studio, vLLM, or hosted compatible services:

```powershell
python benchmark/src/run.py --provider compatible --model YOUR_SERVED_MODEL --base-url http://localhost:1234/v1 --results-dir benchmark/results/my-server-run
```

For an authenticated compatible endpoint, append `--api-key-env MY_API_KEY` after setting that environment variable. For a Responses-compatible endpoint, add `--api-format responses`. Pass the base URL, including `/v1` when your server requires it, without the final `/chat/completions`, `/responses`, or `/api/chat` route.

Supported wire formats are Ollama chat, OpenAI Chat Completions and OpenAI Responses. This is not automatic support for every vendor's native API: a service with a different protocol needs an adapter or compatible gateway. The task remains four-label sentiment classification; another task needs its own prompt and scoring rule.

## Configuration

| Option | Meaning / default |
| --- | --- |
| `--provider` | `ollama`, `groq`, `openai`, `compatible`; repeat to run several presets sequentially |
| `--model` | Model ID; required for OpenAI/compatible unless supplied in the environment |
| `--base-url` | Override the preset endpoint |
| `--api-format` | `ollama`, `chat`, or `responses` |
| `--api-key-env` | Environment variable name holding the key; local compatible servers need no key by default |
| `--temperature` | `0`; use `omit` only when needed and document the difference |
| `--max-tokens` | `256`; mapped to the appropriate API output-limit field |
| `--token-parameter` | Chat API only: `max_tokens` or `max_completion_tokens` |
| `--reasoning-effort` | Optional; passed only when explicitly configured for chat/responses |
| `--timeout` | `120` seconds for the HTTP connection/socket operations; not a strict total wall-clock deadline |
| `--items` | Defaults to `benchmark/Data/items.jsonl`; accepts JSONL or a JSON array |
| `--results-dir` | Defaults to `benchmark/results`; prefer a named subdirectory for new runs |

Without `--provider`, `PROVIDERS` is read from the environment (default `ollama`). Per-provider settings use `OLLAMA_MODEL`, `GROQ_MODEL`, `OPENAI_MODEL`, or `COMPATIBLE_MODEL`, plus the corresponding `_BASE_URL` and `_API_FORMAT` variables. `OLLAMA_URL` is also supported. Explicit CLI settings win. Shared CLI model/endpoint/key overrides require a single provider; use separate invocations for different model-specific settings.

Each dataset record requires a unique nonempty string `id`, a nonempty `text`, and one of the four exact reference labels in `label`. References are saved for scoring but never included in API model inputs. Every request uses `benchmark/src/prompt.py` and a fresh system/user message pair, with no conversation history.

## Results and scoring

Each run writes:

- `per_item_<provider>_<model>.csv`: text, reference, raw generated answer, latency, usage, response model ID, finish reason and failure category.
- A matching `.raw.jsonl`: original successful HTTP response bodies, including provider usage details.
- A matching `.meta.json`: timestamp, configuration, dataset/prompt hashes and run completion status. It stores only the API-key variable name, never its value. Hardware must still be recorded separately by the person running the model.

CSV and raw rows are flushed after every item. If interrupted, recorded rows remain available; there is no automatic resume. The scorer validates IDs, texts and references against the selected dataset and counts missing rows as wrong using the full dataset denominator. A completely empty result file is rejected. Scoring writes `summary.csv` without modifying raw per-item files. Use `--output PATH` for an alternative summary destination. Discovery is limited to the selected directory so archived/copied runs in subfolders are not double-counted.

The scorer accepts only whitespace-trimmed, case-normalized exact labels. It reports parse errors, execution errors, structured refusals, timeouts and truncations separately; all are wrong. Providers that express a refusal only in ordinary prose cannot be reliably distinguished from other invalid text and receive a parse error. p50/p95 use linear interpolation over all recorded request latencies, including failures. Missing token usage remains blank, with partial recorded totals available separately. Ollama decoding tokens/second is stored when `eval_count` and `eval_duration` are returned.

Imported chat answers are supported for supplementary analysis:

```powershell
python benchmark/src/run.py --import-chat benchmark/chat_answers_astra.json --model gpt-6-astra --results-dir benchmark/results/import-example
python benchmark/src/score.py --results-dir benchmark/results/import-example
```

The import JSON must contain an `answers` object mapping every dataset ID to an output string. Imports are marked `chat_nonblind`; they have no invented API timing or token usage and cannot replace independent API calls in the assignment.

## Recorded results

| Model | Correct | Accuracy | p50 / p95 (ms) | Evidence |
| --- | --- | --- | --- | --- |
| Qwen2.5 14B / Ollama | 72/75 | 96.00% | 943.8 / 1066.5 | Recorded model run |
| GPT-OSS 20B / Groq | 69/75 | 92.00% | 2401.9 / 2659.2 | Recorded API run |
| TinyLlama 1.1B / Ollama | 0/75 | 0.00% | 557.7 / 1586.5 | All 75 outputs invalid under the exact-label rule |
| GPT-6 Astra / chat | 73/75 | 97.33% | N/A | Non-blind supplementary answers; labels were visible |

These describe the current repository snapshot, not automatic measurements of every future run. The report's Astra result is not a controlled ranking against the measured models. Hardware, historical run dates, independent dual label review and a blind flagship API run remain missing from the recorded evidence.

Artifacts: [report.pdf](benchmark/report.pdf), [postmortem.md](benchmark/postmortem.md), [summary.csv](benchmark/results/summary.csv), and [combined_per_item.csv](benchmark/results/combined_per_item.csv). The PDF and combined CSV are a snapshot; new runs do not update them automatically. `benchmark/build_report.py` rebuilds the original four-model report snapshot and assumes the original data and filenames, so it is not the general-purpose scorer for arbitrary new runs.

For API cost, `benchmark/src/cost.py` reads the top-level summary and environment rates such as `GROQ_INPUT_PRICE_PER_M` / `GROQ_OUTPUT_PRICE_PER_M` (USD per million tokens). Verify current prices before use. It does not account for every provider's caching/tier rules or hardware and labor. Local cost and break-even need separately recorded hardware, electricity, capacity and labor assumptions.

## Verification

```powershell
python -m unittest discover -s benchmark/src -p "test_*.py" -v
```

Tests cover request schemas, unchanged prompts, provider output parsing, missing usage, failures, checkpoint files, overwrite protection, dataset validation, partial runs and scoring. Mock/local tests do not establish paid API access or availability of any installed local model.

## Product-search application

Set `DATABASE_URL` and `GROQ_API_KEY` in `.env` for the separate application, then run:

```powershell
python -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the FastAPI request schemas. The application exposes product-search routes such as `/agent`, `/agent-guarded` and `/agent-raw`. Its setup and database requirements are independent of sentiment benchmarking.

## Contributions

The team must confirm names and individual responsibilities before submission. Repository contributors observed on GitHub are listed below; no unverified work attribution is assigned.

| Contributor | Contribution record |
| --- | --- |
| Rayene123 | Setup enviroment and tested the tiny llama model assisted in documentation|
| notSelimm | Tested the qwen 14b model and created the dataset assisted in documentation|
| oussama44444 | Tested the groq model and assisted in creating the dataset assisted in documentation|
| OmarAbid1 | Rupdate runner/scorer and assisted in documentation|

AI assistance was used for the runner/scorer adaptation, verification tests, report assembly and supplementary chat answers. Team members remain responsible for reviewing the implementation and explaining their submitted work.
