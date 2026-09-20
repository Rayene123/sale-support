# Project 0 - Postmortem

The sentiment benchmark compares recorded Groq GPT-OSS 20B, Ollama TinyLlama 1.1B and Qwen2.5 14B runs on 75 items. An additional Astra chat evaluation is included with explicit limitations. The earlier SQL prompts are not part of this experiment.

## What went wrong

**Output compliance dominated TinyLlama's result.** All 75 responses violated the exact-label contract, giving 0/75 under the shared scorer. Responses often contained conversational prose rather than a label. This demonstrates failure of this configuration and prompt contract; it does not prove the model understands no sentiment. We preserved these failures instead of repairing predictions by hand.

**The original scorer hid latency for malformed answers.** It skipped rows before collecting their latency and counted execution failures as parse errors. Consequently TinyLlama had no latency summary despite 75 recorded timings. The corrected aggregation includes all recorded request timings and separates parse from execution errors. Groq and Qwen score 69/75 and 72/75 respectively; the raw historical responses remain unchanged.

**Some labels need independent review.** Qwen and Groq misclassified item 012's ironic praise. Qwen read item 037's indirect criticism as positive. Item 072 can be read as negative if working media is factual rather than praise. References were not revised after seeing results. Two people must independently review the labels and document the decisions before a new frozen run.

**Astra was not tested under equivalent conditions.** Its 73/75 answers came from a conversation where the reference labels were already visible. No independent API calls, per-request timing, usage, or cost were recorded. This is a non-blind supplementary result, not evidence that Astra outperformed the other models. A configured runner exists, but a blind API run is still required.

**Reproducibility and cost records are incomplete.** The repository does not document the original data source, a development split, completed dual review, historical run dates, local hardware, decoding tokens/second, or local operating/labor costs. Current Groq list pricing can estimate API cost from usage, but it cannot establish the historical bill or a numeric local break-even point.

## What worked and what we learned

The 75 IDs, texts and references align across all four result files. Exact automatic scoring exposes format failures consistently. Combining 300 per-item records makes summary calculations and individual disagreements traceable. Qwen is the provisional choice among measured runs for accuracy and recorded latency, conditional on hardware and total operating cost. One small run cannot establish a general model ranking.

## Next iteration

Freeze the dataset after independent review and record its provenance. Use separate development examples before freezing the shared prompt. Run Astra through the API without references in its input. Record timestamps, settings, exact model versions, hardware, token rates and cost assumptions. Recompute the same metrics for every model and revisit the choice at 100x traffic. Preserve raw outputs, including failures, rather than tuning the test set to improve scores.
