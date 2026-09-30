# Evaluation run `dev-v3-live-qwen25`

- mode: `live`
- created: 2026-09-30T00:31:30.613727+00:00
- dataset: `C:\Users\flash\sale-support\project 1\data\dev.jsonl` (sha256 `9ef445a37f03`)
- items: 40 | system ok: 40 | failed: 0 | judged ok: 40
- system prompt: `v3` (sha256 `8d2509ddbded`) | model: `qwen2.5:14b`
- judge: `qwen2.5:14b` prompt `judge_v2` (sha256 `f1d4b25e4641`)
- label status: `seeded_unverified`

## What this run does and does not prove

- Metrics rebuilt from the saved rows of this run; no model was called.

## Reproduce

```powershell
python -m harness run --run-id dev-v3-live-qwen25 --output 'results\harness\dev-v3-live-qwen25' --dataset 'C:\Users\flash\sale-support\project 1\data\dev.jsonl' --labels 'C:\Users\flash\sale-support\project 1\data\human_labels.jsonl' --auto-pairs-from 'results\baseline_v1.jsonl' --system-prompt v3 --verbosity-limit 3 --position-limit 3 --position-repeats 2
```

```text
python -m harness run --run-id <new-id> --output results/harness/<new-id> ...
```

## Quality

- average total: **7.95 / 8**
- items with full marks: 39 of 40
- items below full marks: 1
- coverage: 100.0%

Score distribution:

| total | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8  |
|-------|---|---|---|---|---|---|---|---|----|
| items | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 39 |

Average by criterion:

| criterion           | average | maximum |
|---------------------|---------|---------|
| factual_correctness | 1.98    | 2       |
| completeness        | 1.98    | 2       |
| no_hallucination    | 2.00    | 2       |
| relevance           | 1.00    | 1       |
| professional_tone   | 1.00    | 1       |

Weakest criteria (points lost across graded items):

| criterion           | average | points lost | items not full marks |
|---------------------|---------|-------------|----------------------|
| factual_correctness | 1.98    | 1           | 1                    |
| completeness        | 1.98    | 1           | 1                    |
| no_hallucination    | 2.00    | 0           | 0                    |
| relevance           | 1.00    | 0           | 0                    |
| professional_tone   | 1.00    | 0           | 0                    |

## By scenario category

| category           | items | average /8 |
|--------------------|-------|------------|
| ambiguous_edge     | 4     | 8.00       |
| hallucination_trap | 4     | 8.00       |
| multi_part         | 4     | 8.00       |
| order_contents     | 5     | 8.00       |
| order_status       | 5     | 8.00       |
| payment_shipping   | 4     | 8.00       |
| prices_totals      | 5     | 7.60       |
| quantities         | 5     | 8.00       |
| unsupported_info   | 4     | 8.00       |

## By difficulty

| difficulty | items | average /8 |
|------------|-------|------------|
| easy       | 21    | 8.00       |
| hard       | 8     | 7.75       |
| medium     | 11    | 8.00       |

## Lowest scored items

_Only items below full marks are listed._

| item   | category      | total | judge reason                                                                                                   |
|--------|---------------|-------|----------------------------------------------------------------------------------------------------------------|
| P1-031 | prices_totals | 6     | The reply correctly states the line total for the Levi's 501 Original Jeans but does not account for the total |

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

| experiment     | state    | attempted | valid | changed | changed % | avg score change | judge calls |
|----------------|----------|-----------|-------|---------|-----------|------------------|-------------|
| position_bias  | measured | 3         | 3     | 2       | 66.7%     | n/a              | 12          |
| verbosity_bias | measured | 3         | 3     | 0       | 0.0%      | 0.00             | n/a         |

_Scores are model-assigned unless independent human review is attested; they are not a substitute for it._

## Performance

| phase  | requests | mean ms | p50 ms | p95 ms | max ms  |
|--------|----------|---------|--------|--------|---------|
| system | 40       | 5213.3  | 4492.3 | 8365.5 | 12810.5 |
| judge  | 40       | 8712.7  | 8489.1 | 9863.9 | 11277.4 |

- wall clock: 651.9 s (3.68 items/min)
- system tokens: prompt 33761, completion 1245, total 35006 (40 items with usage)
- judge tokens: prompt 42480, completion 2965, total 45445 (40 items with usage)
- experiment judge calls: 15, prompt 19486, completion 676, total 20162, mean 6041.4 ms
- judge arithmetic corrections applied: 4

## Cost

| phase       | status         | per item USD | per 1,000 USD | run total USD |
|-------------|----------------|--------------|---------------|---------------|
| system      | local_provider | n/a          | n/a           | n/a           |
| judge       | local_provider | n/a          | n/a           | n/a           |
| experiments | not_configured | n/a          | n/a           | n/a           |
| combined    | not_configured | n/a          | n/a           | n/a           |
| run_total   | not_configured | n/a          | n/a           | n/a           |

- 100x volume (4000 items): combined n/a USD
- local inference: `not_priced`
  - The evaluated system runs on a local provider; there is no API price.
  - The judge runs on local Ollama; there is no API price.
  - Set JUDGE_INPUT_PRICE_PER_M and JUDGE_OUTPUT_PRICE_PER_M to price the experiment calls on a hosted judge.
- Prices are operator estimates in USD per million tokens; verify them.
- Token usage is what the provider reported; missing usage is reported, not estimated.
- Replayed runs reuse the original run's latency and usage, so their cost is the cost of that original run, not of the report.
- Bias experiments are optional extras; read run_total, not combined, for what a run with experiments actually cost.
