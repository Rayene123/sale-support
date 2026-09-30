# CS496 AI Engineering — Project 1

## The Grader

**Course:** CS496 — AI Engineering
**Project:** Project 1 — The Grader
**Team Size:** 4
**Task:** Customer-support reply evaluation

**Instructor:** Dr Abdeldjalil Labed<br>
**Institution:** Mediterranean Institute of Technology<br>
**Term:** Fall 2026

## Submission Status

The harness is the primary deliverable; the prompted support system exists only
to be measured. The committed evidence covers development-set prompt comparison
and judge-bias screening. A final run on the held-out test split and independent
human labels for generated replies are still required before claiming final
system quality or judge-human reliability.

---

# 1. Project Overview

This project builds an **evaluation harness** for measuring the quality of an AI system that generates customer-support replies based on e-commerce order information.

The AI system receives:

- A customer message
- Relevant order information

and generates a customer-support response.

The project evaluates whether the generated response is:

- Factually correct
- Complete
- Free from hallucinations
- Relevant
- Professional and polite

The main deliverable is the **evaluation harness**, not the customer-support AI itself.

---

# 2. Project Objective

The project must provide a reproducible way to:

1. Create a 150+ item golden evaluation dataset.
2. Define a human labeling rubric.
3. Measure agreement between human evaluators.
4. Run the customer-support AI on the dataset.
5. Use an LLM judge to evaluate generated responses.
6. Measure agreement between the LLM judge and humans.
7. Test judge reliability and biases.
8. Compare different versions of the system prompt.
9. Measure evaluation cost and latency.
10. Document failures and lessons learned.

---

# 3. Evaluation Task

### Input

Each evaluation item contains information such as:

```text
Customer message
Order ID
Order status
Products
Quantities
Prices
Order total
```

### Output

The AI generates a customer-support reply.

### Example

**Customer message:**

> Where is my order and what did I buy?

**Order context:**

```text
Order: #1042
Status: Shipped
Items:
- OnePlus 13 × 1
- USB-C Cable × 2
Total: €839.97
```

**Possible response:**

> Your order #1042 has been shipped. It contains one OnePlus 13 and two USB-C cables, for a total of €839.97.

There is no single exact correct response. Multiple responses can be valid as long as they satisfy the evaluation criteria.

---

# 4. Evaluation Rubric

Each response is scored out of **8 points**.

| Criterion                | Score |
| ------------------------ | ----: |
| Factual correctness      |   0–2 |
| Completeness             |   0–2 |
| No hallucination         |   0–2 |
| Relevance                |   0–1 |
| Professional/polite tone |   0–1 |
| **Total**                | **8** |

Detailed definitions and examples are available in:

```text
data/labeling_guide.md
```

---

# 5. Dataset

The golden dataset must contain **at least 150 evaluation items**.

The dataset should cover:

- Order status questions
- Order content questions
- Quantity questions
- Price and total questions
- Multi-part questions
- Ambiguous questions
- Unsupported-information questions
- Hallucination traps
- Difficult and edge cases

Each item is independently labeled by **two human evaluators**.

Human agreement is measured and documented.

---

# 6. Evaluation Pipeline

The overall evaluation process is:

```text
                ┌─────────────────┐
                │  Golden Dataset │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │  AI System      │
                │  Prompt Version │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Generated Reply │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │   LLM Judge     │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Evaluation      │
                │ Results         │
                └─────────────────┘
```

The results are then compared with human labels to measure judge reliability.

---

# 7. Judge Reliability

The LLM judge will be evaluated against human judgments.

We will measure:

### Human Agreement

Agreement between the two human evaluators.

### Judge-Human Agreement

Agreement between the LLM judge and human evaluations.

### Position Bias

The same answers will be presented in different orders to determine whether changing answer order changes the judge's evaluation.

### Verbosity Bias

Responses will be padded with unnecessary text to determine whether the judge rewards verbosity without an actual improvement in quality.

### Judge Failure Analysis

We will document cases where the judge produces unreliable or inconsistent evaluations.

---

# 8. Prompt Experiments

The customer-support system will have versioned prompts.

Example:

```text
Prompt v1
   ↓
Evaluation
   ↓
Prompt v2
   ↓
Evaluation
   ↓
Prompt v3
   ↓
Evaluation
```

Every prompt change must be documented in:

```text
prompts/CHANGELOG.md
```

Each experiment should record:

- Prompt version
- What changed
- Why it changed
- Score before
- Score after
- Cost
- Latency
- Observed failure changes

---

# 9. Team Responsibilities

## Person 1 — Golden Dataset & Labeling

Responsible for:

- Task definition
- Dataset creation
- 150+ golden items
- Labeling guide
- Human labeling
- Human agreement
- Dev/test split

See:

```text
docs/PERSON_1_DATASET.md
```

---

