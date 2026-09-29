# Person 3: AI judge

This is a small Python implementation with no third-party dependencies (Python 3.10+). It grades support replies using the team's 8-point rubric. The default is local Ollama with the already-installed `qwen3:14b`. Your PC has 32 GB RAM and an RTX 4060 Laptop GPU with 4 GB listed VRAM; this 14B quantized model is the strongest candidate already installed, while bigger local models would likely run poorly on this setup. It makes requests only to your computer at `localhost:11434`; no API key, paid service, or account is needed. Groq is an optional API provider and requires a key.

## Setup

Open a terminal in `sale-support/project 1`. Install Ollama and make sure it is running. Download the model once (about 9 GB):

```powershell
ollama pull qwen3:14b
```

Ollama reported `qwen3:14b` already installed on 2026-09-29, so it should not need to be downloaded again. This newer model was selected in place of the earlier benchmark model, `qwen2.5:14b`, because it is the stronger local model currently available on this PC. Any judge results are new measurements; they cannot be compared directly with the earlier Qwen2.5 system accuracy result because the model serves a different task (grading rather than answering) and the prompts differ. No model download is triggered by this project.

```powershell
Copy-Item judge/.env.example judge/.env
```

For local Ollama, leave `JUDGE_API_KEY=` empty. `.env` is ignored by Git. Environment variables override this file. Do not put keys into source, results, or messages. There is no offline fake grading fallback: if Ollama is stopped or the model is missing, the program reports that before grading. To use the optional Groq service instead, set `JUDGE_PROVIDER=groq` and supply `JUDGE_API_KEY`; that choice sends data to the hosted service and may incur charges.

## First run

```powershell
python -m judge.run --limit 10 --output results/judge-dev-01
```

By default this grades the replies in `human_labels.jsonl` associated with the development set. It never sends human scores, evaluator explanations, or reference answers as extra guidance to the model. These particular candidate replies ARE reference answers: this is a narrow check, not a test of arbitrary system-generated replies.

**The repository's labels are seeded, not confirmed independent human reviews.** The report labels them `seeded_unverified`. After two people actually review them independently, use `--labels-reviewed` to record that attestation. For disagreements we report against each evaluator separately; we do not invent a consensus score. Add human-labeled faulty and incomplete system replies to test whether the judge detects real failures.

## Actual replies from Person 4

The judge accepts Person 4's existing `results/baseline_v1.jsonl` or `results/baseline_v2.jsonl` directly. Those files use UTF-16 and fields named `id` and `response`; the judge converts them while reading and uses the filename as the response set ID. It also accepts a UTF-8 JSONL file with one object per line using either schema:

```json
{"item_id":"P1-001","response_id":"baseline-v1","response_text":"Your order is pending."}
```

```powershell
python -m judge.run --responses results/baseline_v1.jsonl --output results/judge-baseline-v1
```

Human comparisons require labels with the same item_id, response_id, and exact response_text. Unlabeled replies can be graded but are counted as unlabeled, not matched to reference-answer grades. Pass an updated labels file with `--labels`.

## Bias experiments

For a verbosity screening test, add `--verbosity-limit 10`. This appends fixed polite filler, stores both texts and grades, and reports score changes. Inspect cases to check the original was already polite and the filler did not change relevance. A score change alone does not prove length bias.

For position bias create a JSONL file of manually reviewed, distinct answer pairs:

```json
{"item_id":"P1-001","answer_a":"Your order is pending.","answer_b":"Your order has been delivered."}
```

This example is based on the existing pending-order development item. Prepare around 10 varied pairs for an initial experiment; the sample size is a starting choice, not an assignment requirement.

```powershell
python -m judge.run --limit 10 --verbosity-limit 10 --pairs pairs.jsonl --output results/judge-bias-01
```

Both answer orders are evaluated. Results are mapped back to the original answer identities, with ties allowed. Missing tests are reported as zero attempted with null percentages, never as a passed bias test. Repeated trials are useful for separating ordinary model variation from order effects.

Freeze the prompt before evaluating `--dataset data/test.jsonl`. Use development data for prompt revisions; add each new version and rationale to `prompts/CHANGELOG.md` and update the client's prompt selection/version. Do not tune against the final test scores.

## What gets saved

- `results.jsonl`: candidate replies, validated grades, explanations, raw successful responses, usage, latency, or categorized errors. Each row is flushed immediately.
- `verbosity.jsonl` and `position.jsonl`: bias experiment details.
- `reliability.json`: per-criterion and total agreement counts/percentages, per-evaluator comparisons, coverage, mean absolute differences, disagreements of at least 2 total points, and bias summaries.
- `metadata.json`, prompt and source snapshots: settings (never the key), UTC time and input hashes for reproduction.

Existing run directories are refused. No silent retries or automatic resume. An interrupted run retains flushed rows but may not have a final reliability report. A run with API errors returns exit code 1. Failed requests are excluded from agreement denominators and reported separately, so check coverage before interpreting agreement. The client timeout is a socket timeout, not a strict whole-run deadline.

Usage and response latency are recorded. One local Qwen3:14B request on this PC took 117,662 ms including model loading and processing a 969-token prompt; warm-run speed has not been measured. Cost remains Person 2's responsibility for API runs; no costs are assigned to local inference without electricity/hardware assumptions.

## Interface for Person 2

```python
from judge import Judge, JudgeError

judge = Judge()  # reads configuration once
result = judge.grade(customer_message, order_context, response_text)
# result['scores']: five integer criteria plus total
# result['reason']: short explanation
# result also includes latency_ms, usage, raw_response, prompt version/hash
```

Catch `JudgeError` and record its `kind` and message. Supported failure kinds include configuration, input, api, model_missing, network, timeout, invalid_output, incomplete and refusal. No API error body is printed, preventing accidental credential leakage. Total and score ranges are validated locally; JSON output does not guarantee grading accuracy.

## Offline verification

```powershell
python -m unittest discover -s judge/tests -v
```

Tests use mocked HTTP responses and temporary files. They exercise the real request construction, validation, input matching, and comparison calculations. They do not establish provider access or judge reliability.

## Final handoff checklist

Run the local experiments with Ollama available. Review major disagreements and record concrete examples of hallucination misses, completeness mistakes and other judge failures. Share the results and interface with Person 2, failure examples with Person 4, and rubric ambiguities with Person 1. Write the final reliability discussion from observed results; the implementation alone does not complete these experimental deliverables.
