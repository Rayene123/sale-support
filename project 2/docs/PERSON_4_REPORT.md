# Person 4 Report: Evaluation, Optimization, and Cost

## 1. Executive summary

Person 4 completed fixed-set retrieval evaluations, a local Qwen generation
run, a full Qdrant-backed GPT-6 Luna generation baseline, one context-budget
optimization attempt, a targeted legal-correctness screen, and evaluation
cost accounting.

The Qdrant-backed baseline completed all 109 approved evaluation questions:
89 answerable and 20 unanswerable. The one excluded duplicate was not scored.
The attempted context optimization reduced the supplied retrieval context
from 12,000 to 4,500 characters. It reduced prompt tokens by 28.0% and
estimated generation charges by 24.1%, but increased end-to-end p95 latency
by 129.1%, lowered citation precision/recall, and increased false abstentions
on answerable questions from 8 to 18. We rejected it. The required 50%
reduction in cost or p95 latency was not achieved; optimization is on hold.

Real-user feedback and claim-level semantic-faithfulness review were removed
from the agreed scope. A first-pass 16-case legal screen against the project's
frozen corpus is included below and detailed in
[`LEGAL_CORRECTNESS_REVIEW.md`](LEGAL_CORRECTNESS_REVIEW.md). It is not
qualified legal sign-off or a current-law audit.

## 2. Scope, evaluation set, and interpretation

The canonical dataset is `data/eval/questions.jsonl`: 110 rows, of which 109
are approved and one is a retained excluded duplicate. The approved set
contains 89 answerable and 20 unanswerable questions, all in French. There is
no Arabic query/evidence evaluation. The dataset audit confirmed that active
gold evidence IDs resolve to published corpus records and that the stored
quotes match normalized source text. That structural check does not establish
legal correctness. The project owner reported qualified expert approval of
the evaluation questions, but did not provide reviewer identity or review
date, so neither is recorded or independently verified here.

The generation answer-quality score is mean token-overlap F1 against expected
answers; it is not semantic or legal accuracy. Citation precision and recall
compare returned article IDs with dataset gold IDs. Exact quote match means
only that a quotation occurs in a corpus record, not that the answer is
entailed by it. Search-only latency is kept separate from end-to-end
generation latency.

The OpenAI baseline used `service_tier=default`, which OpenAI describes as
standard pricing and performance. This is distinct from the Qdrant plan. The
Qdrant cluster was reported by the project owner to be on Qdrant Cloud Free.

## 3. Work completed

| Stage | Work and outcome |
|---|---|
| Dataset and review process | Defined the canonical JSONL contract, evidence IDs, answerability, review fields, and labeling guidance; corrected and audited the 109 approved questions while retaining the excluded duplicate. |
| Retrieval evaluation | Added fixed-set retrieval metrics and evaluated BM25, vector, hybrid, and hybrid plus reranker at k=1, 3, 5, and 10. |
| Local generation evaluation | Ran Qwen 2.5 3B through the existing `/ask` endpoint over all 109 approved questions; retried 17 transient request failures and retained the partial and recovered results. |
| Qdrant-backed generation evaluation | Ran GPT-6 Luna with hybrid Qdrant retrieval over the same 109 questions, recording answer, citation, abstention, latency, usage, and estimated generation cost metrics. |
| Optimization attempt | Compared a 4,500-character retrieval-context cap with the 12,000-character baseline on the same question set; rejected the candidate after its latency and citation regressions. |
| Legal screen | Reviewed 16 targeted answers against the frozen corpus, covering conditions, exceptions, cross-references, legal conclusions, abstentions, and question/answer-key concerns. |
| Cost and reporting | Calculated generation charges from recorded token usage and configured rates; documented Qdrant Free-tier assumptions, a 100x token-cost projection, limits, and remaining work. |

## 4. Retrieval results

All retrieval methods used the same 109 approved questions. Recall and any-gold
denominators are 89 answerable questions; strict multi-evidence denominator
is 8 questions with multiple required article IDs. Twenty unanswerable
questions are excluded from recall. Search latency excludes process startup
and model/index initialization where the evaluator did not measure them.

