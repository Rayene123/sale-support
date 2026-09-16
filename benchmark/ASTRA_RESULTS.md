# Astra chat evaluation

Dataset: `Data/items.jsonl`, 75 sentiment items. Uses the existing prompt definitions and exact-label scorer. The previous SQL dataset is not used.

Result: 73/75 (97.33%). Zero parse errors and zero execution errors.

This is a non-blind evaluation of answers authored in the current Codex conversation. The dataset labels were visible to the assistant before prediction. These are not 75 independent Astra API responses and this score is not a controlled comparison with the other model runs. API latency, tokens, and cost were not measured and remain blank. No API key was configured in the environment or repository .env.

| Item | Reference | Chat answer |
| --- | --- | --- |
| 030 | negative | mixed |
| 072 | mixed | negative |

030 explicitly praises timely arrival and criticizes the listing; the chat answer treats these as both sentiments. 072 describes functioning media and criticizes controls/software; the chat answer treats functioning media as factual rather than explicit praise. These are disagreements with the existing labels, which were preserved.

Reproduce scoring:

```powershell
python benchmark/src/score.py --results-dir benchmark/results/chat_evaluation
```

To import the saved answers into a fresh results folder:

```powershell
python benchmark/src/run.py --import-chat benchmark/chat_answers_astra.json --model gpt-6-astra --results-dir benchmark/results/chat_evaluation
```

Import refuses to overwrite the existing result file. The generated CSVs and summary are in `results/chat_evaluation`, separate from the measured results.

## API adapter

The runner now supports PROVIDERS=openai and OPENAI_MODEL=gpt-6-astra with OPENAI_API_KEY supplied through the environment or .env. Install openai and python-dotenv before use. Run `python benchmark/src/run.py`. It uses the Responses API, the unchanged classification messages, low reasoning effort, 256 maximum output tokens, a 120-second timeout, and no SDK retries. Temperature is omitted; this configuration differs from the other providers' explicit temperature=0 and must be disclosed. Reasoning shares the output-token budget, so inspect truncations before deciding on a common budget for new comparative runs. The live API adapter has only been tested with a mock response; model access and successful live requests remain unverified. Do not treat the chat result as evidence the API adapter ran.

Official model reference: https://developers.openai.com/api/docs/models/gpt-6-astra

Scorer fixes: execution errors are counted separately from invalid labels; latency includes requests with invalid output or errors when recorded; missing token measurements remain blank. Existing teammate result files and their summary were not rescored or overwritten.
