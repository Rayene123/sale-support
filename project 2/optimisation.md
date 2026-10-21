# Week 8 optimization report

## Requirement status

The retrieval comparison below is a measured ablation, not a claim that the
50% Week 8 target has already been met. On the fixed set, no evaluated
retrieval variant both halves end-to-end p95 latency/cost and stays within two
accuracy points. We therefore keep BM25 as the production baseline and do not
invent a passing before/after result. A qualifying generation optimization
requires a new run on the same 109 questions.

## Fixed-set retrieval comparison

The same 109 approved questions were evaluated in all four stored runs. Recall and any-gold denominators are 89 answerable questions; strict multi-evidence denominator is 8 questions with multiple required article IDs. Twenty unanswerables are excluded from retrieval recall. Search latency excludes process startup and model/index initialization when the evaluator does not measure them.

| Method | Recall@10 | Any-gold@10 | Strict multi@10 | Search p50 | Search p95 |
|---|---:|---:|---:|---:|---:|
| BM25 | 83.15% | 85.39% | 50.00% | 1.82 ms | 2.82 ms |
| Vector | 68.54% | 70.79% | 0.00% | 20.56 ms | 27.48 ms |
| Hybrid | 87.08% | 89.89% | 25.00% | 21.69 ms | 27.63 ms |
| Hybrid + reranker | 87.08% | 89.89% | 25.00% | 24.17 ms | 32.55 ms |

At k=10, hybrid improves recall by 3.93 percentage points and any-gold hit by 4.50 points over BM25, while strict multi-evidence success is 25 points lower. Hybrid p50 search latency is approximately 11.9 times BM25. Reranking leaves k=10 evidence coverage and strict multi-evidence success unchanged from hybrid, while increasing p50 by 2.48 ms and p95 by 4.93 ms. On these measurements, neither hybrid nor reranking is an unconditional optimization; the tradeoff must be justified by the application latency budget and a manual review of missed multi-article cases.

The full k=1/3/5/10 table and interpretation are in `docs/PERSON_4_EVALUATION.md`.

## Generation, cost, and user feedback

The generation harness `eval/generation.py` completed the 109 approved questions using local `qwen2.5:3b`; results are in `data/eval/generation_qwen25_3b_stage9_recovered.json`. Its initial pass had 17 HTTP errors; a separate retry of those 17 IDs succeeded for all of them. The original partial run is preserved. Key results: answer token-overlap F1 proxy 0.307; citation precision 0.341 and recall 0.449 over 89 answerable questions; exact quote occurrence 133/133; unanswerable abstention 13/20, with 7 unsupported questions answered; false abstention 31/89; abstention F1 0.406. Server total p50/p95 was 28.25/37.81 seconds, primarily generation (28.25 seconds p50); retrieval p50 was 3.18 ms. Token use was 448,824 prompt and 30,283 completion tokens.

The lexical F1 and citation-ID matches are proxies, and quote occurrence is not entailment. The project owner reports reviewing the generated answers and considers them faithful; this qualitative review does not establish legal correctness. The local Ollama run incurred no metered API token charge. Electricity, hardware amortization, and operating costs were not measured.

No target-user sessions were performed. Structured feedback from real target users remains outstanding and cannot be inferred from this model evaluation. Groq follow-up is out of scope; the local Ollama evaluation completed independently.

## Reproducibility and optimization gate

The final BM25 evaluator run is stored in
`data/eval/retrieval_bm25_final.json`. It evaluated all 109 approved questions
with the same canonical set used for the other stored runs. The measured
latency was 4.69 ms p50 and 8.36 ms p95 in the current environment; these
values exclude process startup and model loading.

The remaining optimization experiment must select one change (for example,
shorter generation output, a smaller model, prompt caching, or a calibrated
retrieval threshold), run the unchanged fixed set before and after, and report
cost, end-to-end p50/p95, answer quality, citation accuracy, and abstention.
The change is accepted only if cost or p95 falls by at least 50% and accuracy
falls by no more than two percentage points.

## Next optimization gate

1. Collect anonymous target-user task feedback using the procedure in `docs/PERSON_4_EVALUATION.md`.
2. Measure local electricity/hardware operating cost if a total-cost figure is required; token billing for this local Ollama run was not metered.
3. If a generation before/after comparison is required, select and document a specific optimization, then rerun the same fixed set and compare answer quality, citations, abstention, latency, and cost.