## Person 2 — Evaluation Harness

Responsible for:

- Dataset loading
- System execution
- Judge execution
- Structured results
- Metrics
- Cost
- Latency
- Reproducibility
- One-command evaluation

See:

```text
docs/PERSON_2_HARNESS.md
```

---

## Person 3 — LLM Judge & Reliability

Responsible for:

- LLM judge prompt
- Judge output schema
- Human-vs-judge comparison
- Position-bias test
- Verbosity-bias test
- Judge failure analysis

See:

```text
docs/PERSON_3_LLM_JUDGE.md
```

---

## Person 4 — Customer-Support AI System

Responsible for:

- Customer-support AI
- Baseline prompt
- Prompt improvements
- Prompt experiments
- Failure analysis
- Prompt changelog

See:

```text
docs/PERSON_4_SYSTEM.md
```

---

# 10. Team Dependency

The project should progress approximately in this order:

```text
Person 1
Task + Rubric + Dataset Schema
        │
        ├───────────────┐
        ▼               ▼
   Person 3         Person 4
   LLM Judge        AI System
        │               │
        └───────┬───────┘
                ▼
             Person 2
        Evaluation Harness
                │
                ▼
        Full Evaluation
                │
        ┌───────┴────────┐
        ▼                ▼
 Judge Reliability   Prompt Experiments
        │                │
        └───────┬────────┘
                ▼
             Final Report
```

Person 2 can begin designing the harness before the other components are finished, but the final integration requires the interfaces from Persons 1, 3, and 4.

---

# 11. Repository Structure

```text
project 1/
│
├── README.md
│
├── docs/
│   ├── PERSON_1_DATASET.md
│   ├── PERSON_2_HARNESS.md            the requirement list
│   ├── PERSON_2_HARNESS_IMPLEMENTATION.md  what was built, results, limits
│   ├── PERSON_2_HANDOFFS.md           what each teammate gets and owes
│   ├── PERSON_3_LLM_JUDGE.md
│   ├── PERSON_4_SYSTEM.md
│   └── PERSON_4_FAILURE_ANALYSIS.md
│
├── data/
│   ├── golden.jsonl           160 items: 40 dev + 120 test
│   ├── dev.jsonl               40 development items
│   ├── test.jsonl             120 held-out items
│   ├── human_labels.jsonl     two seeded labels per reference answer
│   ├── labeling_guide.md      the rubric humans and the judge share
│   └── dataset_notes.md
│
├── harness/                    the evaluation harness (Person 2)
│   ├── README.md               install, configure, run, artefact reference
│   ├── cli.py  config.py  dataset.py  prompts.py  providers.py
│   ├── system_runner.py  judge_runner.py  metrics.py  cost.py
│   ├── report.py  compare.py  results.py  errors.py
│   ├── .env.example            local configuration template, never a real key
│   └── tests/                  84 offline tests
│
├── judge/                      the LLM judge (Person 3)
│   ├── client.py               grade() and prefer(), standard library only
│   ├── run.py  evaluate_versions.py  compare_humans.py
│   ├── prompts/judge_v1.txt  judge_v2.txt  CHANGELOG.md
│   ├── HANDOFF_PERSON_2.md     the contract the harness integrates against
│   ├── README.md
│   └── tests/                  18 offline tests
│
├── system/                     the customer-support AI (Person 4)
│   ├── run.py  metrics.py
│
├── prompts/                    the evaluated system's prompts (Person 4)
│   ├── system_v1.txt  system_v2.txt  system_v3.txt
│   └── CHANGELOG.md            what changed, why, and the measured effect
│
└── results/
    ├── baseline_v1.jsonl  baseline_v2.jsonl  baseline_v3.jsonl   (Person 4)
    ├── judge-comparison-v2-20260929/       saved judge grades      (Person 3)
    └── harness/                             evaluation runs        (Person 2)
        ├── dev-v1-replay/  dev-v2-replay/  dev-v3-replay/
        ├── dev-v3-live-qwen25/
        └── comparisons/prompt_versions.{json,md}
```

---

# 12. Data Source

The evaluation scenarios will be constructed using the team's existing e-commerce database.

Relevant tables include:

```text
products
categories
orders
order_items
```

The database is used to construct realistic evaluation scenarios.

For the actual evaluation, each JSONL item must contain the necessary order context so that the evaluated system does not need to dynamically retrieve information from the database.

The evaluation should remain reproducible and follow the project constraint of **one model call per item with no agents or retrieval**.

---

# 13. Results

Evaluation results should be stored in:

```text
results/
```

The results should allow us to answer:

- How well does the system perform?
- Which types of questions cause failures?
- Does the judge agree with humans?
- Does answer order affect the judge?
- Does unnecessary verbosity affect the judge?
- How much does each evaluation cost?
- How long does evaluation take?
- Did prompt changes improve the measured score?

