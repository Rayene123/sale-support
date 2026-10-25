# Postmortem

## What we built

We built a French-language retrieval-augmented service over the 2024 IORT
edition of the Tunisian Code de commerce. The system stores article metadata,
retrieves with BM25 in the production baseline, and validates every generated
citation against the exact passage supplied to the model.

## What failed

1. **The first retrieval smoke set was too small.** An eight-question smoke
   result made hybrid retrieval look more decisive than it was. We replaced it
   with 109 approved questions, separated 89 answerable questions from 20
   unanswerable questions, and retained the smoke run only as a development
   artifact.
2. **Semantic retrieval underperformed BM25 on this corpus.** At k=10, vector
   recall was 68.54% versus 83.15% for BM25. Legal article numbers and repeated
   French terminology made lexical matching especially strong.
3. **The reranker did not improve the fixed-set result.** It added latency while
   leaving hybrid k=10 recall unchanged. We therefore do not present it as an
   unconditional improvement.
4. **Unsupported questions were not rejected reliably.** The generation run
   answered 7 of 20 unanswerable questions and falsely abstained on 31 of 89
   answerable questions. Exact quote validation prevented fabricated quotations,
   but quotation occurrence is not the same as semantic support.
5. **The first generation run had transport failures.** Seventeen requests
   failed transiently; a retry completed all 17. The partial and recovered
   artifacts are both retained so the failure is auditable.
6. **The source edition cannot be downloaded reproducibly.** The publisher
   URL serves an older edition, so the 2024 PDF must be supplied manually and
   hash-verified. This is safer than silently indexing the wrong edition, but
   it is a clean-clone limitation.

## How we detected the failures

The fixed evaluation set exposed the retrieval differences and abstention
errors. Unit and integration tests cover schema validation, article parsing,
retrieval contracts, citation identity, exact quote checks, malformed model
output, provider failures, API validation, and lock release. Evaluation output
records denominators, latency, model, source fingerprints, and errors.

## What we learned

- Retrieval and generation must be measured separately.
- A citation that exists in a retrieved article can still be the wrong support
  for the claim.
- A small smoke set is useful for development but cannot justify an ablation.
- Legal corpora benefit from preserving article numbers and hierarchy.
- Honest limitations are more useful than presenting lexical proxies as legal
  correctness.

## Next iteration

The next version should add a calibrated evidence threshold using a held-out
development set, compare a real cross-encoder reranker, and manually review
the 27 abstention errors. It should also collect anonymous task outcomes from
real target users, measure hosted or local operating cost, and rerun the same
fixed set before and after one selected generation optimization.
