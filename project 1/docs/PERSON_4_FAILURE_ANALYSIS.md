# Person 4 — Failure Analysis

## 1. Purpose

This document analyzes failures observed during the customer-support prompt experiments.

The analysis focuses on the failure categories defined for Person 4:

- Hallucination
- Incomplete answer
- Incorrect data
- Unsupported assumption
- Excessive verbosity

The goal is to identify general failure patterns and use them to improve the system prompt without overfitting to individual test cases.

The development set contains 40 cases, evaluated using the same system and harness across prompt versions v1, v2, and v3.

---

## 2. Prompt Versions

### v1 — Baseline

The first prompt established the basic behavior:

- Answer using the order context.
- Do not invent information.
- State unavailable information.
- Answer multi-part questions.
- Be concise and professional.

The purpose of v1 was to establish a simple baseline before adding stronger constraints.

### v2 — Explicit Grounding

v2 strengthened the baseline by explicitly requiring the model to:

- Use only explicitly provided information.
- Avoid inferred policies and outcomes.
- Avoid claims about external systems.
- Preserve exact order facts.
- Distinguish product types from total units.
- Avoid unrelated order information.

### v3 — Stronger Anti-Inference Rules

v3 further strengthened grounding by explicitly prohibiting inference of:

- Refund approvals
- Refund outcomes
- Shipping or delivery events
- Delivery dates
- Tracking information
- Address-change eligibility
- Store policies
- Permissions
- Actions taken

It also instructed the model to state information as unavailable when the requested fact could not be directly determined from the context.

---

## 3. Main Failure Patterns

### 3.1 Unsupported Policies and Refund Claims

One of the clearest baseline failures was the generation of policies that were not present in the order context.

For example, in P1-007, the baseline response stated that a refund could not be approved while the order was processing and that refunds were only issued under certain conditions.

This introduced a store policy that was not supplied by the dataset.

The v3 response instead stated that there was no information available about approving a refund for the order.

**Failure category:**
- Hallucination
- Unsupported assumption

**Prompt improvement:**

The later prompts explicitly prohibit inventing refund policies, refund approvals, and refund outcomes.

---

### 3.2 Inferring Actions From Order Status

Another recurring issue was treating an order status as proof of an action or permission.

For example, P1-016 resulted in a response stating that the shipping address could not be changed because the order had already been delivered.

The order status provides information about the order, but it does not necessarily provide a policy determining whether an address can be changed.

**Failure category:**
- Unsupported assumption

**Required behavior:**

The system should only state that an address change is possible or impossible when the context explicitly provides that information.

Otherwise, it should state that the requested information is unavailable.

---

### 3.3 Unsupported Refund Status

P1-018 produced a response stating that the cancelled order's payment had already been refunded.

A cancelled status does not by itself establish that a refund occurred unless the context explicitly contains that information.

**Failure category:**
- Hallucination
- Unsupported assumption

**Prompt improvement:**

v3 explicitly states that the model must not infer refund outcomes from order status.

---

### 3.4 Claims About External Actions or Systems

Some baseline responses suggested that the assistant could perform or check actions outside the supplied order context.

For example, an earlier response for P1-025 suggested that the assistant could check the order status again.

The system does not have access to external shipping systems or other external sources in this task.

**Failure category:**
- Hallucination
- Unsupported action

**Prompt improvement:**

v2 and v3 explicitly prohibit claiming access to:

- Shipping systems
- Websites
- Emails
- External databases
- Other external information sources

---

### 3.5 Incomplete Answers to Multi-Part Questions

Some responses answered only part of what the customer requested.

For example, P1-011's v3 response listed the products in the order but did not include the quantities.

When the customer's question requires multiple pieces of information, the response should provide every part that can be answered from the context.

**Failure category:**
- Incomplete answer

**Prompt improvement:**

v2 and v3 explicitly require the assistant to answer every part of a multi-part question that can be answered from the supplied context.

---

### 3.6 Unnecessary Information

Some responses provide more order information than is necessary for the customer's question.

For example, P1-036 produces a broad order summary even though the requested information may be narrower.

This does not necessarily make the response factually incorrect, but it can reduce relevance and conciseness.

**Failure category:**
- Excessive verbosity
- Relevance issue

**Prompt improvement:**

v2 introduced an explicit rule not to add unrelated order information unless it is necessary to answer the customer's question.

---

### 3.7 Quantity Interpretation

Quantity questions require distinguishing between:

1. Number of distinct product types
2. Total number of units

P1-003 demonstrates the intended behavior: the response identifies both the number of distinct product types and the total number of units.

P1-039 also correctly identifies that the order contains three units of the same product.

However, quantity questions remain an area that requires explicit instructions because the terms "items," "products," and "units" can be interpreted differently.

**Failure category:**
- Potential incomplete answer
- Quantity interpretation ambiguity

