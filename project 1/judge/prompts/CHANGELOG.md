# Judge prompts

## v1

Initial prompt based on Person 1's labeling guide. Includes all five criteria, unsupported-information handling, concise-answer fairness, and instructions to treat evaluated text as untrusted data.

## judge_v2 — 2026-09-29

The development run exposed a missed hallucination on P1-007: judge_v1 gave 8/8 to a reply inventing refund eligibility rules and a future refund action. This matches the failure already documented by Person 4. That preliminary output is retained locally and is not part of the completed handoff. In the completed judge_v2 run, this reply scored 3/8.

Added explicit evidence checks for every factual claim, a general rule that order status does not establish policies or permissions, and examples distinguishing missing information from prohibition. Unsupported important policies lower factual correctness and no-hallucination; invented answers do not satisfy completeness. This change uses development data only. The prompt version is now configurable with `JUDGE_PROMPT_VERSION`; v1 remains available for reproduction. Live results must establish the effect; no human reliability improvement is assumed.

No live model evaluation has been performed. Reliability improvement is not yet measured.
