# Project 1 - The Grader

**CS496 AI Engineering, Fall 2026**  
**Instructor:** Dr Abdeldjalil Labed  
**Task:** Customer-support replies grounded in order context

## 1. Task and Dataset

The system answers a customer message using only the supplied order context.
Exact-match scoring is inappropriate because multiple replies can be correct;
the rubric scores factual correctness, completeness, non-hallucination,
relevance, and professional tone for 8 points total.

The committed golden set contains **160 valid items**: **40 development** items
and **120 held-out test** items. Each item contains the customer message and all
order facts needed for evaluation. The labeling guide defines the five criteria
and examples. Two seeded labels exist for each reference answer; they are not
independent labels of the generated system replies, so they cannot yet support
a valid judge-versus-human claim.

## 2. Harness

`harness/` loads and validates JSONL, filters by split/category/id, runs one
system call per item, sends successful replies to the structured-output judge,
and writes one joined result row per item. It records errors instead of
silently dropping items, preserves prompt and dataset hashes, and reports
counts, percentages, latency, token usage, cost, and per-item outcomes.

Offline tests cover dataset validation, providers, runners, metrics, cost, and
the CLI. Replays use saved rows and make no model calls.

## 3. Judge Reliability

The judge returns fixed criterion scores, a total, and a short reason. The
development v3 live run includes position and verbosity screening. These are
screening experiments, not proof of reliability: independent human labels for
the evaluated replies are required for judge-human agreement. The saved seeded
reference labels report **86.25% exact agreement** and **100% agreement within
one point**, but those figures describe reference answers rather than generated
replies.

The v3 screening run changed the position verdict in **2 of 3 comparisons
(66.7%)** and changed the verbosity grade in **0 of 3 (0.0%)**. The position
sample is intentionally small and must be expanded for a defensible conclusion.

## 4. System Prompt History

All three versions were compared on the same 40 development items using saved
system replies and saved judge grades:

| Version | Mean score (/8) |    Full marks | Interpretation                            |
| ------- | --------------: | ------------: | ----------------------------------------- |
| v1      |           7.850 | 38/40 (95.0%) | baseline                                  |
| v2      |           7.875 | 39/40 (97.5%) | stronger grounding rules                  |
| v3      |           7.925 | 38/40 (95.0%) | stronger unsupported-information handling |

These are model-assigned development scores and are evidence of prompt
iteration, not final test performance. V3 also used more prompt tokens than v1,
so the score change must be considered with latency and cost.

## 5. Cost, Latency, and Limitations

The harness writes cost and latency per run and projects cost per 1,000 and
100x requests. The committed local-provider runs have no configured USD price,
so cost is reported as `null`, never as zero. The development live run records
system and judge latency plus position and verbosity experiment rows.

Before submission, run the chosen prompt once on the untouched test split:

```powershell
cd "project 1"
python -m harness run --dataset data/test.jsonl --split test --system-prompt v3 `
    --run-id test-v3 --output results/harness/test-v3
```

Then independently label those generated replies and rerun the judge reliability
analysis. Do not tune the prompt against the test scores.

## 6. Contributions

| Member            | Responsibility                                                                    |
| ----------------- | --------------------------------------------------------------------------------- |
| Rayen Zegden      | Person 1: golden dataset, split design, and labeling guide                        |
| Selim Garrach     | Person 2: evaluation harness, result schema, metrics, and tests                   |
| Mohamed Omar Abid | Person 3: LLM judge, structured grading, and reliability experiments              |
| Oussama Medimagh  | Person 4: prompted customer-support system, prompt versions, and failure analysis |

## 7. Reproducibility

```powershell
cd "project 1"
python -m unittest discover -s harness/tests -t harness/tests
python -m unittest discover -s judge/tests -t judge/tests
python -m harness validate --dataset data/golden.jsonl
```

No API keys are committed. Live runs require a configured local or hosted model;
report and comparison commands can run from saved rows without a model.
