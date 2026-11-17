# Proposed Operator State and Trajectory Schema

This is the Person 1 graph state and trajectory contract. Person 2's tool
payloads are documented in `docs/tool-contracts.md`; Person 3 owns evaluations.

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
| `product_criteria` | Optional name, TND price bounds, color, kg weight bounds, and up to ten technical key/value filters. |
| `price_min_tnd`, `price_max_tnd` | Normalized TND bounds used to filter and revalidate returned products. |
| `ticket`, `customer`, `order`, `products` | Retrieved evidence; source text remains untrusted. Customer state excludes email. |
| `selected_products` | Exact product IDs and quantities selected by the customer from returned results. |
| `draft` | Exact support proposal or sandbox order and notification proposal. |
| `approval` | Structured admin ticket decision or customer order confirmation bound to the proposal's operation ID. |
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

`running`, `awaiting_customer_selection`, `awaiting_approval`, `approved`,
`rejected`, `completed`, `failed`, `timed_out`, and `step_limit_reached`.
Terminal statuses have no outgoing edges. A rejected, failed, timed-out, or
step-limited run has no applied actions unless a previous approved action has
an explicit recorded receipt.

## Customer product selection

The first product-order pause returns the matching `products` list and status
`awaiting_customer_selection`. Resume the same `run_id` with:

```json
{
  "items": [
    {"product_id": "Tunisianet-source-product-id", "quantity": 1}
  ]
}
```

The graph accepts only products from the returned list with a known price and
available stock, and rechecks every supplied criterion before drafting an
order.

## Product order proposal

```json
{
  "operation_id": "generated-id",
  "customer_id": "sandbox-customer-id",
  "items": [
    {
      "product_id": "Tunisianet-source-product-id",
      "name": "product name",
      "quantity": 1,
      "unit_price_tnd": 0.0,
      "source_url": "public product page URL"
    }
  ],
  "total_tnd": 0.0,
  "notification": {
    "channel": "sandbox_outbox",
    "customer_id": "sandbox-customer-id",
    "message": "exact text shown for approval"
  },
  "evidence_ids": ["product source IDs"]
}
```

For support-ticket notifications the context field is `ticket_id` instead.
Neither proposal includes customer email. The customer confirms an order in
the customer page; the admin dashboard handles support tickets only. This is a
sandbox order proposal only, never a retailer checkout or payment.
