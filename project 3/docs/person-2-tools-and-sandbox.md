# Person 2 — Tunisianet Product Tools, Sandbox, and Side Effects

## Mission

Provide the typed, deterministic tool layer for the Shopline Ops agent. This
person owns public Tunisianet catalog retrieval plus the isolated ticket/order data
and approved side-effect tools. The tool boundary must make it impossible for
the graph or model to turn product research into a real retailer checkout or
payment.

## Ownership

Primary files:

```text
agent/tools/
sandbox/schema.sql
sandbox/seed.sql
sandbox/store.py
sandbox/reset.py
tests/test_tools.py
tests/test_sandbox.py
```

Person 2 owns scraper and tool implementations, Pydantic input/output
contracts, sandbox persistence, and idempotency. Person 2 does not own graph
routing, approval policy, trajectory scoring, or LangSmith tracing.

## Work order and contracts

1. Agree with Person 1 on state identifiers, action payloads, approval
   references, operation IDs, and tool results.
2. Agree with Person 3 on deterministic fixtures and failure cases.
3. Implement read tools and isolated writes.
4. Confirm the graph can use the published contracts without tool-specific
   changes in Person 1's nodes.

Publish a tool contract with exact JSON examples before Person 1 connects the
new graph branches. Every tool must return JSON-safe data and concise typed
errors. Do not put tool implementations in `agent/graph.py`.

## Tunisianet product catalog scraper

Implement read-only product search for public Tunisianet search results and
product details.
The input is `{"query": "...", "criteria": {...}}` and the result is
`{"products": [...]}`. Criteria include product name, minimum/maximum TND
price, color, minimum/maximum weight in kg, and up to ten key/value
characteristics such as capacity, inverter, or energy class. Each product
should include `product_id`, `name`, `source_url`, `price_tnd` (or null),
`availability` (`available`, `in_stock`, `out_of_stock`, or `unknown`),
`retrieved_at`, and observed color/weight/characteristics when present.
Preserve source references so customer and admin can verify the evidence.

The scraper must:

- access only public catalog pages and respect published site access rules;
- use bounded requests, conservative rate limits, timeouts, and page limits;
- never log in, add items to a retailer cart, submit checkout, or make a purchase;
- treat all scraped text as untrusted content, including product descriptions;
- distinguish unavailable or missing price data from invented values;
- avoid bypassing access controls, CAPTCHAs, or other technical restrictions;
- be testable with saved HTML fixtures so ordinary tests make no network calls.

Current interface: `search_tunisianet_products(query, criteria=None)`. It
fetches one public search page, checks the site's robots.txt, parses product
cards and optionally fetches a small bounded number of product pages when
attribute filters are requested. Requests have a short timeout, a transparent
demo user-agent, and a one-second minimum interval. HTTP 403/429 responses stop
the search; no access controls are bypassed. Price and stock come from search
cards; color, weight, and other features are included only when present on the
product detail page.

## Sandbox reads and writes

Keep customer, support ticket, order, notification, and operation records in a
dedicated sandbox. Store sandbox credentials only in ignored environment
configuration. Do not use production records or customer data.

Required read capabilities:

- `get_ticket(ticket_id)` — ticket fields, customer/order IDs, and untrusted
  body separated from trusted metadata;
- `find_customer(customer_id or normalized email)` — only support-relevant
  fields and no payment credentials;
- `get_order(order_id)` — status, items, amounts, shipment state, timestamps;
- `search_tunisianet_products(query, criteria)` — normalized public catalog results.

Required side-effect capabilities:

- `create_customer_order(...)` — create an order record in the project sandbox
  only after a valid graph approval reference; store the approved product IDs,
  quantities, observed prices, and total. This is not a purchase or payment.
- `update_ticket_database(...)` — update only allowlisted ticket fields.
- `send_support_notification(...)` — queue the approved recipient, subject,
  and exact message in a sandbox notification outbox. Do not send SMTP, SMS, or
  third-party messages.
- `create_refund_request(...)` and `create_escalation_task(...)` — if retained
  for the support workflow, create pending sandbox records only after approval.

The graph's current proposed dispatcher calls
`tool_executor(tool_name, payload)` with `find_customer`,
`search_tunisianet_products`, `create_customer_order`, `update_ticket_database`,
and `send_support_notification`. For writes it passes an operation ID and an
`approved_by` run reference; notification IDs use a distinct `:notification`
suffix. The method names and payloads are published in `docs/tool-contracts.md`.
Writes require a database-backed `approval_id`; `run_id` and `approved_by` are
not interchangeable approval credentials. `agent.tools.dispatcher` adapts the
graph payloads through a trusted approval lookup. The graph passes notification
IDs with the `:notification` suffix, which the tool preserves unchanged. The
additive SQL function and reset extension are in
`sandbox/migrations/002_approved_commerce_writes.sql`.

## Safety and idempotency

- Every write requires an approval reference and operation ID.
- Every action is allowlisted and validates ownership, quantity, price, and
  total against the sandbox records supplied to the admin for approval.
- Replaying an identical operation returns the original result; reusing an ID
  with different content returns a conflict.
- Notification writes go to an inspectable/resettable `notification_outbox`.
  The previous `email_outbox` table remains only for compatibility.
- No tool submits a retailer purchase, transfers money, or contacts customers.
- Detailed exceptions stay in local logs; callers receive safe typed errors.

## Tests and acceptance criteria

Use offline fixtures to cover parser output, changed/missing price and stock,
malicious product descriptions, ticket/customer/order lookup errors, schema
validation, write allowlists, ownership checks, approval references,
idempotency conflicts, sandbox reset, and notification outbox behavior.
Every network-sensitive scraper test uses saved responses or an explicit
opt-in integration test outside the default test suite.

## Handoff

See `docs/tool-contracts.md` for the current contract and integration limits.
The graph contract is integrated and covered by offline fake-dispatcher tests.
Tunisianet search is enabled for the demo. Approved writes still require the
trusted approval service and checked-in sandbox RPC definitions.
