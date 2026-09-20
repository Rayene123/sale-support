# Person 4 — Customer-Support AI System & Prompt Experiments

## Role

**Customer-Support AI System & Prompt Experiment Lead**

## Main Objective

Build the customer-support system that will be evaluated by the harness.

The system itself is not the primary deliverable. Its purpose is to provide something measurable for the evaluation harness.

---

# Dependencies

You need:

### From Person 1

- Dataset schema
- Customer message format
- Order context format
- Examples
- Task definition

### From Person 2

- Harness interface

### From Person 3

- Evaluation rubric
- Judge feedback
- Common failure patterns

---

# 1. Define the System Input

The system should receive information such as:

```text
Customer message
+
Order context
```

The order context may contain:

- Order ID
- Order status
- Products
- Quantities
- Prices
- Total

The system should not access external information during evaluation.

---

# 2. Define System Rules

The system should:

- Answer the customer's question directly
- Use only the supplied information
- Answer all parts of multi-part questions
- Avoid hallucinations
- State when information is unavailable
- Be polite and professional
- Avoid unnecessary verbosity
- Preserve exact factual information

The system should not invent:

- Delivery dates
- Tracking numbers
- Refund approvals
- Discounts
- Policies
- Product details
- Customer information

---

# 3. Create Baseline Prompt

Create the first prompt version:

```text
Prompt v1
```

The baseline should be intentionally simple.

Do not optimize it before measuring it.

The baseline evaluation gives the team something to compare against.

---

# 4. Run Baseline Evaluation

Run the baseline through the evaluation harness.

Record:

- Overall score
- Per-item scores
- Failures
- Cost
- Latency
- Common mistakes

Store the results under:

```text
results/
```

---

# 5. Analyze Failures

Look for patterns such as:

### Hallucination

The system invents information not present in the order context.

### Incomplete Answer

The customer asks three questions but the system answers only one.

### Incorrect Data

The system changes:

- Quantity
- Price
- Product name
- Order status
- Total

### Unsupported Assumption

The system assumes information that is not provided.

### Excessive Verbosity

The response contains unnecessary information.

---

# 6. Prompt Improvements

Create additional prompt versions.

Example:

```text
prompts/system_v1.txt
prompts/system_v2.txt
prompts/system_v3.txt
```

Each version should address a specific observed problem.

Do not change the prompt randomly.

Every modification should have a reason.

---

# 7. Prompt Changelog

Maintain:

```text
prompts/CHANGELOG.md
```

For every version record:

```text
Version:
Date:
Change:
Reason:
Previous score:
New score:
Cost change:
Latency change:
```

Example:

```text
v2

Change:
Added explicit instruction not to invent delivery dates.

Reason:
Baseline produced unsupported delivery estimates.

Result:
Score changed from X to Y.
```

---

# 8. Avoid Test Overfitting

Do not modify the prompt solely because of one specific test example.

Changes should address a general failure pattern.

For example:

Bad approach:

> Add a rule specifically for order #1042.

Good approach:

> Add a general rule requiring the model to answer only from supplied order context.

---

# 9. Compare Prompt Versions

For each version compare:

| Metric              |  V1 |  V2 |  V3 |
| ------------------- | --: | --: | --: |
| Average score       |     |     |     |
| Failed items        |     |     |     |
| Cost/item           |     |     |     |
| Latency             |     |     |     |
| Hallucination cases |     |     |     |

The goal is to show how prompt changes affect measurable system performance.

---

# 10. Handoffs

### To Person 2

Provide:

- System interface
- System input format
- Prompt versions
- System outputs
- Experiment results

### To Person 3

Provide:

- Baseline responses
- Improved responses
- Known failure cases
- Examples where judge decisions appear questionable

### To Person 1

Provide:

- Dataset cases that reveal missing scenarios
- New failure patterns
- Suggestions for additional difficult examples

---

# Definition of Done

- [ ] System input format finalized
- [ ] Baseline system created
- [ ] Baseline evaluated
- [ ] Failure patterns documented
- [ ] Prompt v2 created
- [ ] Additional prompt versions created if useful
- [ ] Every prompt change documented
- [ ] Prompt versions evaluated using same harness
- [ ] Cost measured
- [ ] Latency measured
- [ ] Test overfitting avoided
- [ ] Final prompt experiments handed to team
