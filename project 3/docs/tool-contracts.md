# Person 2 tool contracts (current implementation)

All tools return JSON-safe dictionaries. Errors have `{success:false,error,message,retryable}`. Validation failures are non-retryable (`invalid_input`); unknown records use `*_not_found`; transient sandbox failures use `sandbox_database_failed` and may be retried with the same operation ID. Support updates use `execute_support_write`; orders and notifications use `execute_approved_commerce_write`. Writes and must be run only against the configured sandbox.

## Reads

```json
{"tool":"get_ticket","input":{"ticket_id":"T-001"}}
{"success":true,"data":{"ticket_id":"T-001","customer_id":"C-001","order_id":"O-001","untrusted_customer_message":"...","labels":[],"status":"open","created_at":"..."}}
```

`find_customer` accepts exactly one of `customer_id` or `email` and returns support-relevant fields only (no email, credentials, or payment data). `get_order` accepts `order_id` and returns its status, item summary, amount, currency and shipment dates. Fixture IDs include customers `C-001`–`C-010`, orders `O-001`–`O-010`, and tickets `T-001`–`T-012`. `T-010` contains adversarial customer text; `T-011` has a missing customer reference; `T-012` has a missing order reference.

## Tunisianet search

```json
{"tool":"search_tunisianet_products","input":{"query":"climatiseur","criteria":{"price_min_tnd":"900.00","price_max_tnd":"1800.00","color":"white","weight_max_kg":"35.000","characteristics":{"capacity":"12000 BTU","inverter":"Yes"}}}}
```

Criteria may include `name`, `price_min_tnd`, `price_max_tnd`, `color`, `weight_min_kg`, `weight_max_kg`, and up to ten key/value `characteristics`. Results normalize `product_id`, `name`, `source_url`, `price_tnd`, `availability`, and `retrieved_at`; color, weight, and technical characteristics are included when published on the detail page. Descriptions are ignored as untrusted content. The scraper checks Tunisianet `robots.txt`, makes one search request, and fetches up to eight detail pages only when attribute filters are requested. Requests are HTTPS-only, bounded, rate-limited, and read-only; HTTP 403/429 ends the operation without retries or bypass attempts. The search endpoint is `https://www.tunisianet.com.tn/recherche`.

## Writes and approval context

The database is expected to validate a trusted `approval_id` row bound to the action, customer/ticket and run context, then consume it transactionally. Identical `(action_type, operation_id, payload)` retries return the original result; a changed payload with the same operation ID returns `operation_conflict`. A caller-provided string is not itself approval.

`update_ticket_database(ticket_id, operation_id, status, labels, response_text, approval_id)` writes allowlisted ticket fields. `create_refund_request(ticket_id, order_id, operation_id, amount, reason, approval_id)` creates a pending request only; it never transfers funds. `create_escalation_task(ticket_id, operation_id, team, priority, reason, due_at, approval_id)` creates a pending sandbox task.

`create_customer_order(customer_id, items, operation_id, approval_id, run_id, total_tnd, source_evidence_ids)` writes an internal sandbox order record only. Each graph-compatible `items` entry is `{ "product_id":"...", "name":"...", "source_url":"https://www.tunisianet.com.tn/...", "quantity":2, "unit_price_tnd":1.25 }`. The optional `line_total_tnd` is validated if supplied. Quantities are 1–10 and at most 20 lines are accepted; source links must be HTTPS Tunisianet or MYTEK URLs and evidence IDs must match the proposed products. The tool checks the proposed total; the SQL function independently recalculates and persists it. Order snapshots retain line totals calculated in SQL. No retailer checkout, payment, or cart interaction occurs.

`send_support_notification(operation_id, channel, message, approval_id, run_id, ticket_id=..., customer_id=..., subject=...)` queues a sandbox notification. Exactly one ticket/customer context ID is required; callers cannot supply a recipient address. The trusted approval RPC resolves the customer's current email internally and pins it on the approval row; execution checks the email has not changed and copies it into the restricted outbox. Neither lookup returns it to the model. `notification_outbox` only accepts `queued` status; no SMTP, SMS, chat provider, or customer contact is performed. Graph-generated notification IDs already have the `:notification` suffix; the tool preserves IDs and never appends another suffix.

Example result:

