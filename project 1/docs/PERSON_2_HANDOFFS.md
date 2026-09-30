# Person 2 handoffs

What the evaluation harness produced for the rest of the team, and what it needs
back. Code: `harness/`. Usage: `harness/README.md`. Numbers:
`docs/PERSON_2_HARNESS_IMPLEMENTATION.md`.

---

## To Person 1 — dataset and labeling

### What you get

* `python -m harness validate --dataset data/golden.jsonl --check-prompts` loads
  every file, validates each record, and prints statistics. It never silently
  drops a record: each rejected record is reported as `file:line: item id —
  problem`, and by default any invalid record **stops the run** (exit code 2) so
  a broken file can never be half-evaluated. `--allow-invalid` keeps going and
  lists them.
* The same statistics land in every run's `metadata.json.dataset.statistics` and
  in `metrics.json` under `run`, so the report can quote them without re-running
  anything.

### Current state of the repository data

| File | Items | Splits | Invalid records |
| --- | ---: | --- | ---: |
| `data/golden.jsonl` | 160 | dev 40, test 120 | 0 |
| `data/dev.jsonl` | 40 | dev 40 | 0 |
| `data/test.jsonl` | 120 | test 120 | 0 |
| `data/human_labels.jsonl` | 320 label rows (160 replies × 2) | — | 0 |

All 160 items validate: `id`, `customer_message`, `order_context` with
`order_number`/`status`/`items`, and every line item with
`product_name`/`quantity`/`line_total`. `golden.jsonl` is the union of the two
splits, so the held-out half is
`--dataset data/golden.jsonl --split test`.

### What I need back

1. **The split rule, stated once.** The 40 dev items are the ones Person 4
   iterated on, so prompt versions v1→v3 were chosen while looking at them. The
   120 test items are untouched by that process and are the only honest basis
   for a final number. I recommend: development on `--split dev`, one final
   evaluation of the chosen prompt on `--split test`, reported separately.
2. **Independent human labels for the evaluated replies.** This is the project's
   critical gap — see "To everyone" below. The exact format the harness expects
   is in `harness/dataset.py::load_labels` and in `data/labeling_guide.md`; one
   JSONL row per evaluator per reply:

   ```json
   {"item_id": "DEV-001", "response_id": "dev-v3-live", "response_text": "the exact graded text",
    "evaluator_id": "1", "scores": {"factual_correctness": 2, "completeness": 2,
    "no_hallucination": 2, "relevance": 1, "professional_tone": 1, "total": 8},
    "explanation": "..."}
   ```

   `response_id` must equal the run's reply set id, and `response_text` must be
   the graded text. When the labels are genuinely independent, pass
   `--labels-reviewed` so the run states that in `metadata.json` instead of
   marking the agreement as a smoke check.
3. **A note on the seeded reference labels.** The 160 reference-answer labels
   agree 86.25% exactly (100% within one point, mean |diff| 0.1375) — but
   Cohen's kappa is `0.0`, because evaluator 1 gave 8/8 to all 160 items, so
   their rating has no variance and chance agreement equals observed agreement.
   That is a seeded-placeholder artefact, not a rubric problem. When real labels
   replace them, the kappa figure should become meaningful; until then, quote
   the raw agreement and the kappa together, never kappa alone.

---

## To Person 3 — judge reliability

### What you get

* The harness calls your `judge.Judge` as a library and stores, per graded
  reply: the five criterion scores, the total, the reason, the judge model, the
  judge prompt version **and its SHA-256**, latency, token usage, and
  `declared_total` / `total_corrected` so your judge's own arithmetic slips stay
  visible. `judge.jsonl` in every run directory.
* `metrics.json → reliability` for each run: human-vs-human agreement per
  criterion, judge-vs-human agreement **per evaluator** (never averaged away),
  major disagreements of ≥ 2 total points listed item by item with both reasons,
  labelled coverage, and the two bias experiments with their sample sizes.
* `position.jsonl` and `verbosity.jsonl` in the run directory: every trial, the
  mapped verdict per order, the recorded extra-call usage, and the stored reply
  texts, so a screening result can be re-read rather than taken on trust.
