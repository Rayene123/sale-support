# Person 3 — Verifier, Compatibility and Evaluation

## Mission and ownership

Own the verification agent, deterministic requirement/compatibility checks,
and independent evaluation. Challenge proposals using source evidence, not
only the researcher's explanation. Person 1 owns what happens after findings;
Person 2 supplies retrieval tools and facts.

Target ownership: verifier/check modules, `eval/`, verification/evaluation and
injection tests, `errors.md`, and `threat_model.md`. Coordinate new module
locations with Person 1 before implementation.

## Steps

1. Agree structured requirements and evidence with Persons 1–2; obtain saved
   catalog snapshots and controlled failure fixtures.
2. Build deterministic checks for budget, quantities, required features and
   supported compatibility rules. Distinguish pass, fail and unknown; missing
   ports/specifications must not be interpreted as compatibility.
3. Build an independent verifier that reviews original evidence and returns
   specific issue codes, severity, affected requirements/products, evidence
   IDs and suggested next checks. It cannot approve, mutate an order, or
   silently change customer requirements. Blockers must be resolved before
   approval; unknown essential facts require clarification or a safe stop.
4. Build 30+ deterministic scenarios covering clarification, product search,
   complete setups, incompatibility, unknown facts, changing requirements,
   price/stock changes, approval outcomes, replay, partial writes, interrupted
   resume, tool failures and delegated step exhaustion. Retain support tests.
5. Add 5+ injection cases across ticket text, product descriptions and errors:
   policy override, data extraction, forged approval, altered products/prices,
   real checkout requests and unbounded retry instructions.
6. Compare fixed workflow, adaptive coordinator/researcher, and adaptive plus
   verifier on the same scenarios, model settings and budget. Report whether
   verification improves quality enough to justify its calls and latency.

## Scoring and independence

Measure hard-requirement satisfaction, evidence accuracy, compatibility false
positives, tool/argument correctness, wasted steps, task success, recovery,
duplicate prevention, approval violations and stop-rule compliance. Person 4
collects latency/token/cost data; identify estimates and missing values.

Use fixture expectations and actual sandbox receipts as ground truth. Do not
let the verifier grade its own output as the sole evaluator. Inspect complete
trajectories: a plausible final answer after a forbidden write is a failure.
Default evaluation never scrapes live MYTEK. Record failed cases and reproducible
IDs, not only aggregate scores.

## Handoff

Deliver verification contracts and rules, fixtures, one-command evaluation,
comparison results, error taxonomy, threat model and failure reproductions.
Person 1 consumes findings; Person 4 presents the measured results. Document
unsupported compatibility categories explicitly.