```json
{"success":true,"operation_id":"run-123","data":{"order_id":"S-...","total_tnd":"25.00","currency":"TND","sandbox_only":true}}
```

## Person 1 integration decision

`agent.tools.dispatcher.make_tool_executor` adapts Person 1's `(tool_name, payload)` contract. It takes an `approval_lookup` callback owned by trusted application code; `make_sandbox_approval_lookup(store)` provides a read-only lookup by exact action, operation ID, run ID and canonical payload through `resolve_action_approval` (including consumed approvals with matching receipts). For writes it reads `approved_by` only as a run reference, locates an already-created approval row, and passes the returned `approval_id` separately. The callback never creates approval. The trusted human approval application can call the service-role-only `record_commerce_approval` RPC after authenticating the human and canonicalizing the exact action payload. SQL then checks action, operation ID, run, expiry, status, and full payload. The graph's notification action already uses `operation_id + ":notification"`; the adapter passes that ID unchanged.

One human decision covers the graph's order plus its notification. The trusted approval service therefore persists distinct records for `create_customer_order` and `send_support_notification`, each bound to its action-specific operation ID and canonical payload. The same approval endpoint may persist an `update_ticket_database` record for the legacy `execute_support_write` function. It must create records only after the authenticated human decision and derive `approved_by` from that authenticated operator, never from graph input.

Person 1 graph changes needed before end-to-end integration:

1. In `inspect_order_customer`, validate the returned `customer_id`; remove the `customer.email` requirement. Keep only non-sensitive fields such as `customer_id` and `display_name` in state/model context.
2. In `_generate_order_proposal`/`draft_order`, remove `recipient` from the model-generated and approved notification payload. Include the exact `customer_id`, channel, and message. The SQL approval function resolves and pins the email privately after the human decision; the email must not be put in graph state or sent through `tool_executor`.
3. Change `inspect_ticket` to accept graph config and call `tool_executor("get_ticket", {"ticket_id": ...})`. Change `inspect_context` to use `tool_executor("find_customer", ...)` and `tool_executor("get_order", ...)`. The dispatcher returns the inner `data` objects. Adapt graph field use to Person 2's contracts: ticket `untrusted_customer_message`, customer `display_name`, and order `order_status`/`item_summary`/`total_amount`.
4. Preserve graph `run_id`; `approved_by` in write payloads is only this run reference. The injected resolver finds `approval_id` by `(action_type, operation_id, run_id)`; only the trusted approval service creates database rows. Never map `run_id` directly to `approval_id`.
5. Use base order ID for `create_customer_order`, `operation_id + ":notification"` for every notification, and `operation_id + ":ticket"` for the ticket update. Pass each ID unchanged. A single graph approval must result in separate database approval rows for each action, with the exact normalized action payload. Do not execute a second action if its approval row is absent.

Person 2's adapter never returns email from customer reads and drops any `recipient` field in the notification payload. It does not invent a recipient or change the target after approval.

## Sandbox and limitations

Apply `sandbox/schema.sql`, `sandbox/seed.sql`, then migrations `002`, `003`, and `004` in order to a fresh dedicated Supabase sandbox. Existing sandboxes on 003 need 004. Migration 004 supplies the missing support-write and atomic-reset definitions and the receipt-aware approval resolver. It does not deploy itself.

Trusted server code can use `sandbox.approvals.record_approval` after authenticating and authorizing the human decision. It shares `canonical_action_payload` with execution, including fixed two-decimal money strings. It supports the graph's order, notification and ticket-update actions. Retained refund/escalation writers are outside the current graph and approval helper; they require separately trusted approval records.

`python -m specialist.sandbox.reset --supabase` calls one transactional reset RPC, restoring fixtures and clearing all sandbox effects together. It still requires matching `SUPABASE_URL` and `SUPABASE_SANDBOX_URL`. The hosted sandbox was migrated and tested through the workbench. See the [release verification](person-4-release.md).

Default Python tests are offline. `tests/sql/verify.mjs` additionally executes the checked-in SQL against isolated PGlite PostgreSQL. This covers bootstrap, replay, rollback, approval rejection and reset, but does not prove hosted Supabase authentication, PostgREST integration or concurrent connections. Use the [release guide](person-4-release.md) for current setup and verification commands.
