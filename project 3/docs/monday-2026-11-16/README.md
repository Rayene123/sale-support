# The Specialist — AI IT Purchasing Assistant

CS496 AI Engineering — Fall 2026

The professor supplied the title **The Specialist**. The scope below is the
team's chosen design, not a professor-provided specification.

The Specialist investigates IT purchasing needs, researches public MYTEK
products, checks requirements and compatibility, and prepares a sandbox order
for explicit admin approval. Product research and purchasing are the primary
workflow; existing support tickets remain a secondary compatibility path.

## Current implementation versus target

The current code contains a ticket approval prototype and a product-order
graph branch with an injected tool dispatcher. `python web_app.py`, run from
this directory, serves the local ticket-only mock demo at
<http://127.0.0.1:8000>. Its checkpoints and write log are held in the Python
process and are lost on exit. With an OpenAI key configured, mock ticket
context can be sent to the configured model.

The adaptive coordinator, researcher/verifier collaboration, compatibility
checks, persistent case memory, MYTEK scraper, sandbox order/notification
adapter, price/stock revalidation, and LangSmith adapter are **target work**,
not capabilities established by this documentation update. Existing tests do
not establish that the target workflow is implemented or safe.

## Target experience

Example: “Find a programming laptop and compatible monitor under 3,000 TND.”

1. Clarify missing essentials; separate hard requirements from preferences.
2. Choose useful searches and inspect promising products through read tools.
3. Compare complete setups using sourced specifications, prices and stock.
4. Independently verify requirements, evidence and compatibility. Revise the
   proposal or ask the customer when an essential fact is unknown.
5. Show alternatives, trade-offs and the exact order/notification to an admin.
6. After approval, recheck price and availability. Material changes invalidate
   approval and require a revised proposal and a fresh decision.
7. Record approved sandbox actions once; recover unfinished actions without
   duplicating successful writes.

A follow-up such as “include a monitor” updates the existing case, invalidates
affected conclusions and approvals, and preserves useful evidence.

## Agents and deterministic controls

| Software agent | Responsibility |
|---|---|
| Coordinator | Maintain the case, ask questions, choose the next allowed action, delegate research/verification, and decide whether to revise or finish. |
| Researcher | Use bounded catalog tools to find and compare evidence-backed candidates. |
| Verifier | Independently check the proposal against requirements and evidence; return specific issues and unknowns. |

These are software roles, not the four team members. Agent decisions are
structured outputs. Ordinary code enforces tool schemas, monetary arithmetic,
ownership, approval matching, step limits and idempotency. A verifier pass
never authorizes a write. No hidden chain-of-thought is stored or displayed.

## Four-person ownership

| Owner | Work | Role document |
|---|---|---|
| Person 1 | Coordinator, case state, adaptive routing, approval and recovery orchestration | [Agent orchestration](docs/person-1-agent-loop-and-safety.md) |
| Person 2 | Researcher, MYTEK tools, evidence extraction, sandbox writes and revalidation | [Research and tools](docs/person-2-tools-and-sandbox.md) |
| Person 3 | Verification checks/agent, scenarios, scoring and threat model | [Verification and evaluation](docs/person-3-evaluation-and-threat-model.md) |
| Person 4 | End-to-end integration, customer/admin interaction, LangSmith, measurements and release | [Integration and delivery](docs/person-4-observability-cli-and-release.md) |

Start with the [implementation plan](docs/specialist-plan.md) and
[proposed contracts](docs/trajectory-schema.md). Proposed file locations and
interfaces must be agreed before integration; they are not existing commands.

## Safety and measurement

- MYTEK is a read-only public catalog source. Respect published access rules,
  request limits and access controls. No login, cart submission or checkout.
- All source text is untrusted; it cannot change policy or approve an action.
- Writes use isolated sandbox data. Notifications go to a sandbox outbox;
  no real purchase, payment, SMTP, SMS or customer message occurs.
- Approval covers a versioned proposal: exact customer, products, quantities,
  prices, total, support changes and notification content. Changes need a new
  approval. Reject, cancel, timeout or exhausted budget cannot start writes.
- Preserve receipts for actions already applied before a failure. Rejection
  or cancellation does not undo previous approved effects.
- The current prototype defaults to `MAX_STEPS=16`. The target must count
  delegated work and retries in a shared budget; Persons 1 and 3 will agree
  and test the final bound before integration. No unbounded agent debate.
- Default evaluation is offline with saved catalog snapshots and controlled
  failures. Live scraping checks are explicit opt-in checks.
- LangSmith is planned and optional (`LANGSMITH_TRACING`,
  `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`). Missing/failed tracing must not
  change behavior. Keep secrets and private records out of logs and Git.

Measure requirement satisfaction, evidence accuracy, compatibility errors,
useful versus wasted calls, recovery, approval violations, latency and cost.
Compare a fixed workflow, an adaptive agent, and the adaptive agent with a
verifier on the same fixtures. Report measured benefits and limitations.