**Prompt improvement:**

v2 and v3 explicitly instruct the model to distinguish product types from total units.

---

### 3.8 Output Encoding / Character Corruption

The v3 result file contains several malformed characters, for example:

- `ORDÔÇæ10002`
- `LeviÔÇÖs`
- `ÔÇô`
- `Ôé¼`

These appear in otherwise structurally correct responses.

This should be tracked separately from semantic hallucination because the issue concerns character encoding/presentation rather than the model inventing information.

Examples appear in P1-002, P1-005, P1-038, P1-039, and P1-040.

**Failure category:**
- Output/data presentation issue

**Action:**

Verify the encoding used when writing, reading, and displaying JSONL result files. Results should be consistently handled as UTF-8.

---

## 4. Examples of Improvements

### P1-007 — Refund

**Baseline behavior:**

The response inferred refund rules and conditions that were not present in the context.

**v3 behavior:**

The response states that information about approving a refund is unavailable.

**Observed improvement:**

The prompt successfully reduced unsupported policy inference.

---

### P1-010 — Shipping Status

The v3 response directly states that the order has not shipped and gives its current status.

This is preferable to inferring a future delivery date or shipping event.

**Observed behavior:**

- Direct answer
- Uses supplied status
- Does not invent a delivery date

---

### P1-017 — Delivery Information

The response correctly states that the delivery date and tracking information are unavailable.

However, it also suggests contacting the courier.

This should be treated cautiously because the system is instructed to rely only on the supplied context.

**Failure category:**

- Unsupported recommendation/action

**Potential improvement:**

When requested information is unavailable, simply state that it is unavailable unless the context explicitly provides a next action.

---

## 5. Summary of Remaining Issues

After the prompt improvements, the main remaining areas to monitor are:

| Failure Pattern | Status |
|---|---|
| Invented refund policies | Reduced |
| Invented refund outcomes | Still possible |
| Unsupported address-change conclusions | Still possible |
| External-system claims | Reduced |
| Incomplete multi-part answers | Still possible |
| Unnecessary order information | Still possible |
| Quantity interpretation | Improved |
| Encoding problems | Still present |
| Unsupported recommendations | Still possible |

The results show that stronger grounding instructions address several important baseline failures, but they do not eliminate all unsupported inference or completeness issues.

---

## 6. Prompt Design Lessons

The experiments produced the following general lessons:

### 6.1 Explicit grounding is important

A general instruction such as "do not hallucinate" is useful, but explicit restrictions on common inference patterns provide stronger guidance.

Examples include explicitly prohibiting assumptions about:

- Refunds
- Delivery dates
- Tracking
- Policies
- Permissions
- External actions

### 6.2 Unavailable information should remain unavailable

The model should not replace missing information with a related fact.

For example:

- Missing delivery date → do not provide an estimated date.
- Missing tracking number → do not invent one.
- Missing refund status → do not infer a refund.
- Missing policy → do not create a policy.

### 6.3 Prompt changes should target general patterns

The improvements were designed around recurring failure categories rather than individual order IDs.

For example, instead of adding a rule for a single refund question, the prompt was strengthened to prohibit unsupported refund inference generally.

This follows the project's requirement to avoid test overfitting.

---

## 7. Runtime Experiment Results

All three prompt versions were evaluated on the same 40-case development set.

| Metric | v1 | v2 | v3 |
|---|---:|---:|---:|
| Cases | 40 | 40 | 40 |
| Average latency | 3908 ms | 4570 ms | 5757 ms |
| Average prompt tokens | 562.65 | 717.65 | 860.65 |
| Average completion tokens | 149.00 | 165.30 | 134.93 |
| Average total tokens | 711.65 | 882.95 | 995.58 |
| Total tokens | 28,466 | 35,318 | 39,823 |
| Quality score (/8) | TBD | TBD | TBD |

The `/8` quality scores are intentionally left as **TBD** because the official quality judging is part of the team's evaluation process and should not be replaced by an unofficial Person 4 score.

---

## 8. Limitations

This analysis is based on the available development-set outputs.

The current results establish observed failure patterns, but they do not by themselves provide an official quality ranking between v1, v2, and v3.

Official quality comparison should use the project's evaluation process and the designated judge/human evaluation results.

Runtime metrics such as latency and token usage are separate from the response-quality score.

---

## 9. Conclusion

The prompt experiments progressively strengthened the customer-support system's grounding behavior.

The main improvement was moving from a general "do not hallucinate" instruction toward explicit rules covering common unsupported inferences such as refunds, delivery information, tracking, policies, permissions, and external actions.

v3 represents the most constrained prompt version currently implemented. Remaining work is to combine these failure findings with the official evaluation results, update the prompt changelog with the measured results, and provide the final prompt versions and failure cases to the rest of the team.