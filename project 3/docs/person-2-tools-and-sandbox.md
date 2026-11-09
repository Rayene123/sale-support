# Person 2 — Tools and Sandbox

## Mission

Create deterministic, resettable Supabase sale-support data and the tools used by the
operator. Tools must have strict schemas, safe allowlists, typed JSON-safe
results, clear errors, and observable side effects. The database update and
email-send tools must be safe to replay and must never access production.

## Ownership

Primary files:

```text
agent/tools/schemas.py
agent/tools/reads.py
agent/tools/writes.py
sandbox/data/
sandbox/store.py
sandbox/reset.py
tests/test_tools.py
tests/test_sandbox.py
```

## Dependencies and order

### Must finish first

- Agree with Person 1 on graph state identifiers, action names, and approval
  fields.
- Agree with Person 3 on fixture IDs needed for the evaluation scenarios.

### First implementation owner

Person 2 is the first implementation owner. Build the Supabase schema,
seed/reset path, and tool contracts before Person 1 connects the graph to
real tools.

### Must finish before

- Person 1 wires the production graph nodes.
- Person 3 writes final expected trajectories.
- Person 4 runs the clean-clone demo.

## Sandbox design

Use a dedicated Supabase sandbox project and a sandbox email outbox, not a
production CRM, payment system, SMTP account, or real customer data. Seed at
least:

- 10 support tickets;
- 10 customers;
- 10 orders;
- refund and escalation tables;
- tickets with delivered, delayed, cancelled, and refund-request states;
- at least one missing customer and one missing order;
- at least one record containing prompt-injection text;
- one fixture for a transient read failure;
- one fixture for a write failure before and after persistence.

Implement:

```powershell
python -m sandbox.reset --supabase
```

Create `sandbox/schema.sql` and `sandbox/seed.sql`. The reset command must
restore the exact initial fixture state and clear operation history in the
dedicated Supabase project. Tests should use an isolated schema or reset
before each scenario that depends on initial state.

Required tables are `clients`, `orders`, `tickets`, `refund_requests`,
`escalation_tasks`, `email_outbox`, and `idempotency_keys`. Store
`SUPABASE_URL` and `SUPABASE_KEY` only in the ignored `.env`.

## Tool contracts

Implement these tools and no broader write capability:

### `get_ticket`

Input: `ticket_id: str`.

Returns the ticket ID, customer ID, order ID, body, labels, status, and
created timestamp. Ticket body is untrusted data and must be clearly separated
from trusted metadata.

### `find_customer`

Input: exactly one normalized customer ID or email, with a bounded length.

Returns only the fields needed for support: customer ID, display name,
contact channel, account status, and relevant notes. Do not expose secrets,
payment credentials, or unnecessary personal data.

### `get_order`

Input: `order_id: str`.

Returns order status, item summary, amounts, shipment status, and timestamps.
Return a typed not-found error when the order is absent.

### `update_ticket_database`

Input:

- `ticket_id`;
- `operation_id`;
- `status` from an enum;
- `labels` from an allowlist;
- `response_text` with a bounded length;
- `approved_by` or an equivalent approval reference.

The tool performs a transactional mutation against the Supabase sandbox
database. It
may update only the ticket status, labels, and response history. It must
reject arbitrary field names, URLs, shell commands, customer IDs, and
destination changes. The transaction must either commit all fields or change
nothing.

### `send_support_email`

Input:

- `ticket_id`;
- `operation_id`;
- `to` from the customer email stored in the sandbox database;
- bounded `subject`;
- bounded `body`;
- `approved_by` or an equivalent approval reference.

The tool writes a message to the sandbox `email_outbox` table. It must not
open an SMTP connection. The recipient must match the ticket's customer
record, and the tool must reject model-supplied alternate recipients or
headers. This is a genuine side effect in the test system: the outbox can be
inspected by the evaluator and reset between runs.

### `create_refund_request`

Input: `ticket_id`, `order_id`, `operation_id`, `amount`, `reason`, and
approval reference.

Create one pending refund request in Supabase. Verify that the amount does not
exceed the order total, the order belongs to the ticket client, and the
operation is approved. This action requests a refund; it does not transfer
money.

### `create_escalation_task`

Input: `ticket_id`, `operation_id`, `team`, `priority`, `reason`, due date, and
approval reference.

Create one pending human follow-up task in Supabase. `team` and `priority`
must come from enums, and the task must reference the existing ticket.

## Idempotency requirement

Persist an operation record keyed by `operation_id` for each action type. The
first accepted call for each action commits one Supabase mutation or outbox
row. A repeated identical call returns the recorded result without changing
data or adding another email, refund, or escalation. A repeated operation ID
with different content must return a conflict error and must not apply the
action.

Test:

1. apply one approved operation for each action;
2. repeat each operation twice;
3. verify one database mutation, one outbox row, one refund request, and one
   escalation task;
4. submit each ID with different content;
5. verify conflicts and unchanged Supabase state.

## Error behavior

Errors must be short, typed, and actionable. Examples:

- `ticket_not_found: use a known sandbox ticket ID`;
- `customer_not_found: verify customer_id or email`;
- `invalid_update_field: field is not allowlisted`;
- `invalid_email_recipient: recipient does not match the ticket customer`;
- `refund_amount_exceeds_order: amount must not exceed order total`;
- `invalid_escalation_team: team is not allowlisted`;
- `operation_conflict: operation_id was already used with different content`;
- `sandbox_database_failed: retry with the same operation_id`;
- `sandbox_email_failed: retry with the same operation_id`.

Never return stack traces to the model. Log the detailed exception locally
while returning a safe error object.

## Tests and acceptance criteria

Add tests for:

- valid and invalid schemas;
- unknown ticket, customer, and order;
- bounded text and label validation;
- injection text returned as data only;
- write allowlist enforcement;
- Supabase mutation failure and compensating/rollback behavior;
- email recipient and outbox validation;
- refund ownership and amount validation;
- escalation enum and ticket-reference validation;
- idempotent replay;
- operation conflict;
- reset restoring the original state;
- simulated read and write failures;
- every tool producing an input/output/timing record.

The tools owner is finished when Person 1 can run the graph without modifying
tool code and when all sandbox tests pass offline.

## Handoff to the team

Provide:

1. A tool contract document with example inputs and outputs.
2. Seed-data identifiers and scenario fixture descriptions.
3. Reset instructions.
4. Error codes and retryability rules.
5. Confirmation that no production endpoint or credential is referenced.
