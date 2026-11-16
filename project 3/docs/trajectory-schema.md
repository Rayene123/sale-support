# Proposed Operator State and Trajectory Schema

This is the Person 1 schema proposal for the ecommerce workflow. Person 2 must
confirm tool names/payloads and Person 3 must confirm trajectory fields before
the integration contract is frozen.

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
