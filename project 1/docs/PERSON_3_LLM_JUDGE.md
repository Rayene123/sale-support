# Person 3 — LLM Judge & Reliability

## Role

**LLM Judge & Reliability Lead**

## Main Objective

Build and validate the LLM-based evaluator that scores customer-support responses.

The goal is not simply to create a judge, but to demonstrate that the judge produces reasonably reliable evaluations compared with humans.

---

# Dependencies

You need:

### From Person 1

- Labeling guide
- Evaluation rubric
- Human-labeled dataset
- Good/bad examples

### From Person 2

- Harness interface
- Evaluation result format

---

# 1. Design the Judge

The judge receives:

```text
Customer message
+
Order context
+
AI-generated response
+
Evaluation rubric
```

It must evaluate the response against the rubric.

The judge must not evaluate based on whether it personally prefers the wording.

It should focus on measurable criteria.

---

# 2. Judge Criteria

Use the project rubric:

| Criterion                | Score |
| ------------------------ | ----: |
| Factual correctness      |   0–2 |
| Completeness             |   0–2 |
| No hallucination         |   0–2 |
| Relevance                |   0–1 |
| Professional/polite tone |   0–1 |
| **Total**                | **8** |

The judge should provide:

- Individual criterion scores
- Total score
- Short reason

---

# 3. Structured Output

The judge should return a predictable structure.

Conceptually:

```text
{
  "factual_correctness": 2,
  "completeness": 2,
  "no_hallucination": 2,
  "relevance": 1,
  "professional_tone": 1,
  "total": 8,
  "reason": "..."
}
```

The final schema must be compatible with Person 2's harness.

---

# 4. Compare Against Humans

Use the human-labeled dataset to measure judge reliability.

Calculate:

- Human score
- Judge score
- Difference
- Agreement
- Major disagreements

Report both counts and percentages.

Do not only report one overall score.

---

# 5. Position Bias Test

Test whether the judge changes its evaluation depending on answer order.

For example:

### Version A

```text
Answer A
Answer B
```

### Version B

```text
Answer B
Answer A
```

The content must remain identical.

Compare the judge's verdicts.

Report:

- Number of tests
- Number of changed verdicts
- Percentage of changed verdicts

---

# 6. Verbosity Bias Test

Create padded versions of responses.

Example:

### Original

> Your order has shipped.

### Padded

> Your order has shipped. Thank you very much for contacting us. We truly appreciate your patience and hope that you have a wonderful day. Please do not hesitate to contact us again if you have any additional questions.

The additional text should not add useful factual information.

Compare judge scores.

The goal is to determine whether the judge rewards longer answers even when quality does not improve.

---

# 7. Judge Failure Analysis

Identify cases where the judge fails.

Possible failure types:

- Misses hallucination
- Rewards irrelevant detail
- Penalizes concise answers
- Fails to recognize missing information
- Gives inconsistent scores
- Misunderstands the rubric
- Changes score due to answer order
- Overweights politeness
- Overweights verbosity

Document real examples.

---

# 8. Judge Prompt Versioning

Store judge prompts under:

```text
prompts/
```

For example:

```text
prompts/judge_v1.txt
prompts/judge_v2.txt
```

Document changes in:

```text
prompts/CHANGELOG.md
```

Each change should explain:

- What changed
- Why it changed
- What result changed
- Whether reliability improved

---

# 9. Reliability Report

Create a result containing:

### Human Agreement

```text
Number of items:
Agreement:
Disagreement:
Agreement percentage:
```

### Judge Agreement

```text
Number of items:
Agreement:
Disagreement:
Agreement percentage:
```

### Position Bias

```text
Items tested:
Changed verdicts:
Percentage:
```

### Verbosity Bias

```text
Items tested:
Changed scores:
Average score change:
```

---

# 10. Handoffs

### To Person 2

Provide:

- Final judge input format
- Final output schema
- Judge prompt
- Reliability experiments

### To Person 4

Provide:

- Common system failure patterns
- Examples of hallucination
- Examples of incomplete responses
- Feedback about what the judge detects well/poorly

### To Person 1

Provide:

- Dataset cases where the rubric was ambiguous
- Cases requiring clarification
- Labeling guide improvements

---

# Definition of Done

- [ ] Judge prompt created
- [ ] Judge schema finalized
- [ ] Judge integrated with harness
- [ ] Human comparison completed
- [ ] Human-vs-judge agreement measured
- [ ] Position bias tested
- [ ] Verbosity bias tested
- [ ] Judge failures documented
- [ ] Judge prompt versioned
- [ ] Reliability results saved
- [ ] Results handed to Person 2
