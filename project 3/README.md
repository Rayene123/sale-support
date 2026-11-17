# Shopline Ops — AI Ecommerce Support Operator

CS496 AI Engineering — Fall 2026

The Specialist is a human-supervised IT purchasing assistant. It researches
product listings, verifies compatibility and prepares a sandbox order for
review. The original LangGraph support-ticket workflow remains available
separately.

## Run the Phase 4 workbench

From Project 3 with Python 3.12, Node.js, and Ollama installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location tests/sql
npm ci
Pop-Location
ollama pull ministral-3:8b
.\.venv\Scripts\python.exe specialist_web.py
```

Open [Customer](http://127.0.0.1:8767/customer/) to enter a free-form request
and [Reviewer](http://127.0.0.1:8767/admin/) to approve and execute sandbox
actions. The server prints separate passcodes. The default uses fictional
listings and the project's real sandbox SQL on a local database. Use
`--catalog live` for read-only Tunisianet research. See the
[release and testing guide](docs/person-4-release.md) for reset, data modes,
tracing and evaluation.

## The Specialist purchase workflow

The [November 16 enhanced brief](docs/monday-2026-11-16/README.md) defines
the target. The [implementation comparison and hybrid API](docs/specialist-hybrid.md)
describe what is currently working. The local Ollama model plans multi-item
requests and identifies what the products need to have in common. Independent
research, verification, and approval rules check the plan against listing evidence.
The server-side [Specialist core](docs/specialist-core.md) now handles laptop
and monitor cases, sourcing exact product facts, testing direct display
compatibility, and preserving revisions and sandbox receipts. It runs
alongside the original Shopline Ops graph. The Phase 4 workbench exposes the
case API through separate customer and reviewer views.

## Original Shopline Ops workflow

1. Receive a customer support ticket or a product/order request associated
   with a customer.
2. Read the relevant ticket, customer, and existing order context from the
   sandbox.
3. Search public Tunisianet product listings and details for matching products.
4. Draft a structured support response or a proposed sandbox order, including
   selected products, observed prices, availability, total, and notification
   text.
5. Pause the LangGraph run and show the complete proposed action to an admin.
6. On explicit approval, create the sandbox order or approved support update
   and queue the corresponding notification. On rejection, perform no write.
7. Record a structured trajectory and send privacy-filtered traces to LangSmith
   when configured.

The system must never place a real retailer checkout, collect payment, or send a
real customer notification in this project. Orders and notifications are
sandbox records until the team explicitly defines a separate production
integration and its review process.

## Current implementation status

The repository contains a support-ticket approval graph, a customer product
search/order graph with structured LLM prompt parsing, product parsing and criteria schemas, sandbox tool
adapters, and separate local customer and admin pages. Live Tunisianet search
is enabled for the demo with bounded, read-only requests that check robots.txt
and stop on access denial. With `SPECIALIST_LEGACY_LLM=true`, product prompts use
the local model for structured intent extraction. The customer sees when the
basic parser handles the request. Customer-selected products still require explicit
confirmation; order persistence also requires the configured trusted sandbox
approval service.

## Safety boundaries

- Tunisianet access is read-only, limited to public product pages, rate-limited, and
  subject to the site's published access rules.
- Product-page text, ticket text, and tool results are untrusted data. They
  cannot alter graph policy or authorize an action.
- The admin approves the exact item IDs, quantities, prices shown, order total,
  support mutation, and notification content before any sandbox write.
- Approval is bound to the run and operation IDs. Rejection, invalid approval,
  timeout, or step exhaustion must not write.
- Sandbox order creation does not submit a retailer cart or payment.
- Notifications go to a sandbox outbox; no SMTP, SMS, or third-party message
  is sent by this prototype.
- API keys and private customer data must not be committed or sent to tracing.

## Ownership

- **Person 1 — Agent loop and safety:** typed state, LangGraph routing,
  checkpoint/resume, approval validation, idempotent action orchestration,
  customer product selection, criteria filtering, step limits, and trajectory
  events.
- **Person 2 — Product/data tools and sandbox:** Tunisianet read-only scraper,
  ticket/customer/order reads, sandbox order writes, ticket mutations, and
  sandbox notification outbox.
- **Person 3 — Evaluation and threat model:** deterministic scenarios,
  injection cases, trajectory scoring, error taxonomy, and safety results.
- **Project integration — Customer and admin pages:** separate `/shop` customer
  ordering page and `/admin` ticket-review dashboard.
- **Person 4 — LangSmith observability and release:** traces/spans, optional
  monitoring configuration, runnable demo/release instructions, metrics, and
  final project report.

## Planned layout

```text
agent/       LangGraph state, graph, checkpoint, and limits
sandbox/     isolated order/ticket data and notification outbox
eval/        scenarios, injection fixtures, scoring, and results
tests/       offline tests for agent, tools, sandbox, and evaluation
docs/        role plans and frozen state/tool/trajectory contracts
```

## Local customer shop and admin dashboard

From the project directory:

```powershell
python web_app.py
```

Open <http://127.0.0.1:8000/shop> for the customer product search and order
view, or <http://127.0.0.1:8000/admin> for support-ticket review. The admin
dashboard handles tickets only. The customer form accepts name, TND price
bounds, color, weight, and technical key/value criteria. It uses seeded demo
customers; no real user authentication is implemented. Search currently
uses the approved Tunisianet public search page. Product results are fetched
from the live site; attribute filters are applied when the retailer publishes
those attributes. Graph checkpoints remain in process memory.

With `SPECIALIST_LEGACY_LLM=true`, the ticket path uses Ollama to draft a
response locally. Order proposals use the exact
customer-selected catalog items and prices; the graph never chooses a product
on the customer's behalf.

## Person 3 evaluation

The deterministic evaluator is offline by default. It injects a recorded
`(tool_name, payload)` executor into the real LangGraph and makes no
Tunisianet, database, or model calls. From the project directory:

```powershell
.\.venv\Scripts\python.exe -m eval.run --output eval/results/trajectories.jsonl
.\.venv\Scripts\python.exe -m pytest -q
```

The run writes `eval/results/trajectories.jsonl`, `summary.json`, and
`summary.md`. The combined branch passes 45 offline cases, including two scripted model responses. See `PERSON3_HANDOFF.md` for verification and scope.

## Environment and monitoring

Optional LangSmith tracing for the Phase 4 workbench uses
`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`.
The local trace and sandbox are available without a LangSmith account.

The current Person 1 workflows use `MAX_STEPS=20` by default. Revisit that
bound when a verified product source and trusted approval service are wired.

The [release and testing guide](docs/person-4-release.md) documents the setup,
reset, evaluation, and remaining live integration checks.

## Person 1 reliability patch

See [fixes and explanation](docs/person-1-fixes-handoff.md) for validation,
basket budgets, pre-write catalog refresh, 15-minute proposals, bounded partial
retries and the explicitly simulated local order demo. The graph default is
now `MAX_STEPS=20`; environment overrides remain in effect.
