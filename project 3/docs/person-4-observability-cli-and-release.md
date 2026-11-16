# Person 4 — LangSmith Observability, Customer UI, Demo, and Release

## Mission

Make Shopline Ops inspectable and easy to demonstrate. Own optional LangSmith
tracing, a customer request page, the admin approval experience, run
instructions, performance reporting, and the final release assets.
Observability and UI behavior must never change graph decisions, approval
requirements, or side-effect behavior.

## Ownership

Primary files:

```text
agent/observability.py
agent/cli.py
web_app.py (or the agreed frontend directory)
requirements.txt
README.md (coordinate project overview edits)
postmortem.md
report.pdf
tests/test_observability.py
docs/release-checklist.md
```

Person 4 owns LangSmith configuration and reporting, not graph transitions,
MYTEK scraping, sandbox tools, or evaluation scenario definitions.

## Dependencies and order

- Wait for Person 1's public operator API and stable trajectory events.
- Wait for Person 2's tool results and sandbox reset/outbox behavior.
- Wait for Person 3's evaluator result schema and baseline scenarios.
- Agree with Person 1 on the public request/status API and with Person 2 on
  customer/order fields that may be displayed.
- Build customer and admin pages against those stable interfaces.
- Integrate tracing, run the demo, measure the completed workflow, then prepare
  release documentation.

The earlier prototype requirements/docs may mention Langfuse; this project
description selects LangSmith. Person 4 owns dependency and configuration
changes needed to make that migration. Do not add credentials to the repo.

## LangSmith integration

Provide an optional adapter using `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`,
and `LANGSMITH_PROJECT` (plus any required endpoint configuration). When
disabled or unavailable, the workflow continues locally with the same
trajectory and safety behavior.

Capture one run per operator request and map:

- every graph node to a run/span with concise input/output summaries;
- model proposal generation to a generation observation where supported;
- tool calls to tool spans with safe identifiers and timing;
- approval requested/approved/rejected/timed out to decision events;
- final status, step count, wall-clock latency, and token/cost metadata.

Redact customer contact details and secrets. Do not transmit full ticket
bodies, full product descriptions, credentials, or sensitive sandbox records
unless the team has explicitly reviewed and approved that data policy. A
tracing failure must not authorize, suppress, or repeat a side effect.

## Demo and measurements

Build two distinct views:

- **Customer page:** let a customer submit a product request or support ticket,
  provide only the customer-facing information needed for that request, and
  show a safe request/status confirmation. Do not expose internal notes,
  traces, operation IDs, other customers' records, or admin controls.
- **Admin page:** show the retrieved evidence and exact proposed products,
  prices, order total, ticket update, and notification. Keep approve/decline
  controls here. A customer submission must not count as admin approval.

The demo should show both product-order and support-ticket paths. On admin
approval, show the sandbox result; on rejection, show that no sandbox order or
notification was created. The customer page may show the resulting status but
must not imply a real MYTEK purchase or a real message was sent.

Report per-run steps, tool/model calls, tokens when available, estimated cost,
and latency. Summarize p50/p95 latency, average steps, recovery, injection
pass rate, and safety failures only from actual evaluation runs. Label
provider pricing assumptions and estimates; do not invent measurements.

## Release handoff

Document clean setup, environment variables, sandbox reset, run/demo, and
evaluation commands. Release only after confirming no credentials are
tracked, no live MYTEK checkout/payment or real notification is possible, the
approval and rejection paths work, duplicate actions remain idempotent, and
LangSmith-disabled mode preserves the same safety behavior.
