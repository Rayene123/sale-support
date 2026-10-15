# Person 4 — Evaluation, user feedback, and optimization

## Ownership

Create the evaluation harness, establish baseline measurements, and lead the
Week 8 optimization report.

## Tasks

- Build at least 100 labeled question-answer-source-passage pairs.
- Include answerable, unanswerable, multilingual, and difficult
  cross-reference questions where supported.
- Store questions and gold passages under `data/eval/`.
- Implement recall@k, answer correctness, faithfulness, citation accuracy,
  abstention quality, latency, and cost metrics.
- Run the retrieval ablation and generation evaluation.
- Gather structured feedback from real target users without collecting
  personal data.
- Compare baseline and optimized versions on the same test set.
- Maintain the evaluation and cost sections of the final report.

## Dependencies

This work can start independently by designing the schema, labeling
questions, and implementing metric functions. Final retrieval metrics need
Person 2's pipeline, and final generation metrics need Person 3's service.

## Handoff

Provide:

- Evaluation dataset and labeling guide
- Reproducible evaluation commands
- Baseline and ablation tables
- Cost model
- Before/after optimization table
- User feedback summary
