# CS496 AI Engineering — Project 1

## The Grader

**Course:** CS496 — AI Engineering
**Project:** Project 1 — The Grader
**Team Size:** 4
**Task:** Customer-support reply evaluation

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
project1-grader/
│
├── README.md
│
├── docs/
│   ├── PERSON_1_DATASET.md
│   ├── PERSON_2_HARNESS.md
│   ├── PERSON_3_LLM_JUDGE.md
│   └── PERSON_4_SYSTEM.md
│
├── data/
│   ├── golden.jsonl
│   ├── dev.jsonl
│   ├── test.jsonl
│   ├── human_labels.jsonl
│   └── labeling_guide.md
│
├── harness/
│   └── ...
│
├── system/
│   └── ...
│
├── prompts/
│   ├── system_v1.txt
│   ├── system_v2.txt
│   ├── judge_v1.txt
│   └── CHANGELOG.md
│
├── results/
│   ├── baseline.json
│   ├── prompt_v2.json
│   ├── prompt_v3.json
│   └── ...
│
└── report/
    ├── report.pdf
    └── postmortem.md
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

The README will eventually contain:

### Installation

```text
TODO
```

### Run Evaluation

```text
TODO
```

### Results

```text
TODO
```

The final version of this README must replace these placeholders with the actual commands.

---

# 17. Deliverables

The final project must contain:

- [ ] 150+ golden dataset items
- [ ] Labeling guide
- [ ] Human labels
- [ ] Human agreement measurement
- [ ] Working evaluation harness
- [ ] Structured evaluation results
- [ ] LLM judge
- [ ] Judge reliability measurement
- [ ] Position-bias experiment
- [ ] Verbosity-bias experiment
- [ ] Prompt versions
- [ ] Prompt changelog
- [ ] Cost analysis
- [ ] Latency measurements
- [ ] Final report
- [ ] Postmortem

---

# 18. Current Status

| Component               | Status  |
| ----------------------- | ------- |
| Project structure       | Done    |
| Task definition         | Defined |
| Evaluation rubric       | Defined |
| Person 1 dataset        | To do   |
| Person 2 harness        | To do   |
| Person 3 judge          | To do   |
| Person 4 system         | To do   |
| Human labeling          | To do   |
| Reliability experiments | To do   |
| Prompt experiments      | To do   |
| Final report            | To do   |

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
10. Cost and latency have been measured.
11. Results are reproducible from a clean repository.
12. The final report and postmortem are complete.
13. The team can demonstrate the harness and attempt to break the judge during the project demo.
