# Person 2 — Evaluation Harness: implementation report

Role: **Evaluation Harness Lead**. Requirement source: `docs/PERSON_2_HARNESS.md`.
Code: `harness/` (standard library only, ~2,300 lines including tests).
Usage: `harness/README.md`.

---

## 1. Summary of what was built

```text
python -m harness validate   # dataset check, statistics, no model calls
python -m harness run        # the whole evaluation, one command
python -m harness report     # rebuild every derived artefact, no model calls
python -m harness cost       # print the cost analysis of a run
python -m harness compare    # compare prompt versions
```

`run` is the single command the specification asks for. It loads and validates
the dataset, calls the evaluated system once per item, sends every successful
reply to Person 3's judge, runs the optional bias experiments, and writes
`system.jsonl`, `judge.jsonl`, `items.jsonl`, `errors.jsonl`, `metrics.json`,
`cost.json`, `report.md`, `prompts/`, and `metadata.json` into
`results/harness/<run_id>/`.

The pipeline is exactly the specified one — dataset → system → answer → judge →
structured result → metrics — with no agents, no retrieval, and one system model
call per item. That is asserted in the tests: a full run of a one-item dataset
performs four HTTP requests (two provider tag probes, one system call, one judge
call).

## 2. Requirement-by-requirement

### 2. Dataset loader (§2)

`harness/dataset.py`. Reads JSONL as UTF-8 or UTF-16 (Person 4's files are
UTF-16) and returns **errors instead of exceptions** for malformed lines, so a
damaged file is described rather than crashed on. `validate_item` checks every
required field and its type: `id`, `customer_message`, `order_context`, plus
`order_number`/`status`/`items` and each line item's `product_name`/`quantity`/
`line_total`. Duplicate ids are rejected. Invalid records are never silently
dropped: they become `RecordError`s with file, line number, and item id, and by
default they **stop the run** (`--allow-invalid` keeps going and reports them).

Selection supports `--split dev|test`, `--category` (repeatable), `--item-id`
(repeatable), and `--limit`. `data/golden.jsonl` is the union of the splits
(40 dev + 120 test), so `--dataset data/golden.jsonl --split test` evaluates the
held-out half.

`dataset_statistics()` is the Person 1 handoff: item count, id range, distinct
orders, mean line items per order, per-split / per-category / per-difficulty
counts, items with a reference answer, invalid records.

### 2.1 System runner (§3)

`harness/system_runner.py` + `harness/providers.py`. One request per item,
sequential, temperature 0, no tools, `think` disabled, no retries. Every item
produces one row containing the input ids, the reply, `latency_ms`, provider
token usage, the prompt version and its SHA-256, the request count, text
warnings, and — on failure — a categorised error with metadata.

Two wire formats are supported by the same adapter: Ollama `POST /api/chat` and
OpenAI-compatible `POST {base_url}/chat/completions` (Groq, vLLM, LM Studio).
Latency uses `time.perf_counter()`; decode rate is derived from Ollama's
`eval_duration` when present.

`--system-source FILE` replays replies that already exist instead of calling a
model. Replayed rows are marked `source: "replay"`, keep the original run's
latency and token usage, and gain a `prompt_version_mismatch` warning when the
file's recorded prompt version disagrees with `--system-prompt`.

### 2.2 Judge runner (§4)

`harness/judge_runner.py`. Person 3's `judge.client.Judge` is used **as a
library**, so the harness owns the pipeline, the row schema, and the error
taxonomy while the judge owns the rubric and the parsing rules. The judge
receives the customer message, the order context, and the reply, against the
versioned rubric prompt (`judge_v1`/`judge_v2`).

Each grade row stores the five criterion scores and the total, the reason
(truncated to 400 characters), the judge's model, prompt version and prompt
SHA-256, latency, normalised token usage, and the judge's `declared_total` /
`total_corrected` so its own arithmetic errors stay visible. `JudgeError` is
mapped to a harness category and stored as a row; a judge that crashes on one
reply does not stop the run.

