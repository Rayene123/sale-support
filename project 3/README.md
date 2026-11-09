# Project 3 — The Operator

CS496 AI Engineering — Fall 2026

This project builds a safe, measurable sale/support ticket operator with
LangGraph and Langfuse. The operator reads a sandbox ticket, gathers the
relevant customer and order context, proposes a resolution, asks for human
approval, and then performs idempotent sandbox actions: updating Supabase,
sending an email through a fake email provider, creating a refund request, or
escalating the ticket.

## Scope

The first supported workflow is:

1. Read a support ticket.
2. Search the sandbox customer record.
3. Look up the related order.
4. Draft a response and a ticket action.
5. Pause at a human checkpoint showing every proposed side effect.
6. On approval, execute the approved actions exactly once:
   - update the Supabase support database;
   - send the approved customer email;
   - create a refund request when policy allows;
   - create an escalation task when human follow-up is required.

All side effects are limited to the Supabase sandbox project and local email
outbox. No production Supabase project, real SMTP server, real customer data,
or production credential belongs in this directory.

## Planned layout

```text
project 3/
  agent/       LangGraph state, nodes, tools, checkpoint, and stop rule
  sandbox/     Supabase schema, seed/reset commands, and fake email outbox
  eval/        30+ scenarios, trajectory scoring, and injection cases
  tests/       Unit and integration tests
  docs/        Team contracts, architecture, and experiment notes
  errors.md
  threat_model.md
  postmortem.md
  requirements.txt
  .env.example
```

