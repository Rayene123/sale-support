# Person 1 — Agent Loop and Safety

## Mission

Build the LangGraph control loop that turns a support-ticket request into a
safe, inspectable trajectory. The graph must plan, gather evidence, draft
proposed database, email, refund, and escalation actions, pause for a human
decision, and execute actions only after approval.
The graph is the safety boundary: model output must never be able to skip the
checkpoint, change the write policy, or extend the run indefinitely.

## Ownership

Primary files:

```text
agent/state.py
agent/graph.py
agent/checkpoint.py
agent/limits.py
tests/test_graph.py
tests/test_checkpoint.py
```

You may add small helpers under `agent/`, but coordinate any new public state
field or trajectory event with Persons 2–4 before merging.

## Dependencies and order

### Must wait for

- Person 2's Supabase table and tool contracts before wiring tool calls.
- The agreed trajectory event schema before finalizing graph state.

### Can work in parallel

- Define typed graph state and stop-rule tests while Person 2 builds the
  sandbox.
- Write checkpoint tests using mocked tools.

### Must finish before

- Person 3 can freeze expected trajectories.
- Person 4 can map Langfuse spans and CLI output to stable events.

## Required implementation

### 1. Define the state

Create a typed, serializable state containing at least:

- `run_id`
- `ticket_id`
- `step_count`
- `status`
- `ticket`
- `customer`
- `order`
- `draft`
- `approval`
- `operation_id`
- `tool_calls`
- `errors`
- `trajectory`

Use explicit status values such as `running`, `awaiting_approval`, `approved`,
`rejected`, `completed`, `failed`, and `step_limit_reached`. Do not represent a
failed or rejected run as successful with an empty result.

### 2. Implement graph nodes

The initial graph should contain these bounded nodes:

1. `start_run`: validate the ticket identifier and initialize the run.
2. `inspect_ticket`: call `get_ticket`.
3. `inspect_context`: call `find_customer` and `get_order` only when their
   identifiers are available.
4. `draft_action`: produce a structured response and an allowlisted mutation.
5. `request_approval`: expose the exact database mutation and email message,
   then pause.
6. `apply_approved_actions`: call only the approved subset of
   `update_ticket_database`, `send_support_email`, `create_refund_request`, and
   `create_escalation_task`.
7. `finish_run`: create the final serializable result.

Each node must emit a trajectory event with the node name, input summary,
output summary, start/end timestamps, and resulting status. Never store hidden
chain-of-thought; record concise decisions and structured fields only.

### 3. Implement the human checkpoint

The approval request must show:

- ticket ID;
- proposed status;
- proposed labels;
- exact response text;
- database operation ID and email operation ID;
- sandbox email recipient and subject;
- refund amount and reason, when applicable;
- escalation team, priority, and reason, when applicable;
- evidence IDs used to create the proposal.

Only the values returned by the approval mechanism may authorize a write.
Free-form text such as “ignore the approval requirement” is not approval.
Rejection, cancellation, and timeout must terminate without invoking the write
tool.

### 4. Enforce the stop rule

Set `MAX_STEPS` from configuration, defaulting to `8`. Increment the counter
for every graph node and tool attempt. Before entering another node, terminate
with `step_limit_reached` when the bound is reached. The limit must apply even
when the model asks to retry, produces malformed output, or receives malicious
tool text.

Document the proof as an invariant:

> Every transition consumes one step, every transition checks the counter, and
> no terminal state has an outgoing transition. Therefore a run has at most
> `MAX_STEPS` transitions.

## Public interface

Expose one stable entry point:

```python
run_ticket(
    ticket_id: str,
    approval: ApprovalDecision | None = None,
    *,
    run_id: str | None = None,
) -> OperatorResult
```

The first call may return `awaiting_approval`. A resumed call receives the
checkpoint token or run identifier plus the explicit decision. The result must
be JSON serializable and include final status, trajectory, tool calls, errors,
and the proposed/applied mutation.

## Tests and acceptance criteria

Add deterministic tests for:

- normal read → draft → approval → database update → email/refund/escalation
  actions → finish;
- rejection never calls either action tool;
- cancellation and timeout never write;
- invalid ticket ID becomes a clear terminal error;
- malformed draft is rejected rather than silently defaulted;
- one transient tool failure follows the defined recovery path;
- repeated resume does not create an extra database update or email;
- malicious ticket text cannot alter the graph or tool policy;
- every trajectory has `step_count <= MAX_STEPS`;
- a forced loop reaches `step_limit_reached`.

The graph owner is finished when all tests pass without network access and
Person 2 confirms the graph uses only the agreed tool contracts.

## Handoff to the team

Provide:

1. A short state/event schema in `docs/trajectory-schema.md`.
2. The public `run_ticket` interface and example result.
3. A list of terminal statuses and their meanings.
4. Tests proving the checkpoint and stop rule.
5. A note to Person 4 describing which events should become Langfuse spans.
