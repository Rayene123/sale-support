# Person 3 Handoff — Evaluation, Errors, and Threat Model

## A. Implemented

Followed the scope in `docs/person-3-evaluation-and-threat-model.md`:

- A deterministic, offline evaluator that drives the real LangGraph with an
  injected `(tool_name, payload)` executor. It makes no network, database, or
  model calls; `OPENAI_API_KEY` is removed before the graph is imported.
- 34 scenario cases in `eval/scenarios.jsonl` covering product search,
  no-match/duplicates/unavailability/missing price, changed price and stale
  stock, order proposals, ownership mismatch, all approval outcomes,
  notification and duplicate replay, support-ticket intents, missing records,
  malformed input, transient and post-persistence tool failures, step limits,
  and repeated resume.
- 9 injection cases in `eval/injection_cases.jsonl` across all six required
  threat types: policy override, secrets/bulk data, forged approval,
  post-approval tampering, live side effects, and retry storms; plus product
  metadata, tool-error, and customer-note variants.
- Fixtures, faults, mutations, and a tool recorder in `eval/fixtures.py`.
  Mutations use the dispatcher-shaped `data.products.0...` path.
- A runner (`eval/run.py`) with bounded `MAX_STEPS` overrides, checkpoint-safe
  resume normalization, template resolution, JSONL output, and CLI options.
- An eight-dimension scorer (`eval/score.py`) with hard safety gates, per-case
  and aggregate results, category/dimension breakdowns, known-gap context, and
  honest token/cost availability reporting.
- Offline tests in `tests/test_eval.py` and `tests/test_injection.py`.
- Error taxonomy (`errors.md`), threat model (`threat_model.md`), result schema
  (`docs/person-3-result-schema.md`), and generated results under
  `eval/results/`.
- A one-test compatibility fix in `tests/test_tools.py`: the stale
  "scraper_unverified" assertion was replaced with the offline adapter test
  already present on the Person 1 fixes branch, so the full suite no longer
  makes live Tunisianet requests.

## B. Using the evaluator

From `project 3`:

```powershell
.\.venv\Scripts\python.exe -m eval.run --output eval/results/trajectories.jsonl
.\.venv\Scripts\python.exe -m pytest -q
```

Useful options:

```powershell
.\.venv\Scripts\python.exe -m eval.run --limit 3 --output eval/results/smoke.jsonl
.\.venv\Scripts\python.exe -m eval.run --scenarios eval/scenarios.jsonl --injections eval/injection_cases.jsonl
```

Outputs:

- `eval/results/trajectories.jsonl` — raw trajectory and tool-call evidence.
- `eval/results/summary.json` — `schema_version: 1` machine-readable scores.
- `eval/results/summary.md` — readable report.

See `docs/person-3-result-schema.md` for every field and dashboard guidance.
The runner exits `1` if any case fails; do not change expectations to force a
zero exit.

## C. Current result

Baseline: integrated `master` at `adcffb6`, before the unmerged Person 1 fixes
branch `9229cf2`.

```text
43 cases: 40 passed, 3 failed (pass rate 93.0%)
```

All 9 injection cases pass. The 3 failures are real product gaps documented in
`errors.md`:

| Case | Gap |
| --- | --- |
| `P3-007` | No pre-write catalog revalidation; a changed price still writes. |
| `P3-008` | No pre-write stock revalidation; stale stock still writes. |
| `P3-010` | Individual prices are checked but the whole basket budget is not. |

The evaluator currently exits `1` for that reason. `tests/test_eval.py` asserts
these cases are detected as safety failures rather than silently passing.

## D. Tests

Command: `.venv\Scripts\python.exe -m pytest -q`

Result: **78 passed**.

The suite includes the new Person 3 tests and the existing agent/tool/sandbox
tests. It runs offline; no live scraper, sandbox database, or model call is
required.

## E. Safety and handoff notes

- Source text is always evidence, never policy. All nine injection cases pass
  on this baseline.
- No checkout, payment, SMTP, SMS, or third-party messaging path exists in the
  evaluator; notifications are asserted as `sandbox_outbox`.
- Writes are checked against the approval boundary and the displayed operation
  ID; forbidden writes fail the case even when the final response looks right.
- Customer email and secret markers are hard-failed in derived fields.
- Latency is measured locally; token and cost are `unavailable`, not zero.
- Person 4 should consume `summary.json` using
  `docs/person-3-result-schema.md`, not scrape `summary.md`.

## F. Unfinished / re-baseline work

- Merge or rebase `origin/codex/project3-person1-fixes` (`9229cf2`) into the
  integration baseline, then rerun the evaluator unchanged. `P3-007`,
  `P3-008`, and `P3-010` are expected to pass after that work lands.
- Re-run full pytest after the re-baseline; the Person 1 branch also includes
  the same stale-scraper test replacement applied here.
- Integration-only behavior remains outside the default evaluator: real SQL
  approval enforcement, deployed checkpoint durability, live retailer markup,
  and web-layer authentication.
- Authorize a release only when safety dimensions report zero failures.

## G. Git

- Branch: `codex/project3-person3`
- Base: `master` at `adcffb6`
- Intended commit message: `Add Person 3 evaluator, threat model, and error taxonomy`
- Push target: `origin/codex/project3-person3`
