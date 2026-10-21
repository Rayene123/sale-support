# Person 4 — Evaluation results and process handoff

## 1. Status and dataset

The canonical test set is `data/eval/questions.jsonl`: 110 rows total, 109 approved active questions and one retained `excluded_duplicate` row (`fr-cross-009`). Active questions: 82 single-article, 8 multi-article, and 20 unanswerable-from-this-corpus. All 110 rows are French. Active answerability is 89 answerable and 20 unanswerable. No Arabic query/evidence evaluation is supported by the French-only corpus.

Structural audit against `data/processed/corpus.jsonl`: all active gold IDs resolve to published, nonempty records; every quoted evidence string matches its normalized source text after whitespace normalization. This establishes structural consistency only, not legal correctness. The user reported qualified expert approval; reviewer identity/date metadata was not supplied and has not been invented.

Person 4's main evaluation deliverables are complete: canonical dataset and labeling guide, retrieval evaluator and metrics, four fixed-set retrieval runs, one full Qwen 2.5:3b generation run, cost formula, and retrieval optimization comparison. The project owner reports reviewing the generated answers and considers them faithful. This is qualitative review, not a legal correctness determination. Real target-user feedback has not been collected.

## 2. Process by task stage

| Stage | Task | Process and outcome |
|---|---|---|
| 1 | Project audit and plan | Inspected corpus structure, existing retrieval/generation interfaces, evaluation files, requirements, tests, and report expectations. Mapped Person 4 work to Person 2/3 dependencies. |
| 2A | Dataset contract | Defined a canonical JSONL schema, article-level evidence references, answerability/review fields, and labeling rules grounded in the available French corpus. |
| 2B | Dataset construction | Created the canonical dataset from actual corpus records, with exact evidence tied to stable article IDs. Did not add Arabic questions because Arabic evidence and fluent review were unavailable. |
| 2C | Semantic quality review | Reviewed question clarity, answers, evidence fit, multi-article labels, duplicates, long answers, and corpus-relative unanswerability; prepared corrections rather than treating automatic checks as semantic approval. |
| 2D | Dataset correction | Corrected wording and evidence, retained canonical IDs, and kept `fr-cross-009` as an excluded duplicate for audit history. Review statuses were not promoted by automated checks. |
| 2E | Final dataset audit | Rechecked JSONL structure, IDs, evidence locators, source status, category concerns, and scoring eligibility. |
| 3A | Retrieval metrics | Adapted the evaluator to the canonical dataset, filtered to approved rows, defined recall, any-gold hit and strict multi-evidence success, handled malformed input, and added focused tests. |
| 3B | Dataset review readiness | Refined candidate questions/evidence while retaining honest human-review status. |
| 4A | Human-review workflow | Documented review outcomes, privacy-preserving review records, disagreement/correction handling, and audit-trail rules in `data/eval/LABELING_GUIDE.md`. |
| 4B | Approval record | Recorded the reported expert approval on active questions; preserved the excluded duplicate. Reviewer identity/date were not supplied and were not fabricated. |
| 5A | BM25 readiness | Checked evaluator filtering, tests, CLI/output safety, and resource requirements before baseline execution. |
| 5B | Readiness inspection | Inspected dependencies, local models, indexes, Ollama and method CLI. Confirmed BM25 could run without embeddings. |
| 5C | Method selection | Updated the evaluator to run one retrieval method at a time and added mocked focused tests. |
| 5D | BM25 baseline | Ran BM25 at k=1, 3, 5, 10. Output: `data/eval/retrieval_bm25_stage5c.json`. |
| 6A / 6B | Vector setup and connectivity | Initial vector preparation was blocked by model-download connectivity. Diagnosed it read-only without changing dependencies or security settings. |
| 6D | Vector baseline | After the embedding model was locally available, evaluated the same approved set. Output: `data/eval/retrieval_vector_stage6a.json`. |
| 7A | Hybrid baseline | Evaluated hybrid retrieval on the same fixed set. Output: `data/eval/retrieval_hybrid_stage7a.json`. |
| 8A | Hybrid reranker | Evaluated the implemented reranker and compared ranking/latency against the other methods. Output: `data/eval/retrieval_hybrid_reranker_stage8a.json`. |
| 9A / 9B | Generation readiness | Inspected the `/ask` path, generation service, model selection and Ollama configuration before evaluation. |
| After 9B | Qwen generation run | Used local Ollama `qwen2.5:3b` through `/ask` on the same 109 approved questions. Retried 17 transient HTTP errors successfully; preserved both the original partial and recovered full result files. |
| Handoff | Results and limitations | Recorded metrics, denominators, commands, cost assumptions, qualitative owner review, and remaining real-user feedback work in this report and `optimisation.md`. |

### Key files

| Deliverable | Path |
|---|---|
| Canonical questions | `data/eval/questions.jsonl` |
| Labeling/review guide | `data/eval/LABELING_GUIDE.md` |
| Retrieval evaluator | `eval/retrieval.py` |
| Generation evaluator | `eval/generation.py` |
| Qwen full result / preserved partial result | `data/eval/generation_qwen25_3b_stage9_recovered.json` / `data/eval/generation_qwen25_3b_stage9.json` |
| Week 8 optimization summary | `optimisation.md` |

## 3. Retrieval results

All four saved result files use the same 109 approved questions, 89 answerable recall denominator, 20 unanswerable excluded from recall, and 8 active multi-evidence questions for strict success. Latency is per-query search latency only; startup, model loading, and index creation are excluded where the evaluator did not measure them.

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

