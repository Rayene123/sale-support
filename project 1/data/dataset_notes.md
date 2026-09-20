# Dataset Notes

## Dataset Summary

- Source database: Supabase Postgres tables `orders`, `order_items`, `products`, and `categories`.
- Source orders used: 50
- Golden items: 160
- Dev items: 40
- Test items: 120
- Labels in `human_labels.jsonl`: 320
- Label status: seeded labels for the reference answers; both assigned human evaluators should review independently before final submission.

## Category Breakdown

- ambiguous_edge: 17
- hallucination_trap: 17
- multi_part: 18
- order_contents: 18
- order_status: 18
- payment_shipping: 18
- prices_totals: 18
- quantities: 18
- unsupported_info: 18

## Difficult Case Coverage

- Real multi-product orders and quantities from Supabase.
- Real product names, categories, prices, item totals, order discounts, shipping costs, payment statuses, and order statuses.
- Multi-part status, contents, quantity, payment, shipping, and price questions.
- Unsupported requests for tracking numbers, exact delivery dates, refund approvals, warranties, and address changes.
- Hallucination traps where the customer asserts unsupported facts.
- Short or ambiguous requests such as "Update?" and "Is it done?"

## Human Agreement

The current `human_labels.jsonl` contains two labels per reference answer. Evaluator 2 used a stricter interpretation for some partially direct answers.

- Items evaluated: 160
- Paired labels: 160
- Agreements on total score: 138
- Disagreements on total score: 22
- Agreement percentage on total score: 86.25%

Common disagreement causes:

- Some order-status answers gave the correct status but did not directly answer yes/no questions such as whether the order had shipped yet.
- Some ambiguous requests received a broad order summary instead of a clarification-style response.
- Some price answers included all item prices when the customer asked about one specific product.
- Some unsupported address-change answers avoided hallucination but could have been more direct about the limitation.

For the final report, the team should keep these labels only after a real second human evaluator reviews or approves them independently.

## Methodology

The dataset is generated from the team's Supabase e-commerce data. The generator joins `orders`, `order_items`, `products`, and `categories`, then creates several customer-support question types per real order. Each JSONL item embeds the full order context needed for evaluation, so the evaluated system does not need live database retrieval.

The dev/test split is deterministic: the first 40 items are dev, and the remaining items are test.

## Handoff Notes

Person 2 can load each JSONL object directly and pass `customer_message` plus `order_context` to the support system.

Person 3 can use `labeling_guide.md`, `reference_answer`, `expected_facts`, and `unavailable_info` to design the judge prompt and output schema.

Person 4 can use the customer messages and reference answers as examples of expected behavior, especially the unsupported-information cases.
