# harness — the evaluation harness

`harness/` runs the customer-support system over the dataset, sends every reply to
the LLM judge, and writes structured, reproducible results plus metrics, cost, and
a readable report.

Standard library only. No agents, no retrieval, **exactly one system call per item**,
and one judge call per successful reply.

```powershell
cd "project 1"
python -m harness validate          # check the dataset, no model calls
python -m harness run               # the full evaluation
```

## Commands

| Command | What it does | Model calls |
| --- | --- | --- |
| `python -m harness validate` | Loads a dataset, reports invalid records, prints statistics, optionally lists prompt versions | none |
| `python -m harness run` | dataset → system → judge → metrics → cost → report | 1 per item, plus experiments |
| `python -m harness report --run DIR` | Rebuilds `metrics.json`, `cost.json`, `report.md` from saved rows | none |
| `python -m harness cost --run DIR` | Prints the cost analysis of a finished run | none |
| `python -m harness compare --run DIR ...` | Compares prompt versions across runs (and saved legacy runs with `--legacy`) | none |

Exit codes: `0` success, `1` the run recorded item failures, `2` a configuration
or dataset problem (nothing was run).

## Install

Nothing to install for the harness itself: Python 3.10+ and the standard library.
A model provider is needed for live runs.

```powershell
python --version                 # 3.10 or newer
ollama pull qwen2.5:14b          # local provider, no API key
```

Optional: a hosted provider. Then set the key **in the environment only**:

```powershell
$env:GROQ_API_KEY = "..."        # never written to disk or to results
```

## Configuration

Precedence, highest first: command-line option → environment variable → `harness/.env`
(local, git-ignored). Only the *name* of a key variable is ever recorded.

```powershell
Copy-Item harness/.env.example harness/.env
```

| Variable | Meaning | Default |
| --- | --- | --- |
| `SYSTEM_PROVIDER` | `ollama` or `openai` | `ollama` |
| `SYSTEM_MODEL` | model id | `qwen2.5:14b` |
| `SYSTEM_BASE_URL` | provider endpoint | provider default |
| `SYSTEM_API_KEY_ENV` | **name** of the variable holding the key | none |
| `SYSTEM_PROMPT_VERSION` | `prompts/system_v*.txt` | `v1` |
| `SYSTEM_MAX_TOKERS`, `SYSTEM_TIMEOUT` | request limits | `512`, `300` |
| `JUDGE_PROVIDER` | `ollama` or `groq` | `ollama` |
| `JUDGE_MODEL`, `JUDGE_PROMPT_VERSION` | judge model and `judge/prompts/*.txt` | `qwen3:14b`, `judge_v2` |
| `JUDGE_API_KEY` | judge key, read from the environment only | none |
| `SYSTEM_INPUT_PRICE_PER_M`, `SYSTEM_OUTPUT_PRICE_PER_M` | USD per million tokens | unset → cost `null` |
| `JUDGE_INPUT_PRICE_PER_M`, `JUDGE_OUTPUT_PRICE_PER_M` | USD per million tokens | unset → cost `null` |
| `HARNESS_LOCAL_COST_PER_HOUR` | optional local-compute assumption | unset → `null` |
| `HARNESS_RESULTS_ROOT` | default output root | `results/harness` |

A price or a token count that was not measured is reported as `null`, never as `0`.

## Run the evaluation

```powershell
# check configuration and provider readiness without spending a call
python -m harness run --preflight

# the full evaluation, 40 development items, prompt v3
python -m harness run --system-prompt v3 --run-id dev-v3 --output results/harness/dev-v3

# with the reliability experiments (extra judge calls, reported separately)
python -m harness run --system-prompt v3 --run-id dev-v3-bias `
    --verbosity-limit 10 --auto-pairs-from results/baseline_v1.jsonl `
    --position-limit 10 --position-repeats 2 --output results/harness/dev-v3-bias

# compare prompt versions
python -m harness compare --run results/harness/dev-v1 --run results/harness/dev-v2 `
    --run results/harness/dev-v3 --output results/harness/comparisons/prompt_versions
```

Useful flags: `--limit N`, `--split dev|test`, `--category NAME`, `--item-id ID`,
`--judge-limit N`, `--resume`, `--labels FILE`, `--labels-reviewed`,
`--skip-system`, `--skip-judge`, `--cost-multiplier N`.

### Resuming and overwriting

Rows are flushed as they are produced, so an interrupted run keeps its work:

```powershell
python -m harness run --run-id dev-v3 --output results/harness/dev-v3 --resume
```

`--resume` regrades only what is missing. Without `--resume` the harness **refuses**
to write into a non-empty output directory, and it does so before any model call.

### Replaying saved results (no model needed)

Both phases can reuse replies that already exist, which is how the committed
results in `results/harness/` were produced from Person 4's baselines and Person 3's
saved grades:

```powershell
python -m harness run --system-source results/baseline_v3.jsonl --system-prompt v3 `
    --judge-source results/judge-comparison-v2-20260929/v3/results.jsonl `
    --run-id dev-v3-replay --output results/harness/dev-v3-replay