Hybrid gives the best evidence coverage at k=10 (+3.93 percentage points recall and +4.50 points any-gold versus BM25) but strict multi-evidence success is 25% versus BM25's 50%. Its p50 search latency is about 11.9 times BM25. The reranker does not improve k=10 coverage or strict success over hybrid and raises p50/p95 latency. These results do not support a blanket quality/latency win; choose the method per product constraints and retain BM25 as the fast baseline.

Commands to reproduce retrieval results (choose fresh output paths; evaluator refuses overwrite):

```powershell
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method bm25 --output "project 2/data/eval/retrieval_bm25.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method vector --output "project 2/data/eval/retrieval_vector.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method hybrid --output "project 2/data/eval/retrieval_hybrid.json" --k 1 3 5 10
python "project 2/eval/retrieval.py" --questions "project 2/data/eval/questions.jsonl" --method hybrid_reranker --output "project 2/data/eval/retrieval_hybrid_reranker.json" --k 1 3 5 10
```

## 4. Generation results

`eval/generation.py` was run through the existing `POST /ask` endpoint using `qwen2.5:3b`. The recovered result at `data/eval/generation_qwen25_3b_stage9_recovered.json` covers all 109 approved questions (89 answerable, 20 unanswerable); the one excluded duplicate was not scored. An initial pass had 17 HTTP errors on `fr-single-040` through `fr-single-056`; an individual probe succeeded and all 17 retries then succeeded. The original partial output is preserved as `data/eval/generation_qwen25_3b_stage9.json`.

| Generation metric | Result | Denominator |
|---|---:|---:|
| Answer token-overlap F1 proxy | 0.307 mean | 89 answerable |
| Gold citation precision | 0.341 mean | 89 answerable |
| Gold citation recall | 0.449 mean | 89 answerable |
| Exact quote occurrence in published corpus text | 100% | 133 returned quotes |
| Correct abstention on unanswerable questions | 13/20 (65%) | 20 unanswerable |
| Unanswerable questions answered instead of abstained | 7/20 (35%) | 20 unanswerable |
| Answerable questions incorrectly abstained | 31/89 (34.8%) | 89 answerable |
| Abstention F1 | 0.406 | 109 completed |
| Server total p50 / p95 | 28.25 s / 37.81 s | 109 completed |
| Server retrieval p50 | 3.18 ms | 109 completed |
| Server generation p50 | 28.25 s | 109 completed |
| Prompt / completion tokens | 448,824 / 30,283 | 109 completed |

The answer F1 is a lexical proxy, not semantic correctness. Citation precision/recall compare article IDs with gold labels, not legal entailment. Exact quote matches prove only that quoted words occur in the corpus. The project owner reports reviewing the generated answers and considers them faithful. This is a qualitative owner review; it is not a numeric per-answer entailment score or a claim of legal correctness. The measured abstention behavior remains a separate limitation: the model answered 7 corpus-unanswerable questions and abstained on 31 answerable questions. API/client wall time is distinct from server timing. The run used local Ollama, so there was no metered API token charge; electricity, hardware amortization, and operating costs were not measured. The cost model below can calculate metered-provider charges when applicable rates are supplied.

Start the configured service from the workspace root in a separate terminal, then run from the workspace root using a fresh output path. For the run above, `OLLAMA_MODEL=qwen2.5:3b`; set that variable before starting Uvicorn:

```powershell
$env:OLLAMA_MODEL = "qwen2.5:3b"
python -m uvicorn api.app:app --app-dir "project 2/src" --host 127.0.0.1 --port 8002
python "project 2/eval/generation.py" --questions "project 2/data/eval/questions.jsonl" --corpus "project 2/data/processed/corpus.jsonl" --api-url "http://127.0.0.1:8002" --output "project 2/data/eval/generation_run.json"
```

For a metered provider, pass the actual configured rates explicitly:

```powershell
--prompt-usd-per-million-tokens <rate> --completion-usd-per-million-tokens <rate>
```

The cost formula is `(prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1,000,000`. A null estimate means rates were not supplied. Local Ollama inference has no per-token provider invoice in this model; electricity, hardware amortization, and operating costs are not included. Do not apply a rate for one provider/model to another.

Focused test commands used for the evaluation and service test suites:

```powershell
python -m unittest discover -s "project 2/tests" -p "test_generation_eval.py" -v
python -m unittest discover -s "project 2/tests" -p "test_retrieval_eval.py" -v
python -m unittest discover -s "project 2/tests" -p "test_generation.py" -v
python -m unittest discover -s "project 2/tests" -p "test_api.py" -v
```

## 5. User feedback and remaining work

No target-user feedback was collected in this session. Conduct moderated sessions with actual target users and record only anonymous response counts and task outcomes—no names, contact details, legal case facts, or other personal data. Suggested five-point items: (1) Was the question understood? (2) Was the answer useful for finding the relevant provision? (3) Could each citation be opened and matched? (4) Was abstention clear when evidence was insufficient? (5) What one change would improve usefulness? Ask users to rate confidence separately from legal correctness. Do not treat user satisfaction as legal validation.

Completed for this handoff: retrieval ablation across BM25, vector, hybrid, and hybrid plus reranker; one full Qwen 2.5:3b generation run on the approved fixed set; and the project owner’s qualitative faithfulness review. Groq follow-up is out of scope and is not needed for the local Ollama results. Remaining external work: collect structured feedback from real target users; measure local electricity/hardware operating cost if a total-cost figure is required; and evaluate a specifically selected generation optimization on the same fixed set before making a before/after generation claim. No claim of legal advice or current-law completeness follows from these evaluations.
