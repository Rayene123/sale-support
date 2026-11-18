# The Specialist release and test guide

The [November 16 team brief](monday-2026-11-16/README.md) is the acceptance
baseline. The Phase 4 workbench exercises the purchasing backend with a
minimal interface. Reviewers can open **Support tickets** in the same workbench
for the secondary fixture-based ticket flow.

## Setup and modes

Follow the [README setup](../README.md) from a clean checkout. Start Ollama
and run `python -m specialist` from Project 3. Enter the customer
passcode printed by the server at `http://127.0.0.1:8767/customer/`.
Use the separate reviewer passcode at `http://127.0.0.1:8767/admin/`.
Use the same hostname throughout the session.

The default harness uses fictional catalog listings, the actual local LLM,
and persistent local PostgreSQL through PGlite. The SQL schema, approvals,
actions, reset, and receipt lookup are shared with the hosted sandbox. The
app binds to loopback and authenticates two distinct test accounts using
server-held identities. Support reviews use process-local ticket fixtures in
both profiles. Keep the workbench on your machine.

| Option | Purpose |
| --- | --- |
| `--catalog live` | Read public Tunisianet listing pages under the existing retrieval limits. |
| `--planner rules` | Run the original deterministic laptop and monitor flow without Ollama. |
| `--port 8768` | Run a second profile on a separate port. |
| `--data-dir path` | Use a separate directory for cases, local SQL, and metrics. |
| `--sandbox supabase` | Connect to a dedicated sandbox after applying the schema, seed, and migrations 002–005. Set `SUPABASE_URL`, `SUPABASE_SANDBOX_URL`, and the server-side `SUPABASE_KEY`. |

Tunisianet supplies the live catalog because MYTEK's published robots rules
disallow the catalog search path. The test catalog is fictional. Sandbox
orders and outbox records never affect the retailer. [MYTEK robots rules](https://www.mytek.tn/robots.txt)

## Try a case

1. As the customer, ask for a laptop and compatible external monitor under
   2,900 TND. Omit the budget first to exercise clarification.
2. Read the findings and the listing evidence. Use the reply form to change
   the requirements on the same case.
3. As the reviewer, open the case to review the product quantities, exact
   prices, total, notification, and revision. Approve the proposal.
4. Execute one action to record the sandbox order. Execute again to record
   the sandbox outbox notification. The page shows each confirmed receipt.
5. Use **Run trace** on the reviewer page to see actual steps and timings.
   The customer page shows its own activity and findings.

The integration test supplies a controlled price change after approval, then
drops a real committed notification response. It checks that the reviewer
must approve the new total, and that retry recovers the confirmed receipt.

## Reset and evaluate

Stop the workbench before running `python -m specialist --reset-local`.
Use the same profile switches as when starting the app. This clears that
profile's local cases and restores its sandbox fixtures. Hosted resets use
`python -m specialist.sandbox.reset --supabase` against the dedicated sandbox.

```powershell
python -m pytest -q
npm test --prefix specialist/sandbox/sql
python -m evaluation.comparison
python -m evaluation.legacy.run
python -m evaluation.local_model
```

The last command invokes the selected local model. Benchmark results contain
case outcomes, false positives, p50 and p95 latency, model calls, catalog
calls, and token counts where Ollama publishes them. The local model incurs
zero provider charges. Local hardware and electricity costs are unmeasured.

## Observability and privacy

Each command writes an allowlisted measurement in the profile's
`metrics.jsonl`. To export coordinator, researcher, verifier, reviewer and
sandbox spans, set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY` and
`LANGSMITH_PROJECT`. Case and run IDs link commands and spans. Raw prompts,
retailer text, customer details, products and approved payloads stay out of the
export. Network export runs on a bounded background queue.

## Release checklist

- Verify customer and reviewer sessions, case scoping, and stale approval.
- Verify the catalog and sandbox labels before testing either mode.
- Run the local database migration, reset and recovery checks.
- Record the offline comparison and the local model benchmark with failures.
- Verify the hosted sandbox using the approval and receipt flow below.
- Confirm a trace arrives in the team's LangSmith project when configured.
- Keep the workbench as the test interface for the later frontend.

## Verification report · November 18

| Check | Observed result |
| --- | --- |
| Python suite | 162 passed after the refactor, including role isolation, ticket review, a failed reset and the HTTP recovery flow backed by local SQL. |
| SQL suite | 12 checks passed against the project's schema and migrations. |
| Secondary support and order workflow | 45 offline scenarios passed. |
| Fixed / adaptive / adaptive plus verifier | 14/30, 11/30 and 30/30 correct. The verifier mode produced zero false positives. |
| Local Ministral model | [8/8 scenarios](../evaluation/reference/specialist-local-model.json), zero false positives, p50 6.51 s and p95 34.53 s. |
| Browser workbench | The refactored launcher completed a customer request using Ollama, reviewer approval, and two confirmed local SQL receipts in Chromium. |
| Live catalog | The workbench inspected one laptop and three monitors from Tunisianet. The listings did not establish a shared connection, so the case stopped before approval. |
| Clean export | A fresh Python environment and Node install from the refactored files, the launcher, the full Python suite and a local reset succeeded. |
| Hosted Supabase sandbox | Migrations 002–005 applied in one transaction. The workbench used Ollama and fictional listings, blocked execution before approval, required fresh approval after a simulated price change, and recovered a confirmed notification after a simulated lost reply. Replay left one order and one queued notification. A fresh hosted client read both receipts. |

The model sample covers display, USB, Ethernet, cross-product dimensions,
missing specifications, an over-budget setup and a clarification. Its timing
includes local generation and fictional catalog calls. It is a small fixture
sample. The comparative rules benchmark covers a separate 30-case set.

After the refactor, the same model benchmark passed 8/8 with zero false
positives. The deterministic comparison and 45 earlier graph scenarios kept
their results. The refactored app opened five cases saved before the folder
changes and read both receipts from the existing hosted test order. A bounded
live catalog check returned five candidates and 12 specs on one exact listing.

## Postmortem

The first model runs exposed invented default specs and a translated network
switch label that the verifier could not recognize. The planner now grounds
hard spec values in the request and preserves previously stated requirements.
The canonical type accepts the translated label. An exploratory browser
request saw the model associate dimensions with the wrong products and ask
for PCIe facts the listings did not supply. Verification stopped the order
and showed both gaps. A separate browser case completed with two receipts.
Unknown measurements and incompatible dimensions also stopped proposals in
the benchmark.

The live model's first search was too narrow to find a laptop. The second
research pass now uses bounded category searches for known laptop and monitor
types and can broaden both ends before trying another pairing.

The hosted run produced sandbox order `S-f7d8e7a971a74dc983d395c901709bf8`.
The migration used the checked-in SQL permissions. A hosted privileges check
confirmed that the service role can access the outbox and execute the order and
receipt functions, while anonymous and authenticated client roles lack those
permissions. The hosted sandbox reset was left for intentional fixture resets.

LangSmith live verification still requires the team's LangSmith key. Local
tests verify trace filtering and isolate a trace transport failure.
