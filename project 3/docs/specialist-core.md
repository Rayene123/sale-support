# The Specialist core — Person 1–3 handoff

The original purchasing goal is in [the team plan](specialist-plan.md).
The backend is available through \`agent.specialist.coordinator.Specialist\`.
The original graph and ticket prototype still run independently.

## Server API

| Call | Result |
| --- | --- |
| \`start(customer_id, text)\` | Creates a durable case. Returns a question, source failure, verified proposal or specific verification gaps. |
| \`revise(case_id, customer_id, text, expected_revision=...)\` | Updates the current case. Carries forward stated constraints and fresh product evidence, and invalidates the old proposal. |
| \`store.get(case_id, customer_id)\` | Returns the owner-scoped case with findings, evidence, alternatives, trajectory, status and receipts. The raw state is for trusted server code. |
| \`research(case_id, customer_id)\` | Resumes a case whose initial research was interrupted. |
| \`decide(case_id, customer_id, reviewer_id=..., revision=..., proposal_hash=..., decision=...)\` | Records a trusted reviewer decision for the exact snapshot. A decision is not a write. |
| \`execute_next(case_id, customer_id)\` | Rechecks the order, executes at most one approved action or recovers its confirmed receipt. |

Create the service with \`Specialist(CaseStore(".specialist/cases.sqlite3"))\`.
The default researcher uses the existing bounded Tunisianet tools. For offline
work, pass \`eval.specialist_fixtures.Catalog().researcher()\`. Reads and case
revisions work without an order writer. Use \`SandboxWriter(SandboxStore.from_env())\`
for the dedicated Supabase sandbox after applying schema, seed and migrations
002–005. Phase 4 supplies authenticated customer and reviewer identities
and selects fields appropriate for each view. A user-provided identity or ID
from a request body is not authentication.

## Evidence and decisions

- The bounded coordinator asks for missing essentials, delegates a separate
  search and exact product detail inspection for each role, and broadens
  research when no pair passes. It retains eligible evidence on a revision.
- The independent verifier records \`pass\`, \`fail\` or \`unknown\` with the exact
  field, source URL, product ID and retrieval time. The proposal contains only
  items that pass. Alternatives include reasons for rejection or uncertainty.
- The supported scope is one laptop and/or one external display, a total TND
  budget, laptop RAM/storage, external display size and native resolution,
  and direct HDMI, DisplayPort or explicit USB-C DisplayPort Alt Mode.
  A requested resolution/refresh combination needs evidence on both ends.
  This core does not verify adapters, docks, charging, inferred display modes
  or arbitrary peripherals. Missing essential evidence blocks a proposal.
- Revalidation fetches each approved listing again. A still-valid changed pair
  produces a new proposal, hash and action IDs with \`reapproval_required\`.
  If the change leaves an item unavailable or unverified, the case reports
  \`verification_blocked\` and can be revised before a new proposal is made.
- Sandbox action intents are persisted before execution. After a restart,
  an uncertain write is checked by its exact action, operation ID, approved
  payload and run. Confirmed receipts are retained and the next execution
  processes only the unfinished action. An unconfirmed read stops recovery.
- The shared default budget is 96 counted coordinator, tool, verification and
  write attempts across a case, with at most eight case revisions, up to two
  searches per role per research pass, three exact detail reads per role per
  search, and 18 candidate checks per pass. The lower-level catalog also caps
  redirects and response size. This is a local, single-host case store.

## Reproduce the current checks

From Project 3 with its Python dependencies:

    python -m pytest -q
    python -m eval.specialist --output eval/results/specialist-comparison.json

The comparison uses the same 30 fictional catalog scenarios for all modes.
Fixed research inspects the first result per role. Adaptive research
considers more candidates and validates local facts but skips the relationship
check. Adaptive plus verifier checks both sources together. The two
comparison modes expose candidates rather than approvable proposals.

| Mode | Expected result matched | Candidate offered where none was valid | Mean catalog calls |
| --- | ---: | ---: | ---: |
| Fixed | 14/30 | 4 | 3.87 |
| Adaptive | 11/30 | 9 | 7.40 |
| Adaptive plus verifier | 30/30 | 0 | 8.60 |

The fixture benchmark also emits per-case local latency. It makes no provider
calls. Pytest additionally exercises five untrusted-source cases, owner
isolation, clarification, revisions, price and stock changes, restart,
expired decisions, partial failure and lost responses. The SQL test harness
(\`cd tests/sql\`, \`npm install\`, \`npm test\`) applies the real migrations to an
isolated PostgreSQL runtime. A read-only live check used the original laptop-and-monitor request under
3,000 TND. The researcher inspected Tunisianet category results and the
exact product pages. The coordinator proposed a 1,328 TND pair after
finding published HDMI evidence at both ends. No approval or write was
made. This is one observed catalog run. Hosted Supabase integration still
needs live validation. The new core uses deterministic delegation
and verification, and the old workflow retains its existing optional LLM
path. Phase 4 owns website integration, authorization, LangSmith and release.
