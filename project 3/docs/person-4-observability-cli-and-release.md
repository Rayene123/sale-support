# Person 4 — Langfuse, CLI, Documentation, and Release

## Mission

Make the operator easy to run, inspect, measure, and submit from a clean
clone. Integrate Langfuse tracing without making it a runtime dependency,
provide a visible approval demo, calculate cost and latency metrics, and
assemble the final documentation and release check.

## Ownership

Primary files:

```text
agent/observability.py
agent/cli.py
requirements.txt
README.md
postmortem.md
report.pdf
tests/test_observability.py
docs/release-checklist.md
```

## Dependencies and order

### Must wait for

- Person 1's public `run_ticket` interface and stable trajectory events.
- Person 2's Supabase reset command and all four action-tool results.
- Person 3's evaluator output schema and baseline scenarios.

### Work order

1. Build the CLI against Person 1's public interface.
2. Add Langfuse spans for the frozen graph and tool events.
3. Add cost/latency collection to the evaluator.
4. Run the clean-clone and release checks.
5. Assemble the report and postmortem from measured results.

Person 4 must not redesign tool behavior, bypass approval, or add fallback
writes to make the demo appear successful. Any contract change goes back to
Persons 1 and 2 and requires evaluation updates from Person 3.

Coordinate edits to `README.md` with the whole team. Do not add credentials,
private customer data, or copied production traces.

## Langfuse integration

Create an optional tracing adapter. When Langfuse variables are absent, the
agent must continue locally and record enough structured data for offline
evaluation. When variables are present, create:

- one trace per operator run;
- one span per graph node;
- one generation observation per model call;
- one tool span per tool invocation;
- one event for approval requested, approved, rejected, or timed out;
- one final observation containing status, step count, latency, and cost.

Capture inputs and outputs in a privacy-safe form. Hash or redact customer
contact information and never send secrets or full sensitive records to the
observability service. Flush traces at the end of a run and handle tracing
failure explicitly without changing the operator's safety behavior.

## CLI and demo

Implement:

```powershell
python -m agent.cli --ticket T-001
python -m agent.cli --ticket T-001 --approve
python -m agent.cli --ticket T-001 --reject
python -m sandbox.reset
python -m eval.run --all
```

The interactive path must:

1. display the evidence summary;
2. display the exact proposed Supabase mutation, email message, refund request,
   and escalation task;
3. ask for explicit approval;
4. show the final applied or rejected status;
5. show the operation ID and trajectory summary.

The CLI must not interpret arbitrary user text as approval. Accept only an
explicit command or a normalized confirmation such as `yes`; everything else
must reject or ask again without writing.

## Cost and performance measurements

Record per scenario:

- total steps;
- tool calls;
- model calls;
- input and output tokens when available;
- estimated cost;
- wall-clock latency.

The evaluator should report p50 and p95 latency, average steps, recovery
rate, injection pass rate, and projected cost for 100 runs. If a local model
does not expose billing, label cost as an estimate and document the formula.
Do not silently invent provider prices.

## Documentation deliverables

Keep the main README complete for a clean-clone user:

- project purpose;
- safety boundaries;
- one setup command;
- one run command;
- reset command;
- evaluation command;
- environment variables;
- expected approval interaction;
- latest measured results;
- contributions and four-person ownership;
- explicit statement that the system uses sandbox data only.

Assemble `report.pdf` with:

1. task, tools, and write behavior;
2. graph, checkpoint, and stop-rule proof;
3. sandbox design;
4. trajectory evaluation;
5. errors and recovery;
6. threat model, injection results, and cost model.

Write `postmortem.md` around actual failures found during evaluation. Include
what failed, why it failed, the user or safety impact, the fix, and what
remains imperfect.

## Release checklist

Before freeze, verify:

- clean clone setup works on the supported Python version;
- no `.env`, Supabase keys, API keys, or production endpoints are tracked;
- Supabase URL/key point only to the dedicated sandbox project;
- sandbox reset works;
- normal approved demo works;
- rejection demo proves neither the database nor email outbox changes;
- duplicate operation is idempotent;
- approved demo shows one Supabase update and one sandbox outbox email;
- refund and escalation demos create exactly one pending record each;
- all tests pass offline;
- 30+ evaluation scenarios run;
- five or more injection cases are included;
- no run exceeds `MAX_STEPS`;
- Langfuse-disabled mode works;
- Langfuse-enabled traces contain the required spans;
- README commands match the repository layout;
- report and postmortem are present.

## Handoff to the team

Provide:

1. CLI demo instructions and a short screen-recording script.
2. Observability event names and privacy rules.
3. Cost/latency result tables.
4. Clean-clone test output.
5. Final release checklist signed by all four team members.
