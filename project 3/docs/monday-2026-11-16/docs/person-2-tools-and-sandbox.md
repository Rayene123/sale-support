# Person 2 — Research Agent, Product Tools and Sandbox

## Mission and ownership

Own the researcher agent, MYTEK retrieval, normalized evidence and sandbox
actions. The researcher chooses useful catalog queries and candidate detail
lookups within the coordinator's delegated task and budget. It cannot approve
or execute writes. Person 1 owns routing/approval; Person 3 owns compatibility
and verification rules.

Target ownership: researcher module, product/read/write tools, `sandbox/`,
tool/parser/sandbox tests and saved page fixtures. The repository currently
has `agent/tools.py`; agree a migration before introducing `agent/tools/` so
the module and package do not conflict or break the ticket prototype.

## Steps

1. Agree typed inputs/results and safe error codes with Persons 1 and 3.
2. Build bounded search and product-detail retrieval for public MYTEK pages.
   Respect published access rules, rate limits, timeouts and page limits.
   No access-control bypass, account login, checkout or payment.
3. Normalize product identity, source URL, retrieval time, price/currency,
   stock and relevant specifications. Missing values remain null/unknown.
   Attach field-level evidence where needed; separate source facts from
   researcher judgments. Use precise decimal or minor-unit money arithmetic.
4. Build the researcher to gather and compare candidates against requirements,
   explain trade-offs and return structured evidence. Broaden or refine
   searches when appropriate, without silently relaxing hard constraints.
5. Provide fresh price/stock reads before execution. Return explicit changes,
   unavailable evidence and typed failures; never silently replace products.
6. Implement resettable sandbox customers, tickets, orders, notification outbox
   and operation receipts. Tools validate ownership, allowed fields, quantities,
   totals and exact approval scope before any write.
7. Persist idempotency atomically with each effect. Identical replay returns
   its receipt; the same ID with different content conflicts. Include fixtures
   for failures before and after persistence.

## Tool contract and boundaries

Retain ticket/customer/order reads. Agree product search, product detail and
revalidation tools plus sandbox order, ticket-update and notification actions.
Current dispatcher names are integration proposals, not a complete adapter.
A caller-supplied `approved_by` string alone is not proof of authorization;
validate against trusted approval state coordinated with Person 1.

Notifications are sandbox outbox records, never SMTP/SMS or real messages.
Orders do not reserve MYTEK stock. Define a freshness policy and how expired
revalidation is handled; an external catalog cannot offer atomic stock
reservation through read-only scraping.

## Acceptance and handoff

Offline tests use saved HTML/product snapshots: missing specifications,
duplicate products, changed prices, unknown stock, blocked retrieval,
malicious page text, schema/ownership failures, reset, replay conflicts and
partial writes. Live retrieval is explicit opt-in, not part of default tests.

Deliver researcher/tool contracts, evidence examples, fixtures, reset command,
retry rules and idempotency guarantees. Persons 1 and 3 consume the same facts
without implementing their own scraper.
