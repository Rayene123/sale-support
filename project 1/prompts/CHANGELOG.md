# Prompt Changelog

## v1

**Date:** September 2026

**Change:**
Created the initial baseline customer-support prompt.

**Reason:**
Establish an intentionally simple baseline before prompt optimization.

**Observed failure patterns:**
- Unsupported refund policies and outcomes
- Unsupported assumptions about order actions
- Claims involving external systems
- Incomplete answers for some multi-part questions
- Excessive inclusion of unrelated order information
- Quantity interpretation ambiguity

**Result:**
Baseline used for comparison with subsequent prompt versions.

---

## v2

**Date:** September 2026

**Change:**
Added explicit grounding and anti-hallucination instructions:
- Use only information explicitly provided in the order context.
- Do not infer policies, refunds, delivery dates, tracking information,
  permissions, or actions.
- Do not claim access to external systems.
- Preserve exact order facts.
- Distinguish product types from total units.
- Avoid unrelated order information.

**Reason:**
Address general failure patterns observed in the baseline rather than
overfitting to individual test cases.

**Result:**
Evaluated on the same 40-case development set.

---

## v3

**Date:** September 2026

**Change:**
Strengthened the distinction between explicitly supported facts and
inferred consequences.

Added explicit rules requiring the assistant to:
- answer every part of multi-part questions;
- state information as unavailable when it cannot be determined;
- avoid replacing unavailable requested information with related facts;
- avoid inferred policies, outcomes, actions, and permissions;
- preserve exact factual information.

**Reason:**
V2 required stronger protection against unsupported inference while
maintaining concise responses.

**Observed result:**
Several baseline hallucination patterns were reduced. For example,
the refund-policy hallucination in P1-007 was replaced with an
explicit statement that refund-approval information was unavailable.

However, some failures remained, including unsupported address/refund
inferences and occasional incomplete answers.

---

## Experiment Notes

The three versions were evaluated on the same 40 development cases.

Objective runtime/token measurements:

| Metric | v1 | v2 | v3 |
|---|---:|---:|---:|
| Cases | 40 | 40 | 40 |
| Average latency | 3908 ms | 4570 ms | 5757 ms |
| Average prompt tokens | 562.65 | 717.65 | 860.65 |
| Average completion tokens | 149.00 | 165.30 | 134.93 |
| Average total tokens | 711.65 | 882.95 | 995.58 |
| Total tokens | 28,466 | 35,318 | 39,823 |
| Average quality (/8) | TBD | TBD | TBD |

Quality scores will be added from the evaluation/judge results.