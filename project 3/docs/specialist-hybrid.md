# Specialist hybrid workflow

The November 16 [enhanced team brief](monday-2026-11-16/README.md) and
[work sequence](monday-2026-11-16/docs/specialist-plan.md) are preserved
as supplied. Their status labels describe the design when it was written.
Use this page to track implementation against that brief.

| Monday commitment | Current implementation and evidence |
| --- | --- |
| Interpret requirements and ask questions | The optional OpenAI planner produces typed item lines, quantities, ownership, exact-model references, hard specs, search alternatives and compatibility links. Missing information or detected omissions pause the case. |
| Adapt research and explain a result from evidence | The coordinator searches per item, inspects exact listings and tries a bounded alternate query when the first setup cannot be verified. Each finding carries sources. Results give reasons from verified fields. |
| Independently verify complete setups | The verifier handles direct display, USB and Ethernet links. It checks shared port use, units, prices and evidence freshness. Unknown connection types, ambiguous dock passthrough and unverified concurrent display modes block proposals. |
| Revise cases without losing useful work | Cases retain typed plans and saved evidence. The new revision checks the model's changes, preserves unaffected evidence, and supersedes the exact proposal. |
| Require fresh approval and recover safely | Both workflows share the durable case, exact-revision approval, listing recheck, sandbox writes and receipt recovery. Hybrid order totals include quantities and exclude owned items. |
| Compare configurations and verify failures | The original 30-fixture comparison still covers fixed, adaptive and independent-verifier configurations of the rules engine. Hybrid tests use a provider stub and exact product fixtures to cover multi-item requests, alternate research, unknowns, revisions and replay. A broader live-provider comparison still requires an available key. |
| Customer/admin integration, LangSmith and release | Phase 4 consumes the backend. The new website concept still uses simulated data. Hosted Supabase authorization/writes and tracing remain integration work. |

## Run the hybrid planner

From Project 3, use the existing OpenAI dependency. Set `OPENAI_API_KEY`
in the environment of the trusted server and optionally set
`SPECIALIST_OPENAI_MODEL`. The key is read server-side. The provider receives
the current purchasing prompt and the previous requirements, without customer
identity, tool credentials, raw retailer pages or access to write tools.

```python
from agent.specialist.coordinator import Specialist
from agent.specialist.planner import OpenAIPlanner
from agent.specialist.store import CaseStore

service = Specialist(CaseStore(".specialist/cases.sqlite3"),
                     planner=OpenAIPlanner.from_env())
case = service.start("C-001", "Find a desktop, two keyboards, and a mouse under 1,500 TND.")
```

One model call is allowed per case revision, with the existing shared step
budget and revision limit. Research limits are two queries per line, at most
two details per query and at most 18 combinations. The schema has up to 10
distinct lines and up to 10 units per line. The full candidate cross-product
is not enumerated. Supported connection facts determine what gets verified.
The planner may describe other kinds, but an unknown or unsupported relationship
cannot be counted as compatible.

The existing rule-based service remains available by omitting the planner.
A failed model call in a hybrid case reports `planner_unavailable` so a
multi-item request cannot silently shrink into a two-item case. An optional,
one-request model smoke test uses synthetic input:

```powershell
python -m eval.hybrid_smoke --ask-key
```

An OpenAI rate-limit response blocked the live smoke test. No successful
model result, quota balance or provider outage classification was established.
Offline tests inject a structured-output provider stub.
