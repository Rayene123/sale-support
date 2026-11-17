# Person 1 — LangGraph Agent Loop and Safety

## Mission

Own the control plane that handles a customer support ticket or product-order
request. LangGraph gathers approved evidence through Person 2's tools, drafts a
structured response or sandbox order, pauses for an admin ticket decision or
customer order confirmation, and orchestrates only the exact actions covered
by that decision.

The graph is the safety boundary. Model output and scraped page content are
untrusted. Neither can call a write tool, change the approval policy, change
the approved customer/product/order, or extend a run indefinitely.

## Ownership

Primary files:

```text
agent/state.py
agent/graph.py
agent/checkpoint.py
agent/limits.py
tests/test_graph.py
tests/test_checkpoint.py
docs/trajectory-schema.md
```

Person 1 owns state types, transitions, checkpoints, approval validation,
bounded execution, and graph-level orchestration. Person 1 does not implement
the Tunisianet scraper, Supabase access, order persistence, notification delivery,
or LangSmith tracing.

## Integration contract (Person 2's published tools)

Use `agent.tools.dispatcher.make_tool_executor` for all reads and writes.
Reads are `get_ticket(ticket_id)`, `find_customer(customer_id)`,
`get_order(order_id)`, and `search_tunisianet_products(query, criteria)`. Criteria
cover product name, TND price bounds, color, kg weight bounds, and key/value
technical characteristics. The dispatcher
returns inner `data` for record reads and JSON-safe success results for writes.
The graph validates record IDs and retains only support-relevant customer
fields in state.

Write actions are `update_ticket_database`, `create_customer_order`, and
`send_support_notification`. `run_id` is passed as `approved_by` only as a
run reference; it is never an `approval_id`. The authenticated approval
service must first persist one trusted record for each exact action payload,
then resume the graph. Ticket updates use `<operation_id>:ticket`, all
notifications use `<operation_id>:notification`, and order creation uses the
base operation ID. The dispatcher resolves each pre-existing approval record
and passes its approval ID separately. The graph must not create approval
records or continue if any action lacks a matching record.

Product requests may include structured criteria, including `price_min_tnd` /
`price_max_tnd`, or a TND price range in request text. The graph returns the
matching catalog products in `awaiting_customer_selection`; the customer page
submits selected product IDs and quantities before the graph drafts an order
for customer confirmation. A selection is restricted to returned products
that are available, have a known price, and still satisfy every criterion.
Orders use customer confirmation; support tickets use admin approval.
The customer-facing prompt is parsed with the configured OpenAI model into a
typed search intent. If the model is unavailable, a basic parser fallback is
marked in state and shown to the customer. Product name matching also filters
known accessories when the requested product is a laptop.
Notifications carry exactly one context
identifier (`ticket_id` for support, `customer_id` for product orders), plus
the channel and exact message shown for approval. Never put customer email in
graph state or write payloads; Person 2 resolves it privately inside the
trusted sandbox approval/write boundary.

Order line items include product ID, name, source URL, quantity, and observed
unit price. Tunisianet search uses its read-only public search page; the graph
must surface source errors and must not invent products. The separate customer and admin
pages are maintained by the project integration owner, outside Person 4's
scope. Person 3 owns evaluation fixtures/scoring, and Person 4 owns LangSmith
observability and release work.

## State responsibilities

Maintain serializable state for:

- run ID, request type, customer/ticket identifiers, step count, and status;
- retrieved ticket, non-sensitive customer context, current order, Tunisianet
  product results, full product criteria, and customer selection;
- the structured support reply or proposed order and notification;
- approval decision and operation IDs;
- tool call summaries, concise errors, trajectory events, and applied actions.

Do not put API clients, credentials, callbacks, or hidden chain-of-thought in
state. Keep ticket/product source text separate from trusted IDs and policy.
Coordinate new public state fields with Persons 2–4 before freezing the schema.

## Graph responsibilities

The target workflow is:

```text
START
  → validate request and initialize run
  → inspect support/customer/order context
  → if product selection is needed, search Tunisianet through Person 2's read tool
  → draft support response or exact sandbox order and notification
  → interrupt for admin ticket approval or customer order confirmation
  → if approved, call only the approved sandbox action tools
  → finish with completed, rejected, failed, or step_limit_reached
```

Required node behavior:

1. Validate request and IDs; invalid input terminates clearly.
2. Read only the context needed through Person 2's dispatcher; missing context
   is an error, never a reason to invent customer or product facts.
3. Treat scraper output and all customer text as untrusted data.
4. Validate drafts against typed schemas, Person 2's ticket-status/label
   allowlists, product evidence, and tool allowlists before approval.
5. Show exact product IDs, quantities, observed prices and total for an order;
   show exact ticket mutation and notification text for support work.
6. Pause with LangGraph `interrupt`; resume the same checkpoint with a
  structured decision tied to the exact operation ID (admin for tickets,
  customer for their own order).
7. On approval, orchestrate Person 2's approved actions in a defined order.
   Never run any action on rejection, cancellation, invalid approval, timeout,
   or step exhaustion.
8. Record a concise trajectory event for each node and tool attempt. Do not
   record chain-of-thought or unnecessary personal information.

Order creation here means a sandbox order record only. It must not submit a
retailer cart, authorize payment, or imply that a real purchase occurred.

## Checkpoint and stop rule

Use one process-persistent LangGraph checkpointer for the prototype and a
stable thread ID per run. Resuming must never create a new execution. Repeated
resume must not repeat an action; Person 2's write tools provide durable
idempotency, while the graph validates operation IDs and completed checkpoints.

Configure `MAX_STEPS` (current prototype default `20`) and count graph nodes
and tool attempts. Include the customer-selection interrupt in the budget.
Before entering another node or retrying a tool, stop with
`step_limit_reached` when the limit would be exceeded. Recheck the default when
Person 2's scraper/order/notification calls are integrated and agree the bound
with Person 3.

Invariant: every node/tool attempt consumes one step, every transition checks
the remaining budget, and terminal states have no outgoing transition.
Therefore a run cannot exceed `MAX_STEPS`.

## Public interface

Target one stable JSON-serializable API:

```python
run_operator(request, approval=None, *, run_id=None, tool_executor=None, selection=None) -> dict
```

Calls may return `awaiting_customer_selection` or `awaiting_approval`; resume
the same checkpoint with the original `run_id` and respectively a structured
selection or exact structured decision. Customer-order confirmation is not
an admin ticket action. Keep `run_ticket(...)` as a
compatibility wrapper while the support-ticket UI depends on it.
`tool_executor(tool_name, payload)` is injected by the application and
dispatches only Person 2's published implementations.

## Person 1 acceptance criteria

- Product lookup and support-ticket paths use mocked dispatchers without
  network/database calls in graph tests.
- No action tool runs before approval.
- Approval authorizes only the exact displayed operation; rejection and
  malformed or mismatched approval write nothing.
- Duplicate resume cannot duplicate actions.
- Tool/model failure and step exhaustion terminate with explicit statuses.
- Every trajectory stays within the configured step bound and is JSON-safe.
- The graph passes Person 2's published tool names, payloads, and suffixed
  operation IDs without bypassing the approval lookup or sandbox.

## Handoff

Provide the frozen state/trajectory schema, public API, terminal status list,
checkpoint behavior, stop-rule proof, and the event list Person 4 should map to
LangSmith runs, spans, and approval events.

Reliability changes and remaining boundaries: [Person 1 handoff](person-1-fixes-handoff.md).