* Verification of your saved results: replaying
  `results/judge-comparison-v2-20260929/{v1,v2,v3}/results.jsonl` through the
  harness reproduces your quality figures exactly (7.850 / 7.875 / 7.925) and
  your latency and token figures, and all 120 stored `response_text` values match
  their baselines. Your saved files are consistent and are now readable by one
  command.

### How to run the experiments

```powershell
# position bias: this run's replies against a saved run, both orders, 2 repeats
python -m harness run --system-prompt v3 --run-id dev-v3-bias --output results/harness/dev-v3-bias `
    --auto-pairs-from results/baseline_v1.jsonl --position-limit 20 --position-repeats 2

# or with your own reviewed pairs (item_id, answer_a, answer_b; must be distinct)
python -m harness run --position-pairs results/position_pairs.jsonl --position-limit 20

# verbosity bias: one extra judge call per item, reusing the grade already paid for
python -m harness run --verbosity-limit 20
```

Extra calls are costed separately (`metrics.performance.experiments`,
`cost.json → experiments`, `run_total`), so the extra spend of an experiment run
is never hidden inside the per-item cost.

### What I need back

1. **Label the evaluated replies** (same as above). Your saved comparison and my
   replay runs currently produce scores, not validated agreement, because the
   labels on file cover `reference_answer` only. Every run says this in its
   notes; the fix is data, not code.
2. **A larger sample for the bias experiments.** Both experiments are screening
   results at the sample sizes I could afford: a position pair costs 2 judge
   calls per repeat, and 20 pairs × 2 repeats is 80 extra calls. Whatever sample
   you use, state it next to the percentage, and remember that a pair which
   disagrees on *any* repeat is counted as order-sensitive — that also captures
   ordinary model variation at temperature 0, so a low percentage is "no
   disagreement was observed in these pairs", not "the judge is unbiased".
    First screening results from the live run (`dev-v3-live-qwen25`, judge
    `qwen2.5:14b`, `judge_v2` prompt): **position 2 of 3 pairs order-sensitive
    (66.7%), verbosity 0 of 3 replies changed score**. The position signal is
    worth the larger run; the verbosity one is consistent with the earlier
    tests but too small to lean on.
3. **Read the padded texts before quoting a verbosity delta.** Padding changes
   tone and can change relevance; the stored `padded_text` is in
   `verbosity.jsonl` for exactly this reason.

---

## To Person 4 — prompt experiments

### What you get

* One command per prompt version, and a comparison table that answers "did the
  change help?":

  ```powershell
  python -m harness run --system-prompt v3 --run-id dev-v3 --output results/harness/dev-v3
  python -m harness compare --run results/harness/dev-v1 --run results/harness/dev-v2 `
      --run results/harness/dev-v3 --legacy --output results/harness/comparisons/prompt_versions
  ```

* Per prompt version: average /8, delta against the baseline, full score
  distribution, per-criterion averages, mean and p95 system latency, system and
  judge token counts, and cost — plus per-item rows, every failed item with its
  category and message, and the lowest-scored items with the judge's reason.
* The same figures are re-derivable from the saved rows with
  `python -m harness report --run <dir>`; no model call is needed to rebuild a
  report.

### What the committed runs show

| Prompt | Average /8 | Δ | Factual | Complete | No halluc. | Mean system ms | System tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v1 | 7.850 | — | 1.950 | 1.950 | 1.950 | 3,908.3 | 28,466 |
| v2 | 7.875 | +0.025 | 1.950 | 1.975 | 1.950 | 4,570.2 | 35,318 |
| v3 | 7.925 | +0.075 | 2.000 | 1.925 | 2.000 | 5,757.3 | 39,823 |
| v3 live (qwen2.5:14b) | 7.950 | — | 1.975 | 1.975 | 2.000 | 5,213.3 | 35,006 |

v3 is the best mean and the most expensive: +47% system latency and +40% system
tokens against v1 for +0.075/8. Say that trade-off explicitly in the changelog
rather than only the score.

The v3 live row is a different kind of evidence: it generated replies with
`qwen2.5:14b` and graded them with the same model, so it is not a re-run of the
replay numbers. It ran the bias experiments too (position: 2 of 3 pairs
order-sensitive, 66.7%; verbosity: 0 of 3 changed score) and measured real
latency and usage: system mean 5.2 s / p95 8.4 s, judge mean 8.7 s / p95 9.9 s,
wall clock 651.9 s for 40 items, 95 sequential calls, 15 extra experiment judge
calls (20,162 tokens), 0 errors, cost `null` (local provider). Use it as
evidence that the harness works end to end and as a performance data point, not
as an independent third measurement of the prompt versions.