`--judge-source FILE` replays saved grades. A saved grade is only accepted when
its stored `response_text` matches the reply the harness holds; otherwise it
becomes a `dataset_error` row instead of being attributed to this run. All 120
grades in `results/judge-comparison-v2-20260929/` match their baselines exactly.

### 2.3 Structured results (§5)

`items.jsonl` has exactly one row per evaluation item:

```json
{"item_id": "DEV-001", "split": "dev", "category": "order_status",
 "difficulty": "easy", "status": "ok",
 "system": {"response_text": "...", "latency_ms": 3908.4, "tokens": {...},
            "prompt_version": "v3", "system_prompt_sha256": "...", "requests": 1,
            "warnings": [], "error": null},
 "judge": {"scores": {"factual_correctness": 2, "total": 8}, "reason": "...",
           "judge_latency_ms": 14593.5, "judge_usage": {...},
           "judge_prompt_version": "judge_v2", "status": "ok", "error": null}}
```

`status` is `ok`, `not_judged`, `system_error`, or `not_run`. A missing item in
`items.jsonl` therefore means the run was interrupted, nothing else — coverage is
auditable. The schema was agreed with Person 3 in `judge/HANDOFF_PERSON_2.md`
and follows their row field names, so the saved judge files map onto it directly.

### 2.4 Metrics (§6)

`harness/metrics.py` produces three groups.

**System** — average total /8, score distribution (all nine totals, so absent
scores are visible as `0` counts rather than missing), per-criterion averages
and points lost with the item ids responsible, per-category and per-difficulty
averages, the 15 lowest-scored items with the judge's reason, failed items,
coverage, and failures by category.

**Reliability** — human-vs-human agreement per criterion (exact, within one
point, mean absolute difference, unweighted and linearly weighted kappa),
judge-vs-human agreement reported **per evaluator** with the major disagreements
(≥ 2 total points) listed individually, labelled coverage, and the two bias
experiments.

**Performance** — latency per phase (count/mean/median/p95/min/max/stdev), wall
clock, token totals per phase, throughput, sequential call count, and the extra
judge calls spent on the bias experiments as their own block.

**Cost** — `harness/cost.py` reports per item, per 1,000 requests, per run, and
the required **100× volume projection** (`--cost-multiplier` to change it), for
the system phase, the judge phase, the experiments, the combined pass, and the
whole run. A local-inference estimate is available but strictly optional: it
needs `HARNESS_LOCAL_COST_PER_HOUR` and is labelled
`estimated_from_assumption`, never an invoice.

### 2.5 Error handling (§7)

`harness/errors.py` defines the thirteen categories the specification lists plus
the mappings from the judge's own error kinds. Every failure — dataset, system,
judge, invalid judge output, API, timeout, network, model missing, incomplete
output, refusal, missing field, configuration, internal — becomes a row in
`errors.jsonl` with `item_id`, `phase`, `category`, `message`, and metadata, and
a count in `metrics.errors`.

A single failed item never stops the evaluation: the run continues, coverage is
reported next to every average, and the exit code is `1` so a caller can detect
it. Provider error bodies are never echoed (they can contain credentials), and
nothing is retried, so a rate limit is visible as a rate limit instead of being
hidden behind a retry loop.

### 2.6 One-command execution (§8)

`python -m harness run` with defaults is the whole evaluation. Installation,
configuration, dataset location, command, and result location are documented in
`harness/README.md` and summarised in the project `README.md` §16.

`--preflight` checks configuration and provider readiness (including whether the
requested local model is actually installed) and spends no model call.

### 2.7 Reproducibility (§9)

* `metadata.json` records the exact reproduction command, the dataset path and
  SHA-256, the prompt files with their SHA-256, the judge prompt hash, the
  configuration (variable *names* only), the Python version, platform, and the
  git commit.
* `code_sha256` in the same file ties the run to the code that produced it.
* Rows are streamed and flushed as they are produced, so an interrupted run keeps
  its completed work; `--resume` continues it without repeating a call.
* An existing output directory is never overwritten, and the refusal happens
  *before* any provider call.
