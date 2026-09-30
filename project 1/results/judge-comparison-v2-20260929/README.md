# Persona 3: system-prompt comparison

**v1, v2 and v3 are system prompt versions, not judge versions.**

| System prompt | Judge / prompt | Answers | Average /8 | Read full answers |
| --- | --- | ---: | ---: | --- |
| v1 | qwen3:14b / judge_v2 | 40 | 7.850 | [Report](v1/report.md) |
| v2 | qwen3:14b / judge_v2 | 40 | 7.875 | [Report](v2/report.md) |
| v3 | qwen3:14b / judge_v2 | 40 | 7.925 | [Report](v3/report.md) |

## Interpretation

- Development-set comparison only; no final test-set evaluation.
- Scores are model judgments, not demonstrated judge accuracy.
- Independent human scoring of these exact replies remains pending.
- Position and verbosity experiments did not run in these saved comparisons. Person 2 has separate screening results under `../harness/`.

## File map

- `v*/report.md`: human-readable questions, exact answers, criterion scores, reasons and context.
- `v*/results.jsonl`: original machine-readable evidence; preserved unchanged for the harness.
- `v*/metadata.json`: model settings and input hashes.
- `v*/reliability.json` and `comparison.json`: machine-readable summaries.
- The active judge implementation and prompts are in `project 1/judge/`.

Regenerate the Markdown without model calls, from `project 1`:

```powershell
python -m judge.readable --run results/judge-comparison-v2-20260929
```
