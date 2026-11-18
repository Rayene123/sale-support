# Specialist hybrid workflow

The November 16 [enhanced team brief](monday-2026-11-16/README.md) and
[work sequence](monday-2026-11-16/docs/specialist-plan.md) are preserved
as supplied. Their status labels describe the design when it was written.
Use this page to track implementation against that brief.

| Monday commitment | Current implementation and evidence |
| --- | --- |
| Interpret requirements and ask questions | The local Ollama planner proposes item lines, quantities, ownership, exact models, hard specs, search alternatives and the relationships the setup needs. Missing information or detected omissions pause the case. |
| Adapt research and explain a result from evidence | The coordinator searches per item, inspects exact listings and tries a bounded alternate query when the first setup cannot be verified. Each finding carries sources. Results give reasons from verified fields. |
| Independently verify complete setups | The verifier tests model-selected field comparisons against both products' published specifications. It also checks direct display, USB and Ethernet modes, shared port use, stock, prices and evidence freshness. A generic relationship needs an explicit declaration naming the other model to establish overall compatibility. Missing or conflicting evidence blocks proposals. |
| Revise cases without losing useful work | Cases retain typed plans and saved evidence. The new revision checks the model's changes, preserves unaffected evidence, and supersedes the exact proposal. |
| Require fresh approval and recover safely | Both workflows share the durable case, exact-revision approval, listing recheck, sandbox writes and receipt recovery. Hybrid order totals include quantities and exclude owned items. |
| Compare configurations and verify failures | The original 30-fixture comparison covers fixed, adaptive and independent-verifier configurations of the rules engine. The separate local-model benchmark tests several product families and reports results and measurements against fixture ground truth. |
| Customer/admin integration, LangSmith and release | The Phase 4 workbench provides separate customer and reviewer sessions, approval and recovery controls, local traces and optional LangSmith export. See the [release guide](person-4-release.md) for the verification status. |

## Run the hybrid planner

Start Ollama and make sure the model is installed. If needed, run
`ollama pull ministral-3:8b`. The server defaults to the local endpoint at
`127.0.0.1:11434`. Set `SPECIALIST_OLLAMA_MODEL` to use another installed
model. The planner receives the purchasing prompt and the prior requirements
for revisions. No API key is required.

```python
from specialist.workflow.coordinator import Specialist
from specialist.workflow.store import CaseStore

service = Specialist.with_local_model(CaseStore(".specialist/cases.sqlite3"))
case = service.start("C-001", "Find a desktop, two keyboards, and a mouse under 1,500 TND.")
```

One model call is allowed per case revision, with the existing shared step
budget and revision limit. Research limits are two queries per line, at most
two details per query and at most 18 combinations. The schema has up to 10
distinct lines and up to 10 units per line. The planner chooses what needs to
match across the products. For example, it can ask whether a case's maximum GPU
length is at least as large as the card's length. The verifier obtains both
values from the actual product listings and compares them in common units. A
result for one comparison covers that comparison only. An unresolved
relationship keeps the case from reaching approval.

The existing rule-based service remains available by omitting the planner.
A failed model call in a hybrid case reports `planner_unavailable` so a
multi-item request cannot silently shrink into a two-item case. Each of these
smoke tests sends one synthetic request to Ollama without fetching product pages:

```powershell
python -m evaluation.planner_smoke
python -m evaluation.planner_smoke --checks
```

The first checks multiple products and quantities. The second checks whether
the model identifies GPU clearance on its own. Offline tests separately
verify case outcomes, including what happens when the evidence is missing.
