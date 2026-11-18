# Person 2 Handoff

## A. Implemented

- A local/Supabase sandbox store, SQL schema, seed fixtures, reset helper, and fault fixtures.
- Read tools for tickets, customers, and orders. Customer reads omit email and other private account data.
- Validated support and commerce write tools, including ticket updates, order records, and queued sandbox notifications.
- A MYTEK Product JSON-LD parser and saved HTML fixture. Live search is deliberately disabled until its route and markup are verified.
- A dispatcher for `(tool_name, payload)` calls, including lookup of pre-existing trusted approvals.
- Approval-bound commerce SQL functions, operation idempotency, notification outbox, and sandbox reset extension.
- Tool/sandbox tests and contract documentation. `requirements.txt` already declares compatible LangGraph and LangChain OpenAI ranges.

## B. Using the tools

Create the dispatcher in trusted application code and inject its returned callable into the graph:

```python
from agent.tools.dispatcher import make_sandbox_approval_lookup, make_tool_executor
from sandbox.store import SandboxStore

store = SandboxStore.from_env()
executor = make_tool_executor(
    approval_lookup=make_sandbox_approval_lookup(store),
    store=store,
)
result = executor("get_ticket", {"ticket_id": "T-001"})
```

The same executor must be supplied on each graph invocation, including resume. Available tools and inputs:

| Tool | Input fields |
| --- | --- |
| `get_ticket` | `ticket_id` |
| `find_customer` | exactly one of `customer_id` or `email`; prefer `customer_id` |
| `get_order` | `order_id` |
| `search_mytek_products` | `query` |
| `update_ticket_database` | `ticket_id`, `operation_id`, `status`, `labels`, `response_text`, `approved_by` (run reference) |
| `create_customer_order` | `customer_id`, `items`, `total_tnd`, `source_evidence_ids`, `operation_id`, `approved_by` (run reference) |
| `send_support_notification` | exactly one of `ticket_id` or `customer_id`, `channel`, `message`, optional `subject`, `operation_id`, `approved_by` (run reference); no recipient address |

Successful reads return their `data` object directly. Ticket fields include `ticket_id`, `customer_id`, `order_id`, `untrusted_customer_message`, `labels`, and `status`. Customer fields include `customer_id`, `display_name`, `contact_channel`, `account_status`, and `relevant_notes`. Order fields include `order_id`, `customer_id`, `order_status`, `item_summary`, `total_amount`, `currency`, and shipment dates. Errors raise `ToolDispatchError` from the executor.

Keep `run_id` as the graph/checkpoint identity. The graph passes it as `approved_by`; this is only a run reference. Trusted application code must create approval rows after an authenticated human decision, and the dispatcher resolves the resulting `approval_id`. Never accept or manufacture `approval_id` from model input. Preserve operation IDs across retries: use the base ID for order creation, `:notification` for notification, and `:ticket` for ticket update. Persist separate approval rows bound to each action, operation ID, run ID, and exact canonical payload before executing writes.

## C. Unfinished

- Person 1 must route graph support reads through the injected dispatcher; the current ticket/customer/order support reads still use fixtures.
- Person 1 must remove email requirements and recipient values from model-facing state, drafts, and graph tool payloads. The graph currently expects customer email, while Person 2 intentionally does not return it.
- Verify that the deployed legacy `execute_support_write` binds ticket approvals to the correct operation and run. Its SQL definition is not in this repository.
- Migration `sandbox/migrations/002_approved_commerce_writes.sql` has not been applied or runtime-validated.
- Live MYTEK search is unverified and returns `scraper_unverified` without making a request.
- End-to-end writes against the dedicated sandbox have not been tested.

## D. Tests

Command run from `project 3`: `.venv\Scripts\python.exe -m pytest -q`

Result: **48 passed**, with **2 warnings** from LangGraph about node `config` parameter type annotations. No tests failed. Tests use offline fixtures and mocked RPC calls; they do not validate SQL against Postgres, contact MYTEK, or perform live writes.

## E. Safety

- Never expose customer email to the model or put it in graph/checkpoint state. Resolve it inside trusted database code when needed.
- Never bypass the trusted approval lookup or SQL approval/payload checks.
- Apply the migration only to the dedicated sandbox, after verifying the target; never apply it to production.
- Reuse operation IDs for retries so idempotency can return the existing result; changed payloads with the same ID must remain conflicts.
- Reset and live writes are explicit sandbox operations and were not performed as part of this handoff.

## F. Git

- Branch: `person2-sandbox-tools-continuation`
- Intended commit message: `Complete Person 2 sandbox tools and dispatcher`
- Intended push target: `origin/person2-sandbox-tools-continuation`
