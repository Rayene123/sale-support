# Person 2 handoff: use the Person 3 judge

The judge is on branch `persona-3` under `project 1/judge/`. Merge that branch or otherwise bring its `project 1/judge/` folder into your checkout. Nothing in the Person 3 implementation changes Person 4's system code.

## Quick start

The default judge runs on local Ollama, with no API key. Install/run Ollama and install the model once if needed:

```powershell
ollama pull qwen3:14b
```

From `project 1`, copy the example config once, then run a two-response pilot:

```powershell
Copy-Item judge/.env.example judge/.env
python -m judge.run --responses results/baseline_v1.jsonl --limit 2 --output results/judge-v1-pilot
```

The `.env` file is local and ignored by Git. It must keep `JUDGE_PROVIDER=ollama`, `JUDGE_MODEL=qwen3:14b`, and a blank `JUDGE_API_KEY=` for local grading. This model took about 118 seconds for one cold request on Person 3's laptop; measure warm-run time before committing to a large batch. The pilot uses saved Person 4 output and sends requests only to the machine running Ollama.

The runner reads the saved baseline's UTF-16 JSONL and adapts `id`/`response` into its own schema. It sets `response_id` to the file stem (`baseline_v1`), not the row's `prompt_version`: the repository's `baseline_v2.jsonl` currently contains rows incorrectly marked `prompt_version: v1`.

## Integrate with the harness

For each system response, call:

```python
from judge import Judge, JudgeError

judge = Judge()  # reads judge/.env and environment variables
try:
    grade = judge.grade(customer_message, order_context, response_text)
    row = {
        "item_id": item_id,
        "response_id": response_id,
        "response_text": response_text,
        "scores": grade["scores"],
        "reason": grade["reason"],
        "judge_model": grade["response_model"],
        "judge_latency_ms": grade["latency_ms"],
        "judge_usage": grade["usage"],
        "judge_prompt_version": grade["prompt_version"],
    }
except JudgeError as exc:
    row = {"item_id": item_id, "response_id": response_id,
           "status": "judge_error", "error_type": exc.kind, "error": str(exc)}
```

The five criterion names/ranges and total are defined in `judge/client.py` and `judge/prompts/judge_v1.txt`. Retain one result row per attempted item, including failures. Do not include the key or `.env` in results. The existing standalone runner already implements saving, error reporting, latency/usage, metadata, and local-human comparison; use it for an initial run rather than reimplementing those pieces.

The standalone runner accepts:

```json
{"item_id":"P1-001","response_id":"baseline_v1","response_text":"Your order is pending."}
```

Existing Person 4 baseline files can be passed directly:

```powershell
python -m judge.run --responses results/baseline_v1.jsonl --output results/judge-baseline-v1
python -m judge.run --responses results/baseline_v2.jsonl --output results/judge-baseline-v2
```

## What is needed for final reliability results

The current `human_labels.jsonl` contains two seeded labels for each **reference answer**. Its `response_id` is `reference_answer`, so it does not label Person 4's baseline replies. The current dataset notes also say those seeded reference labels still need independent human review. Consequently, grading the baseline can produce model scores, but it cannot yet produce valid human-vs-judge agreement for those answers.

For each evaluated baseline reply, get two independent human labels using the existing scoring guide. Keep the exact `response_text`; set `item_id` to the dataset id and `response_id` to `baseline_v1` or `baseline_v2`. Preserve each evaluator's five criterion scores and explanation. Point the runner at that labels file with `--labels`. It reports agreement against each evaluator separately; do not average away disagreements without an agreed rule.

To generate the three final result groups:

1. Run the system on the chosen split and save one response per item. A two-item judge pilot estimates runtime; only run the full set after allowing for measured per-item time.
2. Run the judge on those outputs with `--responses` and the matching, independently reviewed `--labels` file. Use a new `--output` directory for every run.
3. Prepare reviewed, distinct answer pairs and pass `--pairs pairs.jsonl` for answer-order sensitivity. Use `--verbosity-limit N` to compare original and padded replies. Inspect these cases because added filler can also change tone/relevance. Save the generated `reliability.json` with the run.

Example once the inputs are prepared:

```powershell
python -m judge.run --responses results/baseline_v1.jsonl --labels results/human_labels_baseline_v1.jsonl --pairs results/position_pairs.jsonl --verbosity-limit 10 --output results/judge-v1-final
```

An omitted experiment is reported as unrun (`null` percentage), not as a successful zero-bias result. The seeded reference labels can be used for a development smoke check only; do not present them as independently validated human agreement. See `README.md` for output details and offline tests.
