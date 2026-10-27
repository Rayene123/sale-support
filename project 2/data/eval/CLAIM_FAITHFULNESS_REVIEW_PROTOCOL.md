# Claim-level faithfulness review protocol

## Purpose and status

This protocol assesses whether each generated claim is supported by its cited
corpus passage. It does not determine whether the claim is legally correct,
current, complete, or suitable as legal advice. The prepared queue contains
152 claims from 81 answered questions in the complete standard-tier
GPT-6 Luna/Qdrant evaluation. Abstained answers have no claim to label.

The queue at `claim_faithfulness_review_queue.jsonl` is a blank review
template. No claim labels or faithfulness score have been produced yet.

## Reviewer instructions

1. Read the question, generated claim, cited quotation, and full article text in
   the `passage` field. Judge only whether that passage supports the claim.
2. Check each factual part of the claim. Check that the answer does not add a
   rule, actor, deadline, condition, exception, or conclusion absent from the
   passage. A quotation appearing in the article is not by itself proof that
   the generated claim follows from it.
3. Complete one review record for every assigned `review_id`. Preserve its
   `claim_sha256` exactly, and fill `label`, `reviewer`, and `reason`.
4. Use an anonymous stable reviewer code (for example, `reviewer-a`), not a
   name or contact detail. Give a short reason grounded in the passage. Do not
   include personal data or case facts.
5. Have two reviewers label claims independently. Resolve disagreements only
   through documented adjudication; until then, count the item as unclear.

## Labels

- `supported`: every substantive part of the claim is supported by the cited
  passage, with material qualifications preserved.
- `partially_supported`: some of the claim is supported, but a material part
  is missing, overgeneralized, or insufficiently qualified.
- `unsupported`: the passage does not support the claim, or contradicts it.
- `unclear`: the passage and supplied context do not permit a reliable label.

## Scoring

The evaluator reports strict support as `supported / (supported +
partially_supported + unsupported)`. `unclear` items are excluded from that
ratio and remain visible in counts. If independent reviewers disagree, the
evaluator counts the item as unclear. Always report the reviewed and
unreviewed claim counts, all label counts, and disagreements alongside the
ratio. Do not describe this score as legal correctness.

To score a completed JSONL file, use the generation evaluator with the
original result, the completed reviews file, and a fresh output path:

```powershell
python "project 2/eval/generation.py" `
  --questions "project 2/data/eval/questions.jsonl" `
  --corpus "project 2/data/processed/corpus.jsonl" `
  --score-existing "project 2/data/eval/generation_openai_gpt6_luna_qdrant_standard.json" `
  --reviews "project 2/data/eval/claim_faithfulness_reviews.jsonl" `
  --output "project 2/data/eval/generation_openai_gpt6_luna_qdrant_standard_reviewed.json"
```

## Separate legal correctness review

Semantic support review is not a substitute for a qualified legal review.
Legal reviewers must separately check the governing law and date, legal
conditions and exceptions, amendments/repeals, cross-references, and whether
the conclusion follows under the applicable provisions. Record those outcomes
using the project dataset's legal-review process, not this claim-support score.
