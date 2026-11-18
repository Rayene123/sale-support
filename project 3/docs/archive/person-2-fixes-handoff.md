# Person 2 fixes — explanation and handoff

The original modules, public tool names, graph adapter and sandbox-only behavior remain in place. These changes repair the reviewed failure cases rather than redesigning your work.

## What changed and why

| Problem | Fix | How to explain it |
| --- | --- | --- |
| A write commits, but its response is lost. The approval is consumed, so the retry cannot find it. | `resolve_action_approval` finds either an active approval or an exact matching stored receipt. The write RPC locks and validates the approval before replay. | Retrying the same approved operation returns its original result; it does not repeat the effect. |
| Approval JSON uses numbers while the writer sends decimal strings. SQL rejects the mismatch. | `agent/tools/payloads.py` gives approval persistence, lookup and execution the same validated representation. Order money uses two-decimal strings. | We approve exactly what we execute, including defaults and money formatting. |
| Unavailable stock text contains the word “available.” | Negative stock markers are checked first and cannot be overwritten by positive markers within the card. | “Unavailable” and “indisponible” no longer become “in stock.” |
| Redirects could leave the approved host; response limits ran after downloading. | Each HTTPS redirect is checked before following it; streaming stops at the byte limit and connections close on success or failure. | The fetcher enforces host, redirect and download bounds while fetching. |
| A clean database lacked support-write and reset functions. | New migration 004 versions those functions and adds receipt-aware resolution. | A fresh sandbox can be built from repository files. |
| Reset could partly clear data before its second RPC failed. | One database transaction restores fixtures and clears all effects. | Reset succeeds or rolls back as one operation. |
| Mocked RPC tests did not exercise SQL. | Added an isolated PGlite PostgreSQL integration suite. | We execute the actual migrations and check row counts, receipts and rollback. |

## Files to read

1. `agent/tools/payloads.py`: the shared payload representation.
2. `sandbox/approvals.py`: trusted-server approval persistence helper.
3. `agent/tools/dispatcher.py`: resolves approvals without creating them.
4. `agent/tools/writes.py`: keeps the existing writer interfaces and uses canonical commerce payloads.
5. `agent/tools/mytek.py`: retains its filename and legacy alias; the active scraper is Tunisianet.
6. `sandbox/migrations/004_replay_and_bootstrap.sql`: receipt replay, support writes and atomic reset.
7. `tests/test_person2_regressions.py` and `tests/sql/verify.mjs`: reproducible failure cases.

## Database setup

For a **fresh dedicated sandbox**, apply in order:

1. `sandbox/schema.sql`
2. `sandbox/seed.sql`
3. `sandbox/migrations/002_approved_commerce_writes.sql`
4. `sandbox/migrations/003_tunisianet_order_sources.sql`
5. `sandbox/migrations/004_replay_and_bootstrap.sql`

For an existing sandbox with 002 and 003, apply 004. Earlier migrations remain unchanged. The RPCs are for the trusted service-role server, not browser credentials. Deploy migration 004 before using the updated approval lookup.

Old unconsumed approval payloads may not use the new canonical representation. Do not silently rewrite approvals: obtain a fresh human decision and fresh operation IDs. Old receipts whose payload representation differs are not automatically converted; reconcile them before attempting another operation.

Only deliberately reset the dedicated sandbox with `python -m sandbox.reset --supabase`. Reset deletes sandbox-created orders, approvals, receipts and outbox entries and restores the supplied fixtures.

## Verification

From `project 3`, with its Python requirements installed:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
python -m pytest -q
```

The patch passed **77 Python tests**. Default tests block network connections.

For the SQL integration suite, with Node.js and npm installed:

```powershell
cd tests/sql
npm install
npm test
```

The patch passed **11 SQL integration checks** using PGlite 0.5.16. Each run creates an isolated in-memory database, applies the actual schema/migrations, and closes it afterward. Checks include lost-response replay, changed payload/run rejection, revoked and expired approvals, rollback on invalid totals, notification deduplication, ticket history deduplication, retained refund/escalation pending records, role rejection and repeated reset.

## Still needed for the full project

- Connect the authenticated human approval endpoint to `record_approval`, using the server-held proposal and the authenticated operator identity. The helper does not authenticate users and must not be exposed directly to model/browser assertions.
- Persist separate approvals for each action in the approved plan, with its exact operation ID and payload. Order, notification and ticket update are separate writes, not one transaction across the whole plan.
- Apply the migration to the real dedicated Supabase sandbox and verify the complete graph → approval → PostgREST → database path.
- Verify simultaneous retries with multiple real database connections. PGlite here tests sequential replay and transactional rollback; advisory locks are present, but this suite does not prove concurrent behavior.
- Retained refund/escalation tools are not wired into the current graph or approval helper. Their SQL tests seed trusted approval records directly.

No live Supabase data, retailer traffic, customer messages or paid model calls were used for this patch. Hosted authentication and current retailer markup were not verified. Changes are local on `codex/project3-person2-fixes`; they have not been pushed.
