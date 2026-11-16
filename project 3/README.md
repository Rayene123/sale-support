# Shopline Ops — AI Ecommerce Support Operator

CS496 AI Engineering — Fall 2026

Shopline Ops is a human-supervised ecommerce assistant for Tunisian IT product
support and order requests. LangGraph coordinates the workflow and its approval
gate. MYTEK product pages are a read-only catalog source. LangSmith is the
planned tracing and evaluation-monitoring platform.

## Target workflow

1. Receive a customer support ticket or a product/order request associated
   with a customer.
2. Read the relevant ticket, customer, and existing order context from the
   sandbox.
3. Search public MYTEK product listings and details for matching products.
4. Draft a structured support response or a proposed sandbox order, including
   selected products, observed prices, availability, total, and notification
   text.
5. Pause the LangGraph run and show the complete proposed action to an admin.
6. On explicit approval, create the sandbox order or approved support update
   and queue the corresponding notification. On rejection, perform no write.
7. Record a structured trajectory and send privacy-filtered traces to LangSmith
   when configured.

The system must never place a real MYTEK checkout, collect payment, or send a
real customer notification in this project. Orders and notifications are
sandbox records until the team explicitly defines a separate production
integration and its review process.

## Current implementation status

The repository contains the ticket approval prototype and a Person 1
product-order graph branch that uses an injected tool dispatcher. The MYTEK
scraper, sandbox order/notification tools, and LangSmith adapter are not
implemented yet, so the product-order branch cannot complete until Person 2
provides its tool adapter. The local review page still demonstrates the
ticket-only path. The role documents below define who owns those next steps.

## Safety boundaries

- MYTEK access is read-only, limited to public product pages, rate-limited, and
  subject to the site's published access rules.
- Product-page text, ticket text, and tool results are untrusted data. They
  cannot alter graph policy or authorize an action.
- The admin approves the exact item IDs, quantities, prices shown, order total,
  support mutation, and notification content before any sandbox write.
- Approval is bound to the run and operation IDs. Rejection, invalid approval,
  timeout, or step exhaustion must not write.
- Sandbox order creation does not submit a MYTEK cart or payment.
- Notifications go to a sandbox outbox; no SMTP, SMS, or third-party message
  is sent by this prototype.
- API keys and private customer data must not be committed or sent to tracing.

## Ownership

- **Person 1 — Agent loop and safety:** typed state, LangGraph routing,
  checkpoint/resume, approval validation, idempotent action orchestration,
  step limits, and trajectory events.
- **Person 2 — Product/data tools and sandbox:** MYTEK read-only scraper,
  ticket/customer/order reads, sandbox order writes, ticket mutations, and
  sandbox notification outbox.
- **Person 3 — Evaluation and threat model:** deterministic scenarios,
  injection cases, trajectory scoring, error taxonomy, and safety results.
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

## Local ticket prototype

From the project directory:

```powershell
python web_app.py
```

Open <http://127.0.0.1:8000>. This local page currently demonstrates the
ticket-only approval flow with mock data. Its checkpoint and write log live in
the Python process and are cleared when that process exits.

When an OpenAI API key is configured, the current prototype sends its mock
ticket context to the selected model to draft a response. The MYTEK workflow is
a separate planned integration owned by Person 2; do not use production
customer data with this prototype.

## Environment and monitoring

Person 2 owns the sandbox and its dedicated credentials. Person 4 owns optional
LangSmith configuration and privacy filtering. Expected LangSmith settings are
`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`; tracing must
not change workflow or approval behavior when disabled or unavailable.

The current Person 1 ticket workflow uses `MAX_STEPS=16` by default. Revisit
that bound after product-order and notification tool calls are connected.

The team must document the final setup, reset, demo, and evaluation commands
after the sandbox and LangSmith integrations are implemented. Do not infer that
planned commands are currently available.
