# Start here

Read the [saved comparison](../results/judge-comparison-v2-20260929/README.md) for readable results. The `v1/v2/v3` result folders are **system prompt versions**, all graded with the same `judge_v2`. Active Python code is in this folder; the comparison directory keeps only canonical outputs.

Regenerate Markdown without model calls:

```powershell
python -m judge.readable --run results/judge-comparison-v2-20260929
```

# Person 3: AI judge

The judge grades support replies using the team's 8-point rubric. It requires Python 3.10+ and no third-party Python packages. The default provider is local Ollama with `qwen3:14b`; Groq is optional and requires an API key.

## Setup

Open a terminal in `sale-support/project 1`. Install Ollama and make sure it is running. Download the model once (about 9 GB):

```powershell
ollama pull qwen3:14b
```

Install the configured model if it is missing. Availability and hardware depend on the machine running the evaluation; historical measurements do not establish current availability.

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

The judge accepts Person 4's `results/baseline_v1.jsonl`, `results/baseline_v2.jsonl`, and merged `results/baseline_v3.jsonl` directly. UTF-16 and UTF-8 are supported. The files use fields named `id` and `response`; the judge converts them while reading and uses the filename as the response set ID. It also accepts a UTF-8 JSONL file with one object per line using either schema:

```json
{"item_id":"P1-001","response_id":"baseline-v1","response_text":"Your order is pending."}
```

```powershell
python -m judge.run --responses results/baseline_v1.jsonl --output results/judge-baseline-v1
```

Human comparisons require labels with the same item_id, response_id, and exact response_text. Unlabeled replies can be graded but are counted as unlabeled, not matched to reference-answer grades. Pass an updated labels file with `--labels`.

## Compare the merged Person 4 versions

```powershell
python -m judge.evaluate_versions --output results/judge-comparison-01
```

This verifies that all three saved versions cover the same 40 development items and that the local model is available. It grades all 120 replies with the same frozen judge prompt. For v3 it also grades ten padded replies and evaluates ten distinct v1/v3 answer pairs in both orders (150 model requests total). Pair selection is deterministic, covering different categories first. These are screening experiments; review the pair texts and padding before interpreting bias. No human winner labels are assumed.

Each version gets per-answer scores and a `reliability.json` with the average `/8`, score distribution, per-criterion averages, and coverage. `comparison.json` collects the three versions. All runs record their source, prompt, input hashes, model, request timing, and raw model responses. Existing output directories are refused. Interrupted runs retain completed rows; there is no automatic resume.

Person 4's `system/metrics.py` measures time and tokens; it does not calculate the quality rubric. These judge outputs supply quality scores for Person 2's harness and Person 4's prompt comparison. Independent human scoring of these exact replies is still needed to complete Persona 3's human agreement and failure analysis. The existing reference-answer labels cannot be substituted.

After two people independently label the actual replies, compare them with the saved scores without another model run:

```powershell
python -m judge.compare_humans --run results/judge-comparison-01/v3 --labels results/human_labels_v3.jsonl --labels-reviewed --output results/human_comparison_v3.json
```

Use the existing human-label schema, exact answer text, and `response_id=baseline_v3`. This verifies the dataset hash and label/answer identity, reports coverage, and compares each human separately. Use `--labels-reviewed` only after independent review actually happened.

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

The default is now `judge_v2`, strengthened after a real development failure where v1 missed an invented refund policy. Set `JUDGE_PROMPT_VERSION=judge_v1` to reproduce the earlier judge. Every run records the selected version and exact prompt hash. See `prompts/CHANGELOG.md` for the evidence and rationale.

## What gets saved

- `results.jsonl`: candidate replies, validated grades, explanations, raw successful responses, usage, latency, or categorized errors. Each row is flushed immediately.
- `verbosity.jsonl` and `position.jsonl`: bias experiment details, created only when those experiments produce records.
- `reliability.json`: per-criterion and total agreement counts/percentages, per-evaluator comparisons, coverage, mean absolute differences, disagreements of at least 2 total points, and bias summaries.
- `metadata.json`: settings (never the key), UTC time, and input hashes.
- `report.md`: readable questions, exact answers, scores, explanations and order context.

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

The total is calculated from the validated criterion scores. `declared_total` preserves the model's proposed total and `total_corrected` flags arithmetic corrections; the original output remains in `raw_response`. Invalid criterion ranges, types, missing fields and explanations are still rejected.

## Offline verification

```powershell
python -m unittest discover -s judge/tests -v
```

Tests use mocked HTTP responses and temporary files. They exercise the real request construction, validation, input matching, and comparison calculations. They do not establish provider access or judge reliability.

## Observed development limitations (2026-09-29)

These are engineering reviews against the supplied context/rubric, not independent human labels or an accuracy benchmark:

- P1-007 / baseline_v1: judge_v1 awarded 8/8 to an invented refund policy. The revised judge_v2 recognized the unsupported policy; its criteria sum to 3/8. It proposed 4 as the total, exposing an arithmetic error now corrected and explicitly flagged by the client.
- P1-004 / baseline_v1: judge_v2 awarded 8/8 despite dollar symbols in the reply and no currency field in the order context. This is a grounding miss. The reference answer also supplies EUR without a currency field, so reference-answer similarity would not resolve the ambiguity; Person 1 should clarify the dataset.
- P1-009 / baseline_v1: judge_v2 awarded 7/8 to a concise status update, citing missing possible follow-up details even though the customer only asked "Update?". This suggests an overly strict completeness judgment for ambiguous short requests.

Preliminary development outputs are not part of the handoff. All three system
versions have been graded in `results/judge-comparison-v2-20260929`: v1 averages
7.85/8, v2 7.875/8, and v3 7.925/8, each on the same 40 development items with
no request failures. Bias tests did not run in these saved comparisons; the
harness has separate screening results. Preserve failures when interpreting
high averages: stable JSON and consistent scores do not demonstrate a reliable
judge.

## Final handoff checklist

Run the local experiments with Ollama available. Review major disagreements and record concrete examples of hallucination misses, completeness mistakes and other judge failures. Share the results and interface with Person 2, failure examples with Person 4, and rubric ambiguities with Person 1. Write the final reliability discussion from observed results; the implementation alone does not complete these experimental deliverables.

## Update from Person 2 (harness integration)

The evaluation harness in `harness/` now calls this judge as a library and has
consumed the saved comparison:

```powershell
python -m harness run --system-source results/baseline_v3.jsonl --system-prompt v3 `
    --judge-source results/judge-comparison-v2-20260929/v3/results.jsonl `
    --run-id dev-v3-replay --output results/harness/dev-v3-replay
```

- All 120 saved grades in `results/judge-comparison-v2-20260929/` match their
  baseline replies exactly, and replaying them reproduces the 7.85 / 7.875 /
  7.925 averages and the recorded latency and token figures.
- Position and verbosity screening tests have now been run through the harness
  (`--position-limit`, `--position-repeats`, `--verbosity-limit`); per-trial rows
  are in `results/harness/*/position.jsonl` and `verbosity.jsonl`, and the sample
  sizes must be quoted with any percentage.
- Judge-versus-human agreement on the evaluated replies is still **not**
  reported: the labels on file cover `response_id: "reference_answer"`, so the
  harness records "labels do not cover this reply set" instead of a number. That
  remains the open item above.

See `harness/README.md` and `docs/PERSON_2_HANDOFFS.md`.
