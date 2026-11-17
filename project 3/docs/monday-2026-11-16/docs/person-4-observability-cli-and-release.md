# Person 4 — Integration, LangSmith and Delivery

## Mission and ownership

Connect The Specialist into a coherent customer/admin demonstration and make
its behavior measurable. Own optional LangSmith tracing, public interaction,
setup instructions, performance reporting and final delivery. Do not duplicate
coordinator decisions, scraping or verifier rules.

Target ownership: `agent/observability.py`, agreed CLI/application adapter,
`web_app.py` or agreed frontend, dependency/configuration documentation,
integration/tracing tests, `README.md`, `postmortem.md`, final report and
release checklist. Some target modules do not exist yet.

## Steps

1. Agree request/resume/status APIs with Person 1, tool receipts with Person 2,
   and verification/evaluation outputs with Person 3. Develop against mocks
   while these interfaces stabilize.
2. Connect customer requests, clarification replies, changed requirements,
   evidence-backed comparisons and case progress. Display concise actions and
   findings, not hidden reasoning or invented progress.
3. Provide a separate admin review flow showing exact proposal revision,
   products, prices, quantities, total and notification. Customer requests are
   not approval. Show changed proposals and require renewed decisions.
4. Show partial completion accurately, including persisted receipts and what
   remains unfinished. Do not hide failures or add fallback writes.
5. Add optional LangSmith runs/spans for coordinator, researcher, verifier,
   delegation, tools, revisions, approval and recovery. Use shared case/run
   IDs, redact secrets/contact details and filter source text.
6. Collect real latency, tool/model calls and tokens where available. Report
   p50/p95, estimated cost per 100 runs and Person 3's quality/safety comparisons.
   Distinguish estimates from measured values; never invent provider prices.
7. Verify clean-clone setup, sandbox reset, demo and evaluation commands.
   Assemble the final report and postmortem from committed results.

## Boundaries and acceptance

LangSmith is the selected target, not Langfuse. Configuration is optional via
`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`; tracing
failure must not authorize, suppress or duplicate actions. Keep local event
records sufficient for offline evaluation.

Customer views expose only their case, never another customer's records,
admin controls or private traces. Define and test the admin authorization
boundary before presenting the app as multi-user. A separate page alone is
not access control.

Demonstrate the complete purchase case from `specialist-plan.md`, plus the
existing ticket path as a secondary flow. Label saved-page fixtures, simulated
failures and sandbox writes honestly. No live checkout/payment or real
notification is introduced.

Deliver run instructions, integration tests, trace examples, measurements,
release checklist, report and postmortem. The report must distinguish current
capabilities, verified results and remaining limitations.