---

# 14. Prompt Changelog

All prompt changes must be tracked.

Example:

```text
## v2

Change:
Added explicit instruction not to invent information unavailable
in the order context.

Reason:
Baseline produced unsupported delivery information.

Evaluation:
Score before: X
Score after: Y

Cost:
X

Latency:
X
```

---

# 15. Security

Never commit:

- API keys
- Access tokens
- Passwords
- `.env` files containing secrets
- Private credentials

Use environment variables for credentials.

Example:

```text
.env
```

should be ignored by Git.

---

# 16. Reproducibility

The final repository must work from a clean clone.

## Installation

Python 3.10 or newer. The evaluation harness, the judge, and the system all use
the **standard library only** — there is nothing to `pip install`. A model
provider is needed only to run a _live_ evaluation.

```powershell
python --version

# local provider (no API key, no network egress)
ollama pull qwen2.5:14b

# optional: copy the local configuration once
Copy-Item harness/.env.example harness/.env
```

`harness/.env` is local and git-ignored. Keys are read from the environment
only and are never written to a file:

```powershell
$env:GROQ_API_KEY = "..."      # only if a hosted provider is configured
```

## Configuration

| What                                       | Where                                         | Default                                |
| ------------------------------------------ | --------------------------------------------- | -------------------------------------- |
| Evaluated system provider / model / prompt | `SYSTEM_*` or `--system-*`                    | `ollama` / `qwen2.5:14b` / prompt `v1` |
| Judge provider / model / prompt            | `JUDGE_*` or `--judge-*`                      | `ollama` / `qwen3:14b` / `judge_v2`    |
| Token prices (USD per million)             | `SYSTEM_*_PRICE_PER_M`, `JUDGE_*_PRICE_PER_M` | unset → cost reported as `null`        |
| Dataset                                    | `--dataset`                                   | `data/dev.jsonl`                       |

Precedence: command-line option → environment variable → `harness/.env`.

## Dataset location

```text
data/golden.jsonl      160 items (40 dev + 120 test), the full set
data/dev.jsonl          40 items, the development split
data/test.jsonl        120 items, the held-out split
data/human_labels.jsonl 320 label rows (160 reference answers x 2 evaluators)
data/labeling_guide.md the rubric both humans and the judge follow
```

## Evaluation command

```powershell
cd "project 1"

# check the data and the configuration, spending nothing
python -m harness validate --dataset data/dev.jsonl --check-prompts
python -m harness run --preflight

# the evaluation: dataset -> system -> judge -> metrics -> cost -> report
python -m harness run --system-prompt v3 --run-id dev-v3 --output results/harness/dev-v3

# with the reliability experiments (extra judge calls, costed separately)
python -m harness run --system-prompt v3 --run-id dev-v3-bias --output results/harness/dev-v3-bias `
    --verbosity-limit 20 --auto-pairs-from results/baseline_v1.jsonl `
    --position-limit 20 --position-repeats 2

# rebuild the report, print the cost, compare prompt versions
python -m harness report --run results/harness/dev-v3
python -m harness cost   --run results/harness/dev-v3
python -m harness compare --run results/harness/dev-v1 --run results/harness/dev-v2 `
    --run results/harness/dev-v3 --legacy --output results/harness/comparisons/prompt_versions
```

No model is needed to rebuild a report, a cost analysis, or the version
comparison from saved rows:

```powershell
python -m harness report --run results/harness/dev-v3-replay
```

Exit codes: `0` success, `1` the run recorded item failures, `2` a configuration
or dataset problem (nothing ran). An interrupted run keeps its completed rows:
re-run the same command with `--resume`.

## Results

```text
results/harness/<run_id>/
    metadata.json    configuration, dataset and prompt hashes, reproduction command
    system.jsonl     one row per item: reply, latency, tokens, warnings, error
    judge.jsonl      one row per graded reply: scores, reason, latency, usage
    items.jsonl      system + judge joined, exactly one row per evaluation item
    errors.jsonl     every categorised failure
    metrics.json     system, reliability, and performance metrics
    cost.json        per item, per 1,000 requests, run total, 100x projection
    report.md        human-readable summary
    prompts/         the exact prompt texts the run used
    position.jsonl   position-bias trials      (if that experiment ran)
    verbosity.jsonl  verbosity-bias deltas     (if that experiment ran)

results/harness/comparisons/prompt_versions.{json,md}
```

Committed results:

| Run                                               | What it shows                                                                                                                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dev-v1-replay`, `dev-v2-replay`, `dev-v3-replay` | the 40 development cases per prompt version, replayed from the saved replies and saved grades; average quality 7.850 / 7.875 / 7.925, identical to the saved judge comparison |
| `dev-v3-live-qwen25`                              | one full live run: 40 items with measured latency and token counts, plus position and verbosity experiments                                                                   |
| `comparisons/prompt_versions`                     | prompt version, average /8, delta, latency, tokens, cost in one table                                                                                                         |

