# Postmortem

## What Went Well

- The dataset is reproducible and contains 160 valid records with an explicit
  40-item development and 120-item held-out test split.
- The harness produces structured per-item rows, preserves failures, records
  hashes and runtime metadata, and has 84 offline tests.
- Prompt versions, judge prompts, replay inputs, and result reports are stored
  under version control.

## What Went Wrong

- The first committed evidence focused on development data; no final run on the
  held-out test split is committed yet.
- `human_labels.jsonl` contains seeded labels for reference answers, not
  independent labels for the generated replies. This blocks a valid
  judge-versus-human reliability claim.
- The v2 baseline rows were recorded with the v1 prompt label, which caused the
  harness to emit prompt-version mismatch warnings during replay. The mismatch
  is documented and must be corrected before treating v2 as clean evidence.
- The position-bias screening used only three comparisons and changed two
  verdicts. That is a useful warning, but not a stable estimate.
- Local-provider pricing was not configured, so cost is reported as `null`.

## What We Learned

The development comparison is useful for prompt iteration but cannot substitute
for a held-out test result. A high model-assigned score is also not evidence of
judge reliability until the same generated replies have been independently
labelled by humans. Bias experiments need enough paired trials to make their
percentages meaningful.

## Corrective Actions

1. Run the selected prompt once on `data/test.jsonl` without changing it after
   seeing the test scores.
2. Have two evaluators label the generated test replies using
   `data/labeling_guide.md`.
3. Run the judge-versus-human comparison and report counts, percentages, and
   major disagreements.
4. Correct the v2 source metadata and rerun the replay before publishing the
   prompt comparison as final evidence.
5. Repeat position and verbosity experiments with a larger reviewed sample and
   configure a documented price or local-compute assumption.
