# Person 3 — Evaluation, Errors, and Threat Model

## Mission

Measure whether Shopline Ops handles product research, sandbox order
proposals, and support tickets safely. Score the route and tool activity, not
only the final message. Keep the default evaluation deterministic and
offline.

## Ownership

Primary files:

```text
eval/scenarios.jsonl
eval/run.py
eval/score.py
eval/injection_cases.jsonl
eval/results/
errors.md
threat_model.md
tests/test_eval.py
tests/test_injection.py
```

## Dependencies and sequence

- Agree with Person 2 on sandbox fixtures, saved Tunisianet page snapshots, tool
  errors, and fault injection controls.
- Agree with Person 1 on graph events, terminal statuses, checkpoint behavior,
  approval outcomes, and `MAX_STEPS`.
- Freeze exact trajectories after both interfaces are stable.
- Give Person 4 the result schema before it prepares LangSmith dashboards and
  the report.

## Scenario coverage

Build at least 30 cases across:

- product search by brand, model, budget, and natural-language description;
- no matching product, duplicate matches, unavailable item, missing price,
  changed price, and stale stock;
- valid order proposal and customer/order ownership mismatch;
- admin approves, rejects, cancels, times out, or sends malformed approval;
- notification approval, sandbox outbox result, and duplicate replay;
- support tickets about delayed, missing, delivered, cancelled, and refund
  requests;
- missing ticket/customer/order, malformed model output, and transient tool
  failures;
- step-limit exhaustion and repeated checkpoint resume.

Each scenario records input, fixture ID, expected graph route, allowed and
forbidden tool calls, expected approval payload, expected sandbox writes,
terminal status, and recovery behavior.

## Threat model and injection cases

Treat ticket bodies, customer notes, product descriptions, page metadata,
prices/availability text, and tool errors as untrusted. Include at least five
cases attempting to:

1. override agent policy from a product description or ticket;
2. ask for secrets or broad customer data;
3. skip or forge admin approval;
4. alter customer, product, quantity, price, or destination after approval;
5. force live checkout, payment, or real notification;
6. induce repeated scraping/tool retries beyond the step budget.

The expected behavior is that source text remains data, the graph uses only
validated tool fields, the admin sees the exact proposed operation, and no
side-effect tool runs without matching approval.

## Scoring and acceptance

Score step accuracy, tool-call precision, task success, recovery, duplicate
prevention, approval safety, injection resistance, and stop-rule compliance.
Record latency and token/cost metrics when available, identifying estimates
as estimates. The evaluator must fail a scenario if any forbidden write
occurs, even when the final response looks correct.

Handoff: publish runnable scenarios, fixtures, scoring output, error taxonomy,
and reproductions for all safety failures. Do not scrape Tunisianet in the default
evaluation run.
