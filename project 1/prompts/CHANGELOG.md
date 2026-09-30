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

The three versions were evaluated on the same 40 development cases, with the
evaluation harness (`harness/`) replaying the saved replies and the saved judge
grades. Reproduce with:

```powershell
python -m harness run --system-source results/baseline_v1.jsonl --system-prompt v1 `
    --judge-source results/judge-comparison-v2-20260929/v1/results.jsonl `
    --run-id dev-v1-replay --output results/harness/dev-v1-replay
python -m harness compare --legacy --run results/harness/dev-v1-replay `
    --run results/harness/dev-v2-replay --run results/harness/dev-v3-replay `
    --output results/harness/comparisons/prompt_versions
```

Objective runtime/token measurements (one laptop, local Ollama):

| Metric | v1 | v2 | v3 |
|---|---:|---:|---:|
| Cases | 40 | 40 | 40 |
| Average latency | 3908 ms | 4570 ms | 5757 ms |
| Average prompt tokens | 562.65 | 717.65 | 860.65 |
| Average completion tokens | 149.00 | 165.30 | 134.93 |
| Average total tokens | 711.65 | 882.95 | 995.58 |
| Total tokens | 28,466 | 35,318 | 39,823 |
| Average quality (/8) — model-assigned | 7.850 | 7.875 | 7.925 |
| Δ vs v1 | — | +0.025 | +0.075 |
| Factual correctness (of 2) | 1.950 | 1.950 | 2.000 |
| Completeness (of 2) | 1.950 | 1.975 | 1.925 |
| No hallucination (of 2) | 1.950 | 1.950 | 2.000 |
| Relevance (of 1) | 1.000 | 1.000 | 1.000 |
| Professional tone (of 1) | 1.000 | 1.000 | 1.000 |

Cost per version: `null` / not configured. These runs used a local Ollama model,
which has no API price; the harness reports `local_provider` and `null` rather
than a zero cost. See `docs/PERSON_2_HARNESS_IMPLEMENTATION.md`.

**Caveats on the quality column.** The scores are assigned by the LLM judge, not
by independent humans: the human labels on file cover the reference answers, not
these replies, so judge-versus-human agreement is still pending. The v1→v3 gap
is 0.075 points out of 8 across 40 items, and the dev split is the split these
prompts were developed against. Treat the ordering as a direction, not a
measurement, and confirm it on the untouched 120-item test split before
publishing a claim.

**Prompt version label bug.** `results/baseline_v2.jsonl` records
`prompt_version: v1` on all 40 rows although those rows are v2 replies. The
harness flags this as `prompt_version_mismatch` on every row of
`results/harness/dev-v2-replay/system.jsonl` instead of silently relabelling
them; the source file should still be corrected to `v2`.