# The Specialist — Proposed State and Trajectory Contracts

Status: proposed, not frozen or implemented in full. The original ticket/order
shapes below are a starting point; the Specialist extensions at the end define
the next contract review. Persons 1–4 must agree exact schemas before integration.

## State

The graph state is JSON-serializable. Optional fields are populated as the
workflow advances; credentials, API clients, callbacks, and hidden reasoning
are never stored in state.

Core fields:

| Field | Purpose |
|---|---|
| `run_id` | Stable graph/checkpoint identifier. |
| `request_type` | `support_ticket` or `product_order`. |
| `ticket_id`, `customer_id`, `product_query` | Request identifiers/context. |
| `ticket`, `customer`, `order`, `products` | Retrieved evidence; source text remains untrusted. |
| `draft` | Exact support proposal or sandbox order and notification proposal. |
| `approval` | Structured admin decision bound to the proposal's operation ID. |
| `operation_id` | Idempotency and approval binding for proposed actions. |
| `tool_calls`, `errors`, `trajectory` | Concise observability and evaluation records. |
| `applied_actions` | JSON-safe receipts returned by approved sandbox writes. |
| `step_count`, `status` | Bounded progress and explicit terminal state. |

## Approval decision

```json
{
  "decision": "approve",
  "operation_id": "the-exact-operation-id-shown-to-the-admin"
}
```

Only `approve` or `decline` with the exact operation ID is accepted
(`reject` remains a compatibility alias; `timeout` is a terminal decision).
Free-form instructions, missing fields, extra fields, and mismatched IDs fail
closed.

## Trajectory event

```json
{
  "node_name": "request_approval",
  "input_summary": "Validated order proposal ready for review",
  "output_summary": "Admin approval requested",
  "start_timestamp": "ISO-8601 timestamp",
  "end_timestamp": "ISO-8601 timestamp",
  "resulting_status": "awaiting_approval"
}
```

Summaries contain concise decisions and identifiers only. They must not contain
chain-of-thought, secrets, full customer contact details, or unfiltered page
content.

## Status values

`running`, `awaiting_approval`, `approved`, `rejected`, `completed`, `failed`,
`timed_out`, and `step_limit_reached`. Terminal statuses have no outgoing
edges. A rejected, failed, timed-out, or step-limited run has no applied
actions unless a previous approved action has an explicit recorded receipt.

## Product order proposal (shape pending Person 2 confirmation)

```json
{
  "operation_id": "generated-id",
  "customer_id": "sandbox-customer-id",
  "items": [
    {
      "product_id": "MYTEK-source-product-id",
      "name": "product name",
      "quantity": 1,
      "unit_price_tnd": 0.0,
      "source_url": "public product page URL"
    }
  ],
  "total_tnd": 0.0,
  "notification": {
    "channel": "sandbox_outbox",
    "recipient": "sandbox customer reference",
    "message": "exact text shown for approval"
  },
  "evidence_ids": ["product source IDs"]
}
```

This is a proposed sandbox order only. Exact required/allowed fields must be
confirmed by Person 2 before graph integration.

## Planned Specialist extensions — contract review required

These additions describe the target; existing Python state and API do not yet
implement this complete contract. Keep compatibility adapters explicit.

| Contract | Required information | Owner |
|---|---|---|
| Requirements | case/customer ID, revision, purpose, budget/currency, hard constraints, preferences, known equipment, unresolved questions | Person 1 |
| Product evidence | evidence/product ID, source URL, retrieved time, field/value/unit, missing fields and untrusted source attribution | Person 2 |
| Research task/result | case/run IDs, requirement revision, delegated goal, remaining shared budget, candidates, evidence IDs, trade-offs and unresolved facts | Person 2 with Person 1 |
| Verification | proposal/requirements revisions, pass/fail/unknown findings, issue code/severity, affected items/constraints, evidence IDs and next checks | Person 3 |
| Proposal | immutable revision, customer, exact items/quantities/prices/total, currency, notification, evidence and verification references | Person 1 with Person 2 |
| Approval | trusted admin identity/reference, case/run ID, exact proposal revision/hash, action operation IDs, decision and expiry | Person 1 |
| Revalidation | proposal revision, check time/freshness limit, observed price/stock, material differences, success/unknown/failure | Person 2 |
| Action receipt | operation ID, approved payload identity, action type, persisted outcome, completion time and safe error/retry metadata | Person 2 |

An exact operation ID in the older approval example is not the full target
approval protocol. Reject stale revisions, altered payloads, expired decisions
and untrusted approval references. A material change creates a new proposal
revision and new operation IDs; retries of an unchanged approved action retain
its original ID. Unknown freshness or stock blocks automatic execution.

Track case revisions separately from run IDs. Requirement changes invalidate
affected proposals, verification and approval, while prior applied receipts
remain immutable. Define restart versus resume and per-customer case isolation.
Proposed additional statuses include `awaiting_clarification`,
`verification_blocked`, `reapproval_required`, `partially_completed`, and
`handoff_required`; agree exact enum/transitions before wiring them.

Extend events with case/run ID, parent/delegation ID, actor role, event type,
requirement/proposal revision, evidence/issue references, allowed action and
concise decision summary, budget consumed/remaining, timing and outcome.
Delegated work consumes the parent budget. Never log hidden chain-of-thought.
Person 4 maps these structured events to optional LangSmith spans.

Contract freeze requires shared JSON examples for: clarification, incompatible
setup, verified proposal, changed price requiring fresh approval, and a retry
after order persistence but before notification completion. Persons 1–3
validate those examples; Person 4 confirms integration and trace usability.
