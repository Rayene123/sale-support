# Person 1 fixes — explanation and handoff

This patch preserves the existing function names, LangGraph routes, ticket
compatibility path, customer product selection and Person 2 dispatcher contract.
It does not replace the project with the larger proposed multi-agent design.

## What changed and why

1. Validate customer, request shape and sufficient budget before invoking the
   intent model. Model calls have a 30-second timeout, no automatic retries and
   a 512-token completion limit. No model calls were used to test this patch.
2. Check the selected basket total against price_max_tnd, not just each item's
   price. In this prototype that maximum is now also the complete-order budget.
   Over-budget selection fails clearly; start a new selection/search.
3. Before an order write, refresh catalog evidence using the existing search
   tool. Require the selected product, source URL, requested criteria, price and
   available stock to match. Otherwise stop with no order and require a new
   proposal/approval. This is conservative: a product absent from bounded search
   results blocks execution. It is not a stock reservation or atomic retailer
   checkout. A dedicated product-detail tool remains a future improvement.
4. Proposals expire after 15 minutes. Approval/resume and action execution
   check elapsed time. Expiry is enforced when resumed; there is no background
   scheduler to update an idle screen. Prior receipts are never erased.
5. Add one graph node, request_retry. After an order/ticket action succeeds but
   notification fails, preserve the receipt, pause, and explicitly retry only
   unfinished work using original IDs. Declining stops without rollback.
6. Reserve steps before effects. Default MAX_STEPS is now 20 to accommodate
   revalidation and bounded recovery. Existing environment overrides remain
   respected; update old MAX_STEPS=16 settings if recovery needs more room.
7. The customer demo now uses clearly labelled process-local simulated order
   and notification receipts, with replay/conflict checks. These disappear on
   restart and do not invoke Supabase. Real integration still requires Person
   2's dispatcher plus a trusted authenticated approval service. Do not treat
   the demo adapter or its run-reference check as production authorization.
8. Replace the stale scraper test with a mocked alias contract and block socket
   connections in default tests. The suite cannot accidentally call a model,
   live catalog or database.

## How to explain it

“The workflow is the same, but we validate before spending tokens, enforce the
whole order budget, refresh prices before writing, and keep receipts so a
failed notification can be retried without creating another order.”

## Verification

Run `python -m pytest -q` from project 3 with requirements installed. Regression
coverage includes invalid input before model calls, basket budgets, stale
prices, approval expiry, partial recovery, repeated failure exhaustion, demo
receipt conflicts and complete simulated orders. No live Supabase, production
identity or real retailer checkout was validated.

## Remaining boundaries

Checkpoints and demo receipts remain in-memory. Restart recovery, multi-user
authentication, adaptive research/verification agents, compatibility reasoning,
case revisions and LangSmith remain separate work. Existing product orders use
customer confirmation; an admin-only product approval policy requires a team
decision and integration. SQL may reject an expired trusted approval even when
the graph proposal has not expired; the stricter service decision wins.
