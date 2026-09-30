# Evaluation run `dev-v1-replay`

- mode: `replay`
- created: 2026-09-30T00:30:57.713319+00:00
- dataset: `data\dev.jsonl` (sha256 `9ef445a37f03`)
- items: 40 | system ok: 40 | failed: 0 | judged ok: 40
- system prompt: `v1` (sha256 `06a19d6320fc`) | model: `qwen2.5:14b`
- judge: `qwen3:14b` prompt `judge_v2` (sha256 `f1d4b25e4641`)
- label status: `seeded_unverified`

## What this run does and does not prove

- Metrics rebuilt from the saved rows of this run; no model was called.

## Reproduce

```powershell
python -m harness run --run-id dev-v1-replay --output 'results\harness\dev-v1-replay' --dataset 'data\dev.jsonl' --system-source 'results\baseline_v1.jsonl' --judge-source 'results\judge-comparison-v2-20260929\v1\results.jsonl' --labels 'C:\Users\flash\sale-support\project 1\data\human_labels.jsonl' --system-prompt v1
```

```text
python -m harness run --run-id <new-id> --output results/harness/<new-id> ...
```

## Quality

- average total: **7.85 / 8**
- items with full marks: 38 of 40
- items below full marks: 2
- coverage: 100.0%

Score distribution:

| total | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8  |
|-------|---|---|---|---|---|---|---|---|----|
| items | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 38 |

Average by criterion:

| criterion           | average | maximum |
|---------------------|---------|---------|
| factual_correctness | 1.95    | 2       |
| completeness        | 1.95    | 2       |
| no_hallucination    | 1.95    | 2       |
| relevance           | 1.00    | 1       |
| professional_tone   | 1.00    | 1       |

Weakest criteria (points lost across graded items):

| criterion           | average | points lost | items not full marks |
|---------------------|---------|-------------|----------------------|
| factual_correctness | 1.95    | 2           | 1                    |
| completeness        | 1.95    | 2           | 2                    |
| no_hallucination    | 1.95    | 2           | 1                    |
| relevance           | 1.00    | 0           | 0                    |
| professional_tone   | 1.00    | 0           | 0                    |

## By scenario category

| category           | items | average /8 |
|--------------------|-------|------------|
| ambiguous_edge     | 4     | 7.75       |
| hallucination_trap | 4     | 8.00       |
| multi_part         | 4     | 8.00       |
| order_contents     | 5     | 8.00       |
| order_status       | 5     | 8.00       |
| payment_shipping   | 4     | 8.00       |
| prices_totals      | 5     | 8.00       |
| quantities         | 5     | 8.00       |
| unsupported_info   | 4     | 6.75       |

## By difficulty

| difficulty | items | average /8 |
|------------|-------|------------|
| easy       | 21    | 7.95       |
| hard       | 8     | 8.00       |
| medium     | 11    | 7.55       |

## Lowest scored items

_Only items below full marks are listed._

| item   | category         | total | judge reason                                                                                                   |
|--------|------------------|-------|----------------------------------------------------------------------------------------------------------------|
| P1-007 | unsupported_info | 3     | The response incorrectly assumes that refunds are only issued after completion or cancellation, which is not s |
| P1-009 | ambiguous_edge   | 7     | The response correctly states the order status as 'shipped' based on the context. It does not make unsupported |

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
| system | 40       | 3908.3  | 4583.6  | 7629.0  | 7717.3  |
| judge  | 40       | 16619.6 | 16417.9 | 20765.0 | 22181.8 |

- wall clock: not measured (this run replayed saved results and made no model calls)
- system tokens: prompt 22506, completion 5960, total 28466 (40 items with usage)
- judge tokens: prompt 44879, completion 4584, total 49463 (40 items with usage)
- experiment judge calls: n/a (no bias experiment ran in this run)
- judge arithmetic corrections applied: 1

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
