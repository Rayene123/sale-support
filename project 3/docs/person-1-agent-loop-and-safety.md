# Person 1 — LangGraph Agent Loop and Safety

## Mission

Own the control plane that handles a customer support ticket or product-order
request. LangGraph gathers approved evidence through Person 2's tools, drafts a
structured response or sandbox order, pauses for an admin decision, and
orchestrates only the exact actions covered by that approval.

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
the MYTEK scraper, Supabase access, order persistence, notification delivery,
or LangSmith tracing.

## Dependencies

Before connecting new nodes, agree with Person 2 on tool names, inputs,
outputs, retry behavior, operation IDs, and which actions write sandbox state.
Agree with Person 3 on the trajectory fields before freezing event names.
Person 4 consumes the resulting stable graph and trajectory events for
LangSmith. Until those contracts exist, Person 1 may work against mocked tool
adapters but must not duplicate another person's tool implementation.

## State responsibilities

Maintain serializable state for:

- run ID, request type, customer/ticket identifiers, step count, and status;
- retrieved ticket, customer, current order, and MYTEK product results;
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
  → if product selection is needed, search MYTEK through Person 2's read tool
  → draft support response or exact sandbox order and notification
  → interrupt and request explicit admin approval
  → if approved, call only the approved sandbox action tools
  → finish with completed, rejected, failed, or step_limit_reached
```

Required node behavior:

1. Validate request and IDs; invalid input terminates clearly.
2. Read only the context needed for the request; missing context is an error,
   never a reason to invent customer or product facts.
3. Treat scraper output and all customer text as untrusted data.
4. Validate drafts against typed schemas and tool allowlists before approval.
5. Show exact product IDs, quantities, observed prices and total for an order;
   show exact ticket mutation and notification text for support work.
6. Pause with LangGraph `interrupt`; resume the same checkpoint with a
   structured approve/decline decision tied to the exact operation ID.
7. On approval, orchestrate Person 2's approved actions in a defined order.
   Never run any action on rejection, cancellation, invalid approval, timeout,
   or step exhaustion.
8. Record a concise trajectory event for each node and tool attempt. Do not
   record chain-of-thought or unnecessary personal information.

Order creation here means a sandbox order record only. It must not submit a
MYTEK cart, authorize payment, or imply that a real purchase occurred.

## Checkpoint and stop rule

Use one process-persistent LangGraph checkpointer for the prototype and a
stable thread ID per run. Resuming must never create a new execution. Repeated
resume must not repeat an action; Person 2's write tools provide durable
idempotency, while the graph validates operation IDs and completed checkpoints.

Configure `MAX_STEPS` (current prototype default `16`) and count graph nodes
and tool attempts. Before entering another node or retrying a tool, stop with
`step_limit_reached` when the limit would be exceeded. Recheck the default when
Person 2's scraper/order/notification calls are integrated and agree the bound
with Person 3.

Invariant: every node/tool attempt consumes one step, every transition checks
the remaining budget, and terminal states have no outgoing transition.
Therefore a run cannot exceed `MAX_STEPS`.

## Public interface

Target one stable JSON-serializable API:

```python
run_operator(request, approval=None, *, run_id=None, tool_executor=None) -> dict
```

The first call may return `awaiting_approval`; a resumed call supplies the
original `run_id` and exact structured decision. Keep `run_ticket(...)` as a
compatibility wrapper while the support-ticket UI depends on it. For product
orders, `tool_executor(tool_name, payload)` is injected by the application and
dispatches only Person 2's agreed tool implementations. This adapter is a
proposed integration point; Person 2 must confirm exact names and payloads.

## Person 1 acceptance criteria

- Product lookup and support-ticket paths use mocked tools without network
  calls in graph tests.
- No action tool runs before approval.
- Approval authorizes only the exact displayed operation; rejection and
  malformed or mismatched approval write nothing.
- Duplicate resume cannot duplicate actions.
- Tool/model failure and step exhaustion terminate with explicit statuses.
- Every trajectory stays within the configured step bound and is JSON-safe.
- The graph can be wired to Person 2's implementation without changing tool
  behavior or bypassing its sandbox.

## Handoff

Provide the frozen state/trajectory schema, public API, terminal status list,
checkpoint behavior, stop-rule proof, and the event list Person 4 should map to
LangSmith runs, spans, and approval events.