| Method | k | Recall (89) | Any-gold hit (89) | Strict multi-evidence (8) |
|---|---:|---:|---:|---:|
| BM25 | 1 | 42.13% | 43.82% | 0.00% |
| BM25 | 3 | 64.61% | 66.29% | 25.00% |
| BM25 | 5 | 74.16% | 76.40% | 37.50% |
| BM25 | 10 | 83.15% | 85.39% | 50.00% |
| Vector | 1 | 31.46% | 31.46% | 0.00% |
| Vector | 3 | 48.88% | 49.44% | 0.00% |
| Vector | 5 | 57.87% | 59.55% | 0.00% |
| Vector | 10 | 68.54% | 70.79% | 0.00% |
| Hybrid | 1 | 45.51% | 47.19% | 0.00% |
| Hybrid | 3 | 73.60% | 76.40% | 0.00% |
| Hybrid | 5 | 79.21% | 83.15% | 0.00% |
| Hybrid | 10 | 87.08% | 89.89% | 25.00% |
| Hybrid + reranker | 1 | 45.51% | 47.19% | 0.00% |
| Hybrid + reranker | 3 | 71.35% | 74.16% | 0.00% |
| Hybrid + reranker | 5 | 79.78% | 83.15% | 12.50% |
| Hybrid + reranker | 10 | 87.08% | 89.89% | 25.00% |

| Method | Search p50 | Search p95 |
|---|---:|---:|
| BM25 | 1.82 ms | 2.82 ms |
| Vector | 20.56 ms | 27.48 ms |
| Hybrid | 21.69 ms | 27.63 ms |
| Hybrid + reranker | 24.17 ms | 32.55 ms |

At k=10, hybrid improved recall by 3.93 points and any-gold hit by 4.50
points over BM25, but strict multi-evidence success was 25 points lower.
Hybrid p50 search latency was about 11.9 times BM25. Reranking did not improve
k=10 coverage or strict success over hybrid and increased p50/p95 latency.
These retrieval measurements do not demonstrate a 50% end-to-end latency
optimization.

## 5. Local Qwen generation result

The recovered local Ollama `qwen2.5:3b` result covers all 109 approved
questions. The original run had 17 HTTP errors on `fr-single-040` through
`fr-single-056`; retries completed all 17. The original partial and recovered
results are retained.

| Metric | Result | Denominator |
|---|---:|---:|
| Answer token-overlap F1 proxy | 0.307 mean | 89 answerable |
| Gold citation precision / recall | 0.341 / 0.449 | 89 answerable |
| Exact quote occurrence in published corpus | 133/133 | Returned quotes |
| Correct abstention on unanswerable questions | 13/20 (65%) | 20 unanswerable |
| Unanswerable questions answered | 7/20 (35%) | 20 unanswerable |
| Answerable questions incorrectly abstained | 31/89 (34.8%) | 89 answerable |
| Abstention F1 | 0.406 | 109 completed |
| Server total p50 / p95 | 28.25 s / 37.81 s | 109 completed |
| Server retrieval p50 | 3.18 ms | 109 completed |
| Server generation p50 | 28.25 s | 109 completed |
| Prompt / completion tokens | 448,824 / 30,283 | 109 completed |

This local run had no metered API token charge. Electricity and local hardware
amortization were not measured. Its answer and citation metrics remain
proxies, not legal or semantic validation.

## 6. Qdrant-backed GPT-6 Luna results

The baseline used GPT-6 Luna, Qdrant Cloud collection `librarian-chunks`,
hybrid retrieval, `service_tier=default`, and 12,000-character maximum
retrieval context. Query rewriting was disabled because the local Ollama
rewrite service was unavailable. The saved run records 582 points in the
collection. This was a live provider evaluation, not evidence of public app
deployment.

| Metric | Baseline result | Denominator |
|---|---:|---:|
| Completed questions | 109/109 | 109 approved |
| Answer lexical F1 proxy | 0.509 mean | 89 answerable |
| Gold citation precision / recall | 71.7% / 77.0% | 89 answerable |
| Exact quote occurrence | 152/152 | Returned quotes |
| Correct abstention on unanswerable | 20/20 | 20 unanswerable |
| Answerable questions incorrectly abstained | 8/89 | 89 answerable |
| Abstention F1 | 0.833 | 109 completed |
| Server end-to-end p50 / p95 | 3.09 s / 5.19 s | 109 completed |
| Client wall p50 / p95 | 3.11 s / 5.20 s | 109 completed |
| Retrieval p50 / generation p50 | 320 ms / 2.60 s | 109 completed |
| Prompt / completion tokens | 325,050 / 14,929 | 109 completed |
| Estimated generation charge | $0.0399695 | 109 completed |

