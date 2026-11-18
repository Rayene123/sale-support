# Person 1 — Coordinator, Case Memory and Safety

## Mission and ownership

Own the coordinator agent and LangGraph orchestration. Turn customer needs
into bounded research, verification and approved execution. Person 2 owns the
researcher/tools; Person 3 owns verifier logic; Person 4 owns presentation and
tracing. The coordinator decides how to respond to verification findings.

Primary ownership: `agent/graph.py`, `agent/state.py`, `agent/checkpoint.py`,
`agent/limits.py`, graph/checkpoint tests, and `docs/trajectory-schema.md`.
These existing modules must evolve; this plan does not claim the new behavior
is already implemented.

## Steps

1. Agree contracts with Persons 2–3: requirements, evidence, tool outputs,
   verification findings, proposal revisions, approval and events.
2. Maintain case memory: hard constraints, preferences, candidates, rejected
   options and reasons, evidence, proposal revisions and action receipts.
   Separate case identity from individual run identity. Define persistence,
   resume, reset and customer isolation; do not store credentials or hidden
   reasoning.
3. Implement bounded next-action selection: clarify, research, inspect,
   compare, verify, revise, request approval, execute or finish. Validate model
   decisions against allowed actions. Do not run every tool automatically.
4. Delegate through stable researcher/verifier interfaces. Route specific
   findings to a revised search, a customer question, or a clear stop. Unknown
   facts are not positive verification. Bound delegation and revision rounds.
5. Version proposals. Changes to requirements or material product facts
   invalidate affected findings and approval. Preserve unaffected evidence.
6. Pause for exact admin approval. Coordinate Person 2's revalidation before
   writes; changed price/availability requires revision and fresh approval.
7. Preserve successful receipts after partial failure and retry only unfinished
   actions using the same operation IDs and validated approval scope.

## Safety and public interface

Keep `run_ticket(...)` compatible with the existing ticket demo while agreeing
an operator API with Person 4. Proposed richer request/resume APIs must not be
presented as implemented. Resume identifies the existing case, run and proposal
revision; customer text is never interpreted as admin approval.

The current step default is 16. Define a shared budget with Person 3 that
includes graph work, delegated model/tool attempts and retries. Child agents
must not reset it. Agree a separate bounded revision-round policy if needed.
Every attempt checks the budget before starting; terminal runs cannot execute
more actions. Approval waiting has explicit timeout/cancellation semantics.

## Acceptance and handoff

Test clarification, adaptive search after failure, changed requirements,
verifier objections, interrupted resume, customer isolation, invalid/stale
approval, rejection, timeout, duplicate resume and partial recovery. Prove all
paths remain bounded, including malicious tool text and delegated loops.

Deliver the public API, state/event contracts, transition rules, approval
invariants and deterministic tests. Person 4 must be able to integrate without
recreating orchestration logic.