* `python -m harness report --run DIR` rebuilds `metrics.json`, `cost.json`, and
  `report.md` from the saved rows with no model call, so the report is
  reproducible from the committed results alone.
* No key is ever written to a file. `SystemConfig` records `api_key_env`; the
  judge records `api_key_configured: true/false`. A test runs the whole pipeline
  with a key in the environment and asserts the value appears in **no** file
  under the run directory.

### 2.8 Prompt version tracking (§10)

`harness/prompts.py` loads `prompts/system_v*.txt`, hashes each one, and refuses
an unknown version by name. Every run records the prompt version and its
SHA-256 in `metadata.json`, in every `system.jsonl` row, in `items.jsonl`, and in
the comparison.

`python -m harness compare` builds the table the specification asks for — prompt
version, run id, split, items, judged, average /8, delta against the baseline,
mean and p95 system latency, system and judge tokens, cost — and adds the score
distribution per version. `--legacy` includes the repository's earlier saved
evidence so old and new numbers are readable in one table.

### 2.9 Results location (§11)

`results/harness/<run_id>/` for runs, `results/harness/comparisons/` for the
prompt-version comparison. Committed evidence:

| Artefact | What it is |
| --- | --- |
| `results/harness/dev-v1-replay/` | v1, 40 items, replayed from Person 4 + Person 3 |
| `results/harness/dev-v2-replay/` | v2, same |
| `results/harness/dev-v3-replay/` | v3, same |
| `results/harness/dev-v3-live-qwen25/` | v3, full live run (system + judge + both experiments) |
| `results/harness/comparisons/prompt_versions.{json,md}` | the version table |

### 2.10 Handoffs (§12)

See `docs/PERSON_2_HANDOFFS.md`.

## 3. Results

Committed replay runs reproduce Person 3's saved evaluation exactly:

| Prompt | Items | Judged | Average /8 | Δ vs v1 | Mean system ms | p95 system ms | System tokens | Judge tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | 40 | 40 | 7.850 | — | 3,908.3 | 7,629.0 | 28,466 | 49,463 |
| v2 | 40 | 40 | 7.875 | +0.025 | 4,570.2 | 7,854.7 | 35,318 | 48,708 |
| v3 | 40 | 40 | 7.925 | +0.075 | 5,757.3 | 9,859.1 | 39,823 | 48,267 |

Per-criterion averages (out of 2/2/2/1/1):

| Prompt | Factual | Complete | No halluc. | Relevant | Polite |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 | 1.950 | 1.950 | 1.950 | 1.000 | 1.000 |
| v2 | 1.950 | 1.975 | 1.950 | 1.000 | 1.000 |
| v3 | 2.000 | 1.925 | 2.000 | 1.000 | 1.000 |

**How to read this.** v3 is the best mean score, and it is also the slowest and
the most verbose (39,823 system tokens against 28,466 for v1, +40%). The
difference between the three means is 0.075 points on a scale of 8, i.e. three
points spread across 40 items, and it was produced by a **model judge, not by
independent humans**. The direction is consistent with Person 4's change (v3
raises factual correctness and no-hallucination to 2.000 and gives up 0.05 of
completeness), but the magnitude is inside the noise of a single judge run.
These numbers support "v3 is not worse and is plausibly slightly better"; they do
not support a strong claim. The first live measurement with the position and
verbosity controls in place is in the next section; it is one data point, not the
re-measurement the report should lean on.

### One full live run

`results/harness/dev-v3-live-qwen25/` is the first end-to-end run that actually
called models: `qwen2.5:14b` served both the system (prompt `v3`) and the judge
(prompt `judge_v2`) over local Ollama, 40 dev items, plus both bias experiments.
It exists to demonstrate the harness end to end and to supply real latency, token
usage, and experiment figures; it is **not** byte-reproducible (a live run
depends on the local model and machine), unlike the replay rows above.