The Flex attempt completed only 39/109 requests; 70 failed with
`flex_unavailable` (69 HTTP 503, one HTTP 504). All 39 successful questions
were answerable, so it provides no unanswerable-question abstention result and
is not a paired comparison. Its $0.00704 partial charge is not evidence of a
cost reduction.

## 7. Context-budget optimization attempt

This experiment changed the maximum supplied retrieval-context text from
12,000 to 4,500 characters. It did not change prompt wording or instructions.
The model, API service tier, Qdrant collection, retrieval configuration,
rewrite setting, and 109-question set were held fixed. The candidate had 11
transient provider errors in its first pass; retries recovered all 109.

| Metric | Baseline: 12,000 chars | Candidate: 4,500 chars | Change |
|---|---:|---:|---:|
| Prompt tokens | 325,050 | 233,917 | -28.0% |
| Completion tokens | 14,929 | 13,898 | -6.9% |
| Estimated generation cost | $0.03997 | $0.03034 | -24.1% |
| Cost per request | $0.0003667 | $0.0002784 | -24.1% |
| Server end-to-end p50 | 3.09 s | 3.43 s | +11.3% |
| Server end-to-end p95 | 5.19 s | 11.90 s | +129.1% |
| Answer lexical F1 proxy | 0.509 | 0.493 | -1.58 points |
| Gold citation precision | 71.7% | 63.0% | -8.71 points |
| Gold citation recall | 77.0% | 68.5% | -8.43 points |
| Exact quote occurrence | 152/152 | 125/125 | 100% each |
| Correct abstentions | 20/20 | 20/20 | Unchanged |
| False abstentions on answerable questions | 8/89 | 18/89 | 10 more |
| Abstention F1 | 0.833 | 0.690 | -14.37 points |

**Decision: rejected.** Generation charges fell by 24.1%, short of the 50%
target, while p95 latency became more than twice as high. The lexical F1
proxy loss was within two points, but citation scores and answerable-question
abstention worsened substantially. Retain 12,000 characters as the measured
baseline. Do not describe this as a successful optimization.

## 8. What went well and what did not

### What went well

- Completed the Qdrant-backed baseline and recovered candidate on the same
  109 approved questions, enabling a paired comparison.
- All 20 corpus-unanswerable questions were correctly abstained on in both
  complete GPT-6 Luna runs.
- All returned quotation strings matched published corpus text. This is a
  useful structural check, although it does not prove legal support.
- The shorter context reduced input tokens and estimated generation charges.
- The targeted legal screen compared actual answer text and article text; it
  distinguished low lexical overlap from actual legal mismatches.

### What went wrong or remains weak

- The context candidate increased end-to-end p95 latency by 129.1%.
- Citation precision and recall each fell by more than eight percentage
  points; false abstentions on answerable questions increased from 8 to 18.
- The Flex service tier failed on most requests and could not be evaluated on
  the full set.
- The lexical answer score does not establish semantic or legal correctness.
- The legal screen found wrong-article answers, missed answerable questions,
  an ambiguous question about the instrument, and an expected answer that
  omitted a post-protest exception.

The project owner also reported a qualitative review of generated answers
and considered them faithful. This is owner feedback, not a numeric claim-
support assessment or a legal correctness determination.

## 9. Legal-correctness screen

The 16-case first pass compared generated responses and citations with
questions, expected answers, and source articles in the corpus. It covered
legal conditions, exceptions, cross-references, and conclusions. The findings
included five correct or mostly correct answers, two incomplete answers,
three incorrect or materially misdirected answers, one instrument-ambiguous
case, and five answerable questions where the system abstained.

The review also identified a gold-answer issue for `fr-single-039`: the
expected answer states the general post-maturity rule but omits the explicit
post-protest exception relevant to the question. `fr-single-030` does not
identify whether it asks about a cheque or bill of exchange. See
[`LEGAL_CORRECTNESS_REVIEW.md`](LEGAL_CORRECTNESS_REVIEW.md) for case-level
details and review limits.

The corpus is a Tunisian Commercial Code edition reviewed through 15 February
2024 and records amendments through Law No. 2019-47. The screen is corpus-
relative, targeted, and not a representative full-set estimate. It is not
qualified Tunisian legal sign-off or a confirmation of current law.

## 10. Cost model

### Measured run and request estimate

The baseline used 325,050 prompt tokens and 14,929 completion tokens over
109 requests. The evaluation calculated the charge at its configured rates
of $0.10 per million prompt tokens and $0.50 per million completion tokens:

`(325,050 × $0.10 + 14,929 × $0.50) / 1,000,000 = $0.0399695`