```

A replay makes no model call, so it invents no latency: `wall_clock_seconds` is
`null` and the original run's measurements are labelled as such. Saved judge
grades are only accepted when their stored `response_text` matches the reply the
harness holds; a mismatch is recorded as a `dataset_error` instead of being
quietly attributed to this run. A replayed file whose `prompt_version` disagrees
with `--system-prompt` gets a `prompt_version_mismatch` warning on every row.

## What a run writes

```text
results/harness/<run_id>/
├── metadata.json    configuration, hashes, environment, completion status
├── system.jsonl     one row per item: reply, latency, tokens, warnings, error
├── judge.jsonl      one row per graded reply: scores, reason, latency, usage
├── items.jsonl      system + judge joined, exactly one row per evaluation item
├── errors.jsonl     every categorised failure, for later analysis
├── metrics.json     system, reliability, and performance metrics
├── cost.json        cost per item / per 1,000 requests, 100× projection
├── report.md        human-readable summary
├── position.jsonl   position-bias trials (only if that experiment ran)
├── verbosity.jsonl  verbosity-bias deltas (only if that experiment ran)
└── prompts/         the exact prompt texts this run used
```

`items.jsonl` is the structured result row for an item:

```json
{"item_id": "DEV-001", "status": "ok", "system": {…}, "judge": {…}}
```

`metadata.json` records the reproduction command, the SHA-256 of the dataset, the
prompt files, the code, and the environment, so a run can be traced to the exact
inputs that produced it. `python -m harness report --run DIR` rebuilds every
derived artefact from those rows, with no model call.

## Metrics

* **System** — average total /8, score distribution, per-criterion averages and
  points lost, per-category and per-difficulty breakdowns, failed items,
  coverage.
* **Reliability** — human-vs-human agreement, judge-vs-human agreement per
  evaluator, major disagreements, position-bias and verbosity-bias results.
* **Performance** — latency (mean/median/p95/min/max), wall clock, token usage
  per phase, throughput, and the extra calls spent on the bias experiments.

Conventions that keep the numbers honest:

* an experiment that did not run reports `null`, never `0`;
* a missing price or unmeasured token count is `null`, never `0`;
* a failed call is never averaged in as a good result — coverage is reported
  next to every average;
* kappa is printed next to raw agreement, because a skewed distribution can make
  a high agreement rate look worthless (and vice versa);
* scores are model-assigned unless the run passes `--labels-reviewed`, which
  asserts that the human labels were independently reviewed.

## Error handling

Every failure is one of the categories in `harness/errors.py`: `dataset_error`,
`missing_field`, `configuration`, `system_error`, `api_error`, `timeout`,
`network`, `model_missing`, `incomplete_output`, `refusal`, `judge_error`,
`invalid_judge_output`, `internal`. A failed item is a row, not a crash: the run
continues, `errors.jsonl` and `metrics.errors` record what happened, and the exit
code is `1`. Provider error bodies are never echoed, because they can contain
credentials. Nothing is retried, so a rate limit is visible as a rate limit.

## Bias experiments

Both are optional and are costed separately from the main phases.

* **Position bias** — grade the same pair of distinct replies in both orders and
  map the verdict back to the reply, so an order effect is measurable.
  `--position-pairs FILE` (reviewed) or `--auto-pairs-from FILE` (this run's
  replies against a saved run's), with `--position-limit` and `--position-repeats`.
* **Verbosity bias** — grade a padded copy of a reply and record the score change.
  The grade already produced in this run is reused, so this costs one extra judge
  call per item. `--verbosity-limit N`.

Both store their rows and their extra-call usage in the run directory, so
`report` can rebuild the same figures without a model.

## Tests

```powershell
python -m unittest discover -s harness/tests -t harness/tests
python -m unittest discover -s judge/tests -t judge/tests
```

The CLI tests mock the provider, so the whole pipeline — including a hosted
provider, a resumed run, and a failing provider — is exercised in about a second
without a model.

## Module map

| File | Responsibility |
| --- | --- |
| `cli.py` | commands, flags, phases, bias experiments |
| `config.py` | precedence, provider config, pricing, secret handling |
| `dataset.py` | JSONL loading, validation, statistics, labels, saved replies |
| `prompts.py` | versioned system prompts and their hashes |
| `providers.py` | Ollama / OpenAI-compatible adapters, preflight, error mapping |
| `system_runner.py` | one call per item, live and replay |
| `judge_runner.py` | wraps `judge.Judge`, live and replay, usage normalising |
| `metrics.py` | system / reliability / performance metrics, kappa, bias summaries |
| `cost.py` | per item, per 1,000 requests, 100× projection, `null` when unpriced |
| `report.py` | `report.md` |
| `compare.py` | prompt-version comparison across runs |
| `results.py` | run directory layout, streaming writers, metadata |
| `errors.py` | the error taxonomy |

Person 3's judge is used as a library (`judge.client.Judge`); the harness owns the
pipeline, the row schema, and the error taxonomy. See
`judge/HANDOFF_PERSON_2.md` for the integration contract and the known caveats in
the saved result files.