| Measure | Value |
| --- | --- |
| Quality | 7.950 / 8 (39 full marks, 1 below: `P1-031` prices_totals, 6/8) |
| System latency | mean 5,213 ms, p95 8,366 ms, max 12,810 ms |
| Judge latency | mean 8,713 ms, p95 9,864 ms, max 11,277 ms |
| Wall clock | 651.9 s (3.68 items/min, 95 sequential model calls) |
| System tokens | 33,761 prompt + 1,245 completion = 35,006 (40 items) |
| Judge tokens | 42,480 prompt + 2,965 completion = 45,445 (40 items) |
| Experiment calls | 15 extra judge calls, 20,162 tokens |
| Position bias | 2 of 3 pairs order-sensitive (66.7%) |
| Verbosity bias | 0 of 3 replies changed score (avg change 0.00) |
| Errors | 0 (system ok 40/40, judged 40/40) |
| Judge arithmetic corrections | 4 |
| Cost | `null` — local provider, no API price |

The measured live score (7.950) is among the best seen for v3 and close to the
replayed figures, which is reassuring but not a claim: the replayed runs judge
Person 4's saved replies with Person 3's judge, while the live run judges replies
generated by a different model (qwen2.5, not Person 4's setup on the saved
baselines), so the two number sets are not directly comparable.

The bias experiments are screening results at tiny sample sizes. The position
result (2 of 3 pairs order-sensitive) matters: it says the judge's stated
preference between two replies flipped in at least one repeat for two of the
three pairs — exactly the "re-measure with controls in place" warning above, now
observed once. The verbosity result (0 of 3 changed) means no score change was
observed in these three replies, not that the judge is verbosity-immune.

Latency and token figures are provider- and hardware-specific. They were
measured on one laptop with local Ollama; they are comparable *within* this table
and not across machines.

### Human agreement on the current labels

`data/human_labels.jsonl` holds 160 reference answers with two seeded labels
each: 86.25% exact agreement on the total, 100% within one point, mean absolute
difference 0.1375. Cohen's kappa is `0.0` — **not** because the raters disagree,
but because evaluator 1 assigned 8/8 to all 160 items, so their rating has no
variance and chance agreement equals the observed agreement. That is a property
of the seeded placeholder labels, not of the rubric, and it is exactly why the
report prints raw agreement next to kappa.

### What these results do not prove

* **No independent human labels for the evaluated replies.** The labels on file
  cover `response_id: "reference_answer"`, not `baseline_v1/v2/v3` or any live
  reply set. The harness detects this and says so in every run's notes instead of
  reporting an agreement number. Judge-vs-human agreement is therefore still
  **pending**, and the score comparisons above are model-assigned only.
* **The bias experiments are screening results.** A position pair is called
  order-sensitive if any repeat disagrees, which also captures ordinary model
  variation; with one repeat and a handful of pairs, "0% changed" means "no
  disagreement was observed in these pairs", not "the judge is unbiased". The
  live run's 66.7% position result (2 of 3 pairs) is a genuine signal, but it
  rests on three pairs; a final claim needs the larger sample asked for in the
  handoffs.
* **Cost is `null`.** No prices were configured, because a local Ollama run has no
  API price. `cost.json` says `local_provider` and reports `null` rather than
  `0`. A hosted-judge run with `JUDGE_*_PRICE_PER_M` set produces real numbers.

## 4. Design decisions worth knowing

1. **Standard library only**, matching `judge/client.py` and `system/`. A clean
   clone runs the harness with nothing but Python 3.10+.
2. **One writer per row, flushed immediately.** `JsonlSink` appends and flushes,
   which is what makes `--resume` honest. An existing directory is never
   clobbered.
3. **The judge is a library, not a subprocess.** The harness needs latency,
   usage, and errors per item, and needs to run experiments against the same
   client. `judge/evaluate_versions.py` is still available for standalone use.
4. **Replay is a first-class mode.** It is what makes the committed results
   reproducible on a machine with no model, and it is how the saved evidence was
   cross-checked rather than re-measured.
5. **Derived artefacts are always rebuildable.** `report` re-derives metrics, cost,
   and the report from the saved rows, so a formatting change never requires
   re-running a model.
6. **Experiments are costed separately.** Extra judge calls are recorded per row
   as `extra_calls` (usage + latency), so `run_total` in `cost.json` is what a
   run with experiments actually cost, and `combined` stays the plain per-item
   pass.
