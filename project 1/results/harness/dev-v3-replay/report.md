# Evaluation run `dev-v3-replay`

- mode: `replay`
- created: 2026-09-30T00:30:58.137091+00:00
- dataset: `data\dev.jsonl` (sha256 `9ef445a37f03`)
- items: 40 | system ok: 40 | failed: 0 | judged ok: 40
- system prompt: `v3` (sha256 `8d2509ddbded`) | model: `qwen2.5:14b`
- judge: `qwen3:14b` prompt `judge_v2` (sha256 `f1d4b25e4641`)
- label status: `seeded_unverified`

## What this run does and does not prove

- Metrics rebuilt from the saved rows of this run; no model was called.

## Reproduce

```powershell
python -m harness run --run-id dev-v3-replay --output 'results\harness\dev-v3-replay' --dataset 'data\dev.jsonl' --system-source 'results\baseline_v3.jsonl' --judge-source 'results\judge-comparison-v2-20260929\v3\results.jsonl' --labels 'C:\Users\flash\sale-support\project 1\data\human_labels.jsonl' --system-prompt v3
```

```text
python -m harness run --run-id <new-id> --output results/harness/<new-id> ...
```

## Quality

- average total: **7.92 / 8**
- items with full marks: 38 of 40
- items below full marks: 2
- coverage: 100.0%

Score distribution:

| total | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8  |
|-------|---|---|---|---|---|---|---|---|----|
| items | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 38 |

Average by criterion:

| criterion           | average | maximum |
|---------------------|---------|---------|
| factual_correctness | 2.00    | 2       |
| completeness        | 1.93    | 2       |
| no_hallucination    | 2.00    | 2       |
| relevance           | 1.00    | 1       |
| professional_tone   | 1.00    | 1       |

Weakest criteria (points lost across graded items):

| criterion           | average | points lost | items not full marks |
|---------------------|---------|-------------|----------------------|
| factual_correctness | 2.00    | 0           | 0                    |
| completeness        | 1.93    | 3           | 2                    |
| no_hallucination    | 2.00    | 0           | 0                    |
| relevance           | 1.00    | 0           | 0                    |
| professional_tone   | 1.00    | 0           | 0                    |

## By scenario category

| category           | items | average /8 |
|--------------------|-------|------------|
| ambiguous_edge     | 4     | 8.00       |
| hallucination_trap | 4     | 7.50       |
| multi_part         | 4     | 8.00       |
| order_contents     | 5     | 8.00       |
| order_status       | 5     | 7.80       |
| payment_shipping   | 4     | 8.00       |
| prices_totals      | 5     | 8.00       |
| quantities         | 5     | 8.00       |
| unsupported_info   | 4     | 8.00       |

## By difficulty

| difficulty | items | average /8 |
|------------|-------|------------|
| easy       | 21    | 8.00       |
| hard       | 8     | 7.62       |
| medium     | 11    | 8.00       |

## Lowest scored items

_Only items below full marks are listed._

| item   | category           | total | judge reason                                                                                                   |
|--------|--------------------|-------|----------------------------------------------------------------------------------------------------------------|
| P1-026 | hallucination_trap | 6     | The response correctly states the discount amount from the context, but fails to address the refund question.  |
| P1-001 | order_status       | 7     | The response correctly states the order status and payment status based on the context. It is relevant to the  |

## Failures

_no data_

## Judge reliability

Human vs human (total score):

| comparisons | exact agreement | within 1 point | mean abs diff | kappa | kappa (linear) |
|-------------|-----------------|----------------|---------------|-------|----------------|
| 160         | 86.2%           | 100.0%         | 0.14          | 0.00  | 0.00           |

Kappa at or near zero here does not mean the raters disagreed: it means chance agreement already explains the observed agreement, which happens when one evaluator's ratings have no variance. Read the raw columns, not kappa.

Coverage: 0 labelled of 40 graded; unlabelled 40 (seeded_unverified).
Bias experiments:

| experiment     | state   | attempted | valid | changed | changed % | avg score change | judge calls |
|----------------|---------|-----------|-------|---------|-----------|------------------|-------------|
| position_bias  | not_run | 0         | 0     | n/a     | not run   | n/a              | n/a         |
| verbosity_bias | not_run | 0         | 0     | n/a     | not run   | n/a              | n/a         |

_Scores are model-assigned unless independent human review is attested; they are not a substitute for it._

## Performance

| phase  | requests | mean ms | p50 ms  | p95 ms  | max ms  |
|--------|----------|---------|---------|---------|---------|
| system | 40       | 5757.3  | 6187.4  | 9859.1  | 16081.5 |
| judge  | 40       | 14593.5 | 14175.8 | 16550.7 | 20978.9 |

- wall clock: not measured (this run replayed saved results and made no model calls)
- system tokens: prompt 34426, completion 5397, total 39823 (40 items with usage)
- judge tokens: prompt 43850, completion 4417, total 48267 (40 items with usage)
- experiment judge calls: n/a (no bias experiment ran in this run)
- judge arithmetic corrections applied: 0

## Cost

| phase       | status         | per item USD | per 1,000 USD | run total USD |
|-------------|----------------|--------------|---------------|---------------|
| system      | local_provider | n/a          | n/a           | n/a           |
| judge       | local_provider | n/a          | n/a           | n/a           |
| experiments | not_run        | n/a          | n/a           | n/a           |
| combined    | not_configured | n/a          | n/a           | n/a           |
| run_total   | not_configured | n/a          | n/a           | n/a           |

- 100x volume (4000 items): combined n/a USD
- local inference: `not_measured`
  - The evaluated system runs on a local provider; there is no API price.
  - The judge runs on local Ollama; there is no API price.
- Prices are operator estimates in USD per million tokens; verify them.
- Token usage is what the provider reported; missing usage is reported, not estimated.
- Replayed runs reuse the original run's latency and usage, so their cost is the cost of that original run, not of the report.
- Bias experiments are optional extras; read run_total, not combined, for what a run with experiments actually cost.
