# The Specialist backend

The [enhanced team brief](monday-2026-11-16/README.md) defines the workflow. The [workbench](person-4-release.md) calls `specialist.workflow.coordinator.Specialist` with authenticated server identities.

| Call | Result |
| --- | --- |
| `start(customer_id, text)` | Creates a durable case and returns questions, findings or a verified proposal. |
| `revise(case_id, customer_id, text, expected_revision=...)` | Updates the requirements and supersedes the proposal. Fresh evidence that still matches can be reused. |
| `research(case_id, customer_id)` | Resumes a case with pending research. |
| `store.get(case_id, customer_id)` | Reads a case scoped to its owner. The workbench chooses which fields each role sees. |
| `decide(case_id, customer_id, reviewer_id=..., revision=..., proposal_hash=..., decision=...)` | Records a human decision for the exact review snapshot. |
| `execute_next(case_id, customer_id, expected_revision=..., expected_hash=...)` | Executes one approved action or looks up the receipt for a prior attempt. |

## Follow a request through the code

1. The [planner](../specialist/workflow/planner.py) proposes item lines, quantities, specs and relationships. [Planning checks](../specialist/workflow/planning.py) keep the plan grounded in the request and prior revisions.
2. The [researcher](../specialist/catalog/research.py) runs bounded searches and inspects exact listing pages. The [verifier](../specialist/verification/setup.py) checks requirements, budget, stock and relationships against published facts. Unknown essential evidence blocks approval.
3. The [proposal builder](../specialist/workflow/proposals.py) creates the exact order and notification preview. [Approval](../specialist/workflow/approval.py) binds the reviewer decision to its revision and hash.
4. [Execution](../specialist/workflow/execution.py) rechecks material listing facts and persists intent before asking the [sandbox writer](../specialist/sandbox/writer.py) for an effect. Changed facts require renewed approval. On retry, the service looks up the receipt for the exact action, run and approved payload.

The [hybrid planning guide](specialist-hybrid.md) describes model bounds and compatibility coverage. The deterministic laptop/display planner remains available as a benchmark and a model-free workbench option. Both routes use the same proposal and receipt handling.