This is approximately **$0.0003667 per request** for generation. It is an
estimate from the rates recorded with the run, not an independently checked
provider invoice.

The project owner reports using Qdrant Cloud Free. Assuming the evaluation
used that cluster and no paid Qdrant-hosted inference, Qdrant's direct hosting
charge for this period is **$0**. The reported cluster had 582 points. The
current Free tier lists one node with 0.5 vCPU, 1 GB RAM, and 4 GB disk;
confirm actual plan and billing in the Cloud Console. [Free cluster resources](https://qdrant.tech/documentation/cloud/create-cluster/),
[Qdrant billing](https://qdrant.tech/documentation/cloud-pricing-payments/).

On these assumptions, known direct cost for the baseline is $0.03997 total,
or $0.0003667/request. This excludes unreported provider charges and does
not price engineering labor. Electricity and hardware amortization are not
separately measured: the measured stack uses managed Qdrant Cloud and a hosted
generation API, so the project has no direct meter for the providers'
underlying electricity or hardware. Those internal costs are unavailable,
not zero.

### Projection at 100x traffic

Scaling the same request mix and token usage linearly to 10,900 requests gives
estimated generation charges of:

`100 × $0.0399695 = $3.99695` (about **$4.00**)

This is a token-cost projection, not a load test. Qdrant would cost $0 only if
the Free tier remains sufficient. Whether its 0.5 vCPU, 1 GB RAM, and 4 GB
disk can serve 100x traffic at acceptable latency has not been tested. Any
required paid-cluster cost must be added from the Cloud Console or pricing
calculator. The projection is therefore **about $4.00 plus any Qdrant upgrade
or other provider charges**, not a guaranteed all-in figure.

## 11. Scope and remaining items

- Real-user feedback and claim-level semantic-faithfulness labels are outside
  the agreed scope; no results are claimed for either.
- Optimization is on hold. The Week 8 requirement remains unmet. If resumed,
  test a single change on the unchanged 109-question set and compare cost,
  end-to-end latency, answer quality, citations, and abstention.
- Obtain qualified Tunisian legal review if legal sign-off or a current-law
  claim is required.
- Confirm account invoices and any paid inference use if the complete cost
  model must include charges beyond the assumptions above.
- Final results apply to the saved model, prompt, corpus, Qdrant collection,
  and settings. Do not generalize them to other models, deployments, or legal
  domains.

## 12. Reproducibility files and commands

### Result files

- Canonical questions: `data/eval/questions.jsonl`
- Corpus: `data/processed/corpus.jsonl`
- Retrieval runs: `data/eval/retrieval_bm25_stage5c.json`,
  `retrieval_vector_stage6a.json`, `retrieval_hybrid_stage7a.json`,
  `retrieval_hybrid_reranker_stage8a.json`
- Final BM25 run: `data/eval/retrieval_bm25_final.json`
- Local Qwen result: `data/eval/generation_qwen25_3b_stage9_recovered.json`
- Qdrant GPT-6 Luna baseline:
  `data/eval/generation_openai_gpt6_luna_qdrant_standard.json`
- Recovered context candidate:
  `data/eval/generation_openai_gpt6_luna_qdrant_context4500_recovered.json`
- Incomplete Flex result:
  `data/eval/generation_openai_gpt6_luna_qdrant_flex.json`
- Case-level legal screen: `docs/LEGAL_CORRECTNESS_REVIEW.md`

### Retrieval evaluation commands

Use fresh output paths; the evaluator refuses to overwrite existing files.

```powershell
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method bm25 --output "project 2/data/eval/retrieval_bm25.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method vector --output "project 2/data/eval/retrieval_vector.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method hybrid --output "project 2/data/eval/retrieval_hybrid.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method hybrid_reranker --output "project 2/data/eval/retrieval_hybrid_reranker.json" --k 1 3 5 10
```

### Local Qwen generation command

```powershell
$env:OLLAMA_MODEL = "qwen2.5:3b"
python -m uvicorn api.app:app --app-dir "project 2/src" --host 127.0.0.1 --port 8002
python "project 2/eval/generation.py" --questions "project 2/data/eval/questions.jsonl" --corpus "project 2/data/processed/corpus.jsonl" --api-url "http://127.0.0.1:8002" --output "project 2/data/eval/generation_run.json"
```

The OpenAI runs are retained as full raw result and checkpoint files in
`data/eval/`; use their saved provenance when reproducing or comparing them.