Current findings, and their limits, are written up in
`docs/PERSON_2_HARNESS_IMPLEMENTATION.md`; the open gaps for each teammate are
in `docs/PERSON_2_HANDOFFS.md`. In short: the harness is complete and
reproducible, every score is currently model-assigned, and independent human
labels for the evaluated replies are still needed before judge-human agreement
can be reported.

---

# 17. Deliverables

The final project must contain:

- [x] 150+ golden dataset items — 160 in `data/golden.jsonl`, 0 invalid records
- [x] Labeling guide — `data/labeling_guide.md`
- [ ] Human labels — seeded for the 160 reference answers; the **evaluated replies still need independent review**
- [x] Human agreement measurement — 86.25% exact, 100% within one point (seeded labels)
- [x] Working evaluation harness - `harness/`, one command, 84 offline tests
- [x] Structured evaluation results — `results/harness/*/items.jsonl`, one row per item
- [x] LLM judge — `judge/`, rubric prompts v1 and v2
- [ ] Judge reliability measurement — human-vs-human done; **judge-vs-human blocked on the labels above**
- [x] Position-bias experiment — `python -m harness run --auto-pairs-from ... --position-repeats 2`
- [x] Verbosity-bias experiment — `python -m harness run --verbosity-limit N`
- [x] Prompt versions — `prompts/system_v1..v3.txt`
- [x] Prompt changelog — `prompts/CHANGELOG.md` with the measured effect of each change
- [x] Cost analysis — `cost.json` per run; USD figures are `null` while the local provider has no price
- [x] Latency measurements — per-phase mean/median/p95 in every `metrics.json`
- [x] Final report — `report.md`
- [x] Postmortem — `postmortem.md`

---

# 18. Current Status

| Component               | Status  | Notes                                                                                      |
| ----------------------- | ------- | ------------------------------------------------------------------------------------------ |
| Project structure       | Done    |                                                                                            |
| Task definition         | Defined |                                                                                            |
| Evaluation rubric       | Defined | `data/labeling_guide.md`                                                                   |
| Person 1 dataset        | Done    | 160 items, 0 invalid; dev/test split; seeded reference labels                              |
| Person 2 harness        | Done    | `harness/`, 5 commands, 84 tests, results in `results/harness/`                            |
| Person 3 judge          | Done    | `judge/`, rubric prompts v1/v2, saved comparison for all three versions                    |
| Person 4 system         | Done    | `system/`, prompts v1–v3, baselines, failure review                                        |
| Human labeling          | Partial | seeded reference labels only; the evaluated replies are **not** independently labeled      |
| Reliability experiments | Partial | position/verbosity screening runs exist; judge-human agreement blocked on the labels above |
| Prompt experiments      | Done    | v1/v2/v3 compared; 7.850 / 7.875 / 7.925 (model-assigned, dev split)                       |
| Cost and latency        | Done    | measured per run; USD figures `null` while the local provider has no price                 |
| Final report            | Done    | `report.md`; explicitly separates development evidence from final-test gaps                |
| Postmortem              | Done    | `postmortem.md`                                                                            |

---

# 19. Important Constraints

The project must follow these constraints:

- Minimum 150 golden items
- Two human labels per item
- One model call per item for the evaluated system
- No agents
- No retrieval during evaluation
- Structured evaluation output
- Prompts stored under version control
- No API keys in Git
- Results must be reproducible
- Judge reliability must be measured rather than assumed
- Real failure cases must be documented

---

# 20. Definition of Done

The project is complete when:

1. The golden dataset contains at least 150 items.
2. Human labeling and agreement are documented.
3. The evaluation harness can run the complete dataset.
4. The system produces a response for each item.
5. The LLM judge produces structured evaluations.
6. Judge reliability has been measured against humans.
7. Position bias has been tested.
8. Verbosity bias has been tested.
9. Prompt versions have been compared.
10. The final report and postmortem are complete; remaining evidence gaps are
    stated explicitly rather than hidden.

---

# 21. Contributions

| Member            | Contribution                                                                      |
| ----------------- | --------------------------------------------------------------------------------- |
| Rayen Zegden      | Person 1: golden dataset, split design, and labeling guide                        |
| Selim Garrach     | Person 2: evaluation harness, result schema, metrics, and tests                   |
| Mohamed Omar Abid | Person 3: LLM judge, structured grading, and reliability experiments              |
| Oussama Medimagh  | Person 4: prompted customer-support system, prompt versions, and failure analysis |

10. Cost and latency have been measured.
11. Results are reproducible from a clean repository.
12. The final report and postmortem are complete.
13. The team can demonstrate the harness and attempt to break the judge during the project demo.
