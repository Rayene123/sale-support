# Labeling Guide

## Task

Evaluate a customer-support reply generated from a customer message and the provided order context.

The response must use only the supplied order context. It must not invent delivery dates, tracking numbers, refund approvals, discounts, policies, product details, customer details, or anything else that is not explicitly present.

## Dataset Schema

Each line in `golden.jsonl`, `dev.jsonl`, and `test.jsonl` is one JSON object:

- `id`: stable item id.
- `split`: `dev` or `test`.
- `category`: scenario type.
- `difficulty`: easy, medium, or hard.
- `customer_message`: the message given to the support system.
- `order_context`: all order data available to the system.
- `reference_answer`: one valid answer.
- `expected_facts`: facts the answer should preserve.
- `unavailable_info`: facts the model must not invent.
- `notes`: extra evaluator guidance.

## Rubric

Score each response out of 8 points.

| Criterion | Score |
| --- | ---: |
| Factual correctness | 0-2 |
| Completeness | 0-2 |
| No hallucination | 0-2 |
| Relevance | 0-1 |
| Professional/polite tone | 0-1 |
| Total | 8 |

## Factual Correctness

- 2: All factual claims are correct according to the order context.
- 1: Minor factual issue that does not substantially change the answer.
- 0: Major incorrect information such as wrong status, wrong product, wrong quantity, or wrong price.

## Completeness

- 2: Answers all parts of the customer's request.
- 1: Answers most but misses one important part.
- 0: Fails to answer the main request.

## No Hallucination

- 2: Does not invent unsupported information.
- 1: Uses slightly unsupported wording with limited impact.
- 0: Invents important information such as a tracking number, delivery date, refund approval, discount, or policy.

## Relevance

- 1: Directly addresses the customer's request.
- 0: Includes irrelevant or distracting information.

## Professional Tone

- 1: Clear, polite, and professional.
- 0: Rude, confusing, dismissive, or inappropriate.

## Labeling Rules

Two evaluators should label independently. Do not show evaluator 2 evaluator 1's labels before both are submitted.

For unsupported requests, a good answer should say the information is unavailable in the provided context and avoid guessing.

For multi-part requests, missing one requested part should reduce completeness even if the answer is factually correct.

For ambiguous short requests such as "Update?", accept a concise summary of the known order status and key order details.

## Label Output Schema

Each line in `human_labels.jsonl` should contain:

- `item_id`
- `response_id`
- `response_text`
- `evaluator_id`
- `scores.factual_correctness`
- `scores.completeness`
- `scores.no_hallucination`
- `scores.relevance`
- `scores.professional_tone`
- `scores.total`
- `explanation`
