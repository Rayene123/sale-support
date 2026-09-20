# Person 2 — Evaluation Harness

## Role

**Evaluation Harness Lead**

## Main Objective

Build the evaluation infrastructure that runs the system against the dataset and produces structured, reproducible evaluation results.

The harness is the main deliverable of the project.

---

# Dependencies

You will receive:

### From Person 1

- Dataset schema
- `golden.jsonl`
- `dev.jsonl`
- `test.jsonl`
- Labeling guide

### From Person 3

- LLM judge interface
- Judge output schema
- Judge prompt

### From Person 4

- System interface
- System prompt
- System output format

---

# 1. Define the Evaluation Pipeline

The final pipeline should conceptually be:

```text
Dataset
   ↓
System
   ↓
Generated Answer
   ↓
LLM Judge
   ↓
Structured Evaluation
   ↓
Results
   ↓
Metrics
```

The harness should make this process reproducible.

---

# 2. Dataset Loader

The harness must:

- Read JSONL files
- Validate required fields
- Handle malformed records
- Assign a unique ID to every item
- Support dev/test/golden datasets

Do not silently ignore invalid records.

Errors should be recorded clearly.

---

# 3. System Runner

The harness should be able to run the evaluated customer-support system on every item.

For every item record:

- Input
- System output
- Execution time
- Error status if applicable
- Token/cost information if available

There should be one result per evaluation item.

---

# 4. Judge Runner

Send the generated response to the LLM judge.

The judge should receive:

- Customer message
- Order context
- Generated response
- Evaluation rubric

Store:

- Score
- Reason
- Judge response
- Latency
- Cost if available
- Parsing/validation errors

---

# 5. Structured Results

The harness should produce structured output.

Example conceptual result:

```text
{
  "id": "001",
  "system_output": "...",
  "score": 7,
  "reason": "...",
  "latency_ms": 1200,
  "cost": 0.003
}
```

The exact schema should be finalized with Person 3.

---

# 6. Metrics

Calculate at minimum:

### System Metrics

- Average score
- Score distribution
- Per-item score
- Number of failed items

### Reliability Metrics

- Judge-human agreement
- Position-bias result
- Verbosity-bias result

### Performance Metrics

- Average latency
- Total evaluation time
- Cost per item
- Cost per 1,000 requests

Also calculate projected cost at approximately **100× current evaluation volume**.

---

# 7. Error Handling

The harness must distinguish between:

- Dataset errors
- System errors
- Judge errors
- Invalid judge output
- API errors
- Timeout
- Missing fields

A single failed item should not necessarily stop the entire evaluation.

Record failures so they can be analyzed later.

---

# 8. One-Command Execution

The project must eventually support a simple command such as:

```text
run evaluation
```

The exact command can be chosen later.

The README should explain:

1. Installation
2. Configuration
3. Dataset location
4. Evaluation command
5. Result location

---

# 9. Reproducibility

A clean clone of the repository should be able to reproduce the evaluation.

Do not commit:

- API keys
- Passwords
- Tokens
- Private credentials

Use environment variables where necessary.

---

# 10. Prompt Version Tracking

The harness should make it easy to compare:

```text
Prompt v1
Prompt v2
Prompt v3
```

For every experiment record:

- Prompt version
- Dataset split
- Score
- Cost
- Latency
- Date/run identifier

This allows Person 4 to demonstrate whether prompt changes actually improved the system.

---

# 11. Results

Store evaluation outputs in:

```text
results/
```

Possible result files:

```text
results/baseline.json
results/prompt_v2.json
results/prompt_v3.json
results/judge_reliability.json
results/cost_analysis.json
```

---

# 12. Handoffs

### To Person 1

Provide:

- Dataset validation feedback
- Invalid/missing records
- Dataset statistics

### To Person 3

Provide:

- Judge outputs
- Human-vs-judge comparison data
- Position-swap results
- Verbosity-padding results

### To Person 4

Provide:

- Prompt experiment scores
- Per-item failures
- Cost
- Latency
- Score changes between versions

### To Everyone

Provide:

- Final evaluation results
- Reproducible command
- Metrics
- Error logs

---

# Definition of Done

- [ ] Dataset loader works
- [ ] System can be evaluated automatically
- [ ] Judge can be called automatically
- [ ] Structured results generated
- [ ] One result exists per item
- [ ] Errors are recorded
- [ ] Score statistics calculated
- [ ] Cost calculated
- [ ] Latency calculated
- [ ] Prompt versions can be compared
- [ ] Evaluation can run from a clean clone
- [ ] No secrets committed
- [ ] Final results stored in `results/`
