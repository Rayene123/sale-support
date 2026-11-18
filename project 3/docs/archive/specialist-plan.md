# The Specialist — Implementation and Demonstration Plan

Status: agreed team direction. The bounded purchasing core is implemented for supported laptop/display requests. See the [current backend handoff](specialist-core.md) for verified behavior and remaining integration.
This is not an additional specification from the professor.

## Work sequence

1. **Contracts — all four:** agree on requirements, evidence, proposals,
   verification findings, approval revisions and trajectory events. Persons
   1–2 settle tool schemas; Person 3 defines validation; Person 4 checks that
   the events support progress reporting. Mark contracts frozen only after
   review. Build against fixtures while interfaces are being implemented.
2. **Research foundation — Person 2:** product search/details, saved page
   fixtures, source tracking, sandbox reset and validated action tools.
   Person 1 can build coordinator/checkpoint logic against mocks in parallel.
3. **Adaptive case — Person 1:** clarification, bounded action selection,
   persistent case revisions, follow-up requests and structured proposals.
   Person 2 connects the researcher through agreed tools.
4. **Verification — Person 3:** deterministic requirements/compatibility
   checks and independent evidence review. Person 1 routes findings back to
   research, clarification or a safe stop. Bound the revision loop.
5. **Execution recovery — Persons 1–2:** exact proposal approval, fresh
   price/stock checks, renewed approval on changes, receipts and retries of
   unfinished actions only.
6. **Integration — Person 4:** connect customer/admin flows and optional
   LangSmith traces. Person 3 runs evaluation; Person 4 publishes actual
   results and clean-clone instructions.

## Demonstration

Use controlled fixtures for a reproducible demo:

- Request a programming laptop and monitor within a total budget.
- Clarify a missing essential requirement.
- Inspect candidates; detect an incompatible connection or missing evidence.
- Revise the selection and explain the trade-off with source references.
- Change a customer requirement and revise the existing case.
- Approve a proposal; inject a price/stock change before execution.
- Show the difference and obtain fresh approval.
- Fail notification after order creation; retry only the notification and
  show exactly one order and one outbox record.

Label fixtures, simulated failures and sandbox results visibly. Do not imply
that a sandbox order is a MYTEK reservation or that availability is guaranteed.

## Definition of done

- Complete the primary purchase workflow, including clarification and revision.
- No claim of compatibility without the required specification evidence.
- No writes without matching current approval; no duplicates on replay.
- Persistent case isolation and interrupted-run recovery are tested.
- 30+ offline scenarios and 5+ injection cases cover the primary workflow.
- Every path, including delegation and retry, respects a documented budget.
- Compare fixed, adaptive, and adaptive-plus-verifier configurations on the
  same inputs. Track quality, safety, tool use, latency and estimated cost.
- Setup, reset, demo and evaluation work from a clean clone; optional tracing
  failure does not alter the results. Publish failures as well as successes.

Keep general support secondary. Add features only after this end-to-end
workflow passes; more agents alone are not evidence of better performance.