7. **`null` is a value.** Unrun experiments, unpriced tokens, unmeasured wall
   clock, and undefined kappa are all `null`. The report prints `n/a`.

## 5. Tests

```powershell
python -m unittest discover -s harness/tests -t harness/tests   # 84 tests
python -m unittest discover -s judge/tests -t judge/tests       # 18 tests
```

| File | Tests | Covers |
| --- | ---: | --- |
| `test_dataset.py` | 15 | loading, validation, duplicates, encodings, statistics, labels, saved replies |
| `test_providers.py` | 10 | both wire formats, preflight, error mapping, key handling |
| `test_system_runner.py` | 9 | one call per item, resume skipping, replay, prompt mismatch |
| `test_judge_runner.py` | 10 | grading, judge errors, usage normalisation, replay text matching |
| `test_metrics.py` | 17 | distributions, kappa, agreement, bias summaries, null handling |
| `test_cost.py` | 8 | per item, per 1,000, projection, experiments, unpriced `null` |
| `test_results_cli.py` | 15 | the whole CLI end to end with a mocked provider |

The CLI tests drive the real entry point with mocked HTTP, so a full run, a
hosted-provider run, a resumed run, a failing provider, a refusing overwrite, a
replay, and a bias-experiment run all execute in about a second with no model
and no network.

## 6. Known limitations

1. **Sequential execution.** No concurrency, by design: it keeps per-item latency
   measurable and the run reproducible. Wall clock is therefore the sum of the
   requests.
2. **No statistical significance testing.** Averages are reported with
   distributions, coverage, and per-item rows, but no confidence interval or
   significance test is computed; a paired per-item difference file is available
   (`items.jsonl`) if someone wants to do that analysis.
3. **The bias experiments scale poorly.** They are one judge call at a time, so a
   40-pair position experiment with two repeats is 160 extra calls. Sample sizes
   are set by `--position-limit` / `--verbosity-limit` and must be stated in the
   report.
4. **One dataset hash per run.** A run covers one dataset file; comparing two runs
   over different datasets is possible but the comparison table does not warn
   about it. Check `metadata.json.dataset.sha256` before comparing.
5. **Provider usage is taken at face value.** Token counts are what the provider
   reported. A provider that under-reports is under-reported here too; nothing is
   estimated to fill the gap.
6. **`Person 2` did not relabel anything.** The missing human labels are a
   dataset/labeling gap, reported in `docs/PERSON_2_HANDOFFS.md` rather than
   silently filled with model scores.

## 7. Definition of Done

From `docs/PERSON_2_HARNESS.md`:

| Requirement | Status | Evidence |
| --- | --- | --- |
| Dataset loader works | Done | `harness/dataset.py`, `test_dataset.py`, `python -m harness validate` |
| System can be evaluated automatically | Done | `python -m harness run`, `test_results_cli.py` |
| Judge can be called automatically | Done | `harness/judge_runner.py`, `test_judge_runner.py` |
| Structured results generated | Done | `items.jsonl` schema above |
| One result exists per item | Done | `join_rows` + `items_without_result` in `metrics.run` |
| Errors are recorded | Done | `errors.jsonl`, `metrics.errors`, exit code 1 |
| Score statistics calculated | Done | `metrics.system` (average, distribution, breakdowns) |
| Cost calculated | Done | `cost.json` (per item / per 1,000 / run / 100× projection) |
| Latency calculated | Done | `metrics.performance` |
| Prompt versions can be compared | Done | `python -m harness compare`, `results/harness/comparisons/` |
| Evaluation can run from a clean clone | Done | stdlib only; `harness/.env.example`; no committed secrets |
| No secrets committed | Done | asserted by `test_metadata_and_artifacts_never_contain_a_key` |
| Final results stored in `results/` | Done | `results/harness/` |

Known gap, owned by others: **judge-vs-human agreement on the evaluated replies**
needs independently reviewed human labels for those exact replies
(`docs/PERSON_2_HANDOFFS.md`).