## Local setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r "project 3/requirements.txt"
Copy-Item "project 3/.env.example" "project 3/.env"
```

Langfuse tracing is optional for offline tests and enabled only when the
required environment variables are present. Project 3 uses a dedicated
Supabase sandbox project. Never commit `.env`, Supabase keys, API keys, or real
customer data.

The run and evaluation commands will be added by the owners below after the
initial implementation:

```powershell
.\.venv\Scripts\python.exe -m agent.cli --ticket T-001
.\.venv\Scripts\python.exe -m eval.run --all
```

## Safety and measurement commitments

- **Read and action tools:** `get_ticket`, `find_customer`, `get_order`,
  `update_ticket_database`, `send_support_email`, `create_refund_request`,
  and `create_escalation_task`; every tool has a strict Pydantic input schema.
- **Human checkpoint:** the graph cannot call either action tool until the
  complete database mutation and email message are displayed and explicitly
  approved.
- **Sandbox:** clients, orders, tickets, refunds, and escalations live in a
  dedicated resettable Supabase sandbox; email is written to a sandbox
  outbox, never sent to the internet.
- **Idempotency:** each action carries an operation ID; replaying it returns
  the original result without applying the database mutation or adding a
  second email to the outbox.
- **Stop rule:** a run ends at approval, rejection, a terminal tool error, or
  `MAX_STEPS` (default 8). Tests must prove no trajectory exceeds this limit.
- **Observability:** every node and tool call records inputs, outputs, latency,
  token usage, and cost through Langfuse when configured.
- **Untrusted text:** ticket bodies, customer notes, and order responses are
  data only. They cannot alter the system prompt, tool policy, approval gate,
  or stop rule.

## Four-person work split

The names can be replaced with the actual team members. Each owner must add
tests for their surface and keep the interfaces below stable.

### Person 1 — Agent loop and safety owner

Owns `agent/graph.py`, `agent/state.py`, `agent/checkpoint.py`, and
`agent/limits.py`.

- Define the LangGraph state and transitions: plan → inspect → draft →
  approval → write → finish.
- Implement the `MAX_STEPS` stop rule and terminal-state handling.
- Implement pause/resume at the human checkpoint; rejection must never write.
- Add trajectory events with a stable event schema.
- Test normal flow, approval rejection, timeout, step-limit enforcement, and a
  failed tool followed by recovery.

**Integration contract:** expose `run_ticket(ticket_id, approval)` and return a
serializable trajectory containing states, tool calls, errors, and final status.

### Person 2 — Tools and sandbox owner

Owns `agent/tools/`, `sandbox/`, and `tests/test_tools.py`.

- Define strict Pydantic schemas and clear model-actionable errors.
- Implement `get_ticket`, `find_customer`, `get_order`,
  `update_ticket_database`, and `send_support_email`.
- Create resettable fixtures for at least 10 tickets, customers, and orders.
- Enforce sandbox-only IDs and allowlisted update fields.
- Connect only to the dedicated Supabase sandbox project using
  `SUPABASE_URL` and `SUPABASE_KEY`.
- Implement `update_ticket_database`, `send_support_email`,
  `create_refund_request`, and `create_escalation_task`.
- Make every action idempotent with an operation ID and add partial-failure
  fixtures.

**Integration contract:** tools must be callable without an LLM and return
typed JSON-safe results; all calls must be logged with input, output, and time.

### Person 3 — Evaluation, errors, and threat model owner

Owns `eval/`, `errors.md`, `threat_model.md`, and the scenario fixtures.

- Create at least 30 scenarios with expected next steps and expected tool
  arguments.
- Add trajectory scoring for step accuracy, tool-call precision, wasted steps,
  success, and recovery-after-failure.
- Add at least 5 tool-output injection cases, including attempts to bypass
  approval or change the destination of a write.
- Define the error taxonomy and one automated test per error class.
- Produce the stop-rule proof and the baseline evaluation report.

**Integration contract:** the evaluator consumes the trajectory schema from
Person 1 and deterministic sandbox controls from Person 2; it must not score
only the final answer.

### Person 4 — Langfuse, CLI, documentation, and release owner

Owns `agent/observability.py`, `agent/cli.py`, `requirements.txt`,
`README.md`, `postmortem.md`, and the final report assets.

- Add Langfuse traces/spans for each run, node, tool call, retry, and decision.
- Record token/cost estimates, p50/p95 latency, and cost at 100 runs.
- Build the CLI/demo flow that visibly pauses for approval.
- Keep setup, reset, run, and evaluation commands working from a clean clone.
- Assemble the report and postmortem from committed evaluation outputs.

**Integration contract:** tracing must be optional and must never change agent
behavior when disabled; the CLI uses only the public `run_ticket` interface.

## Collaboration order

The work must follow these dependencies:

### Phase 0 — Agreement: Persons 1 and 2, parallel

Before coding, agree on:

- Supabase table names and columns;
- tool input/output schemas;
- action names and operation-ID rules;
- LangGraph state fields;
- trajectory event format;
- approval decision format.

**Deliverable:** a frozen contract in `docs/trajectory-schema.md` and the
tool-contract section of Person 2's document.

### Phase 1 — Supabase foundation: Person 2 first

Person 2 creates the dedicated Supabase sandbox schema, seed data, reset
command, read tools, and action tools. Person 1 may create graph types in
parallel, but cannot connect graph nodes until the tool contracts are stable.

**Exit condition:** Supabase reset works and tool tests pass for clients,
orders, tickets, email outbox, refunds, escalations, and idempotency.

### Phase 2 — Safe graph: Person 1 after Phase 1

Person 1 wires the LangGraph loop to Person 2's tools:

```text
read ticket → read client/order → draft actions
→ human approval → update/email/refund/escalation → finish
```

**Exit condition:** approved actions execute once, rejected actions execute
nothing, and the step limit is proven.

### Phase 3 — Evaluation and threat model: Person 3 after Phases 1–2

Person 3 freezes the 30+ scenarios against the real tool and trajectory
contracts, then adds failure-recovery and injection cases.

**Exit condition:** trajectory scoring, error tests, injection tests, and
stop-rule tests run against the integrated graph and Supabase sandbox.

### Phase 4 — Observability and demo: Person 4 after Phases 1–3

Person 4 adds Langfuse spans, CLI approval interaction, cost/latency
measurement, and the clean-clone release check. Person 4 must not hide a
failed action behind tracing or CLI fallback behavior.

**Exit condition:** the demo shows the proposed actions, waits for approval,
executes the approved actions, and produces usable Langfuse/evaluation output.

### Phase 5 — Final review: all four people

Together verify the sandbox reset, rejection path, duplicate-operation path,
injection demo, stop rule, clean-clone setup, report, and postmortem.

Use small branches or pull requests per owner. Do not merge changes that add a
new tool, state field, or trajectory event without updating its contract and
tests.