### What I need back

1. **A decision on the split.** All three versions were scored on the 40 dev
   items, which is the split you iterated on. Confirm the held-out run: one
   evaluation of the chosen prompt on `--split test` (120 items, never used for
   tuning). I will run it as soon as you pick the prompt.
2. **Fix the `prompt_version` label in `results/baseline_v2.jsonl`.** Those 40
   rows record `prompt_version: v1` although they are v2. The harness detects the
   disagreement and puts `prompt_version_mismatch` on all 40 rows of
   `results/harness/dev-v2-replay/system.jsonl` rather than silently relabelling
   them — but the source file should still say `v2`. (This is the issue noted in
   `judge/HANDOFF_PERSON_2.md`.)
3. **A costed claim for the changelog.** `prompts/CHANGELOG.md` asks for cost per
   version. Every run so far is `local_provider`, so cost is `null`. To get a real
   number, either price a hosted run (`JUDGE_INPUT_PRICE_PER_M`,
   `JUDGE_OUTPUT_PRICE_PER_M`) or state the local-compute assumption
   (`HARNESS_LOCAL_COST_PER_HOUR`), which the report labels
   `estimated_from_assumption`.
4. **Per-failure attribution.** The harness records failed items and the judge's
   reason for the lowest scores, and Person 4's `results/baseline_v1_review.jsonl`
   already contains a review of the v1 failures. Aligning your review with the
   harness's `items.jsonl` is the cheapest way to make the failure analysis in the
   final report verifiable.

---

## To everyone — final results and the reproducible command

### The command

```powershell
cd "project 1"

# 1. check the data and the configuration, spending nothing
python -m harness validate --dataset data/dev.jsonl --check-prompts
python -m harness run --preflight

# 2. the evaluation
python -m harness run --system-prompt v3 --run-id dev-v3 --output results/harness/dev-v3

# 3. the report, the metrics, and the cost
python -m harness report --run results/harness/dev-v3
python -m harness cost   --run results/harness/dev-v3

# 4. the version comparison
python -m harness compare --run results/harness/dev-v1 --run results/harness/dev-v2 `
    --run results/harness/dev-v3 --legacy --output results/harness/comparisons/prompt_versions
```

### What is already committed

| Path | Contents |
| --- | --- |
| `results/harness/dev-v1-replay/`, `dev-v2-replay/`, `dev-v3-replay/` | 40-item runs per prompt version, replayed from the saved baselines and saved grades — identical quality figures to Person 3's comparison |
| `results/harness/dev-v3-live-qwen25/` | one full live run: 40 items, real latency and token counts, position and verbosity experiments |
| `results/harness/comparisons/prompt_versions.{json,md}` | the version table |
| `harness/README.md` | install, configuration, commands, artefacts, metrics, tests |
| `docs/PERSON_2_HARNESS_IMPLEMENTATION.md` | what was built, results, limitations |

The replay runs need no model: `report`, `cost`, and `compare` all work from a
clean clone on the committed rows alone.

### The one thing still missing

**Independent human labels for the evaluated replies.** Every score in this
project is currently model-assigned. The labels on file cover
`response_id: "reference_answer"`, so:

* the measured averages (7.85 / 7.875 / 7.925) are judge-vs-judge comparisons,
  not agreement with a human standard;
* judge-vs-human agreement is **not reported** — the harness says so in each
  run's notes rather than printing a number it cannot support;
* the prompt-version deltas are differences between small numbers produced by one
  model on the split that was tuned on.

Closing that gap is labeling work, not engineering: for each evaluated reply,
two people score it independently with `data/labeling_guide.md`, keeping the
exact `response_text` and setting `response_id` to the run's reply set. Then:

```powershell
python -m harness run --system-prompt v3 --run-id dev-v3 --resume `
    --labels results/human_labels_dev-v3.jsonl --labels-reviewed
```

Until then, the report should say "model-assigned, human validation pending"
next to every score, and should not present the bias experiments as proof that
the judge is unbiased.
