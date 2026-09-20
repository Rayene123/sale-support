# Person 1 — Golden Dataset & Labeling

## Role

**Golden Dataset & Labeling Lead**

## Main Objective

Build the 150+ item golden evaluation dataset and define how human evaluators should judge customer-support replies.

The dataset is the foundation of the entire evaluation project. The other team members depend on the input format, rubric, and labeling guide defined here.

---

## Dependencies

You need:

- Existing Supabase e-commerce data
- `products`
- `categories`
- `orders`
- `order_items`
- The agreed customer-support task
- The evaluation rubric

You do **not** need to build the AI system or evaluation harness.

---

# 1. Define the Evaluation Task

The task is:

> Given a customer message and the relevant order information, generate an appropriate customer-support response.

The system may receive information such as:

- Order ID
- Order status
- Order items
- Product names
- Quantities
- Prices
- Order total
- Customer message

The system must only use information provided in the evaluation input.

It must not invent:

- Delivery dates
- Refund approvals
- Discounts
- Tracking numbers
- Policies
- Product information
- Other customer information

unless that information is explicitly provided.

---

# 2. Define Dataset Format

Every evaluation item should contain enough information for another person to evaluate the answer without accessing Supabase.

Example structure:

```text
{
  "id": "001",
  "customer_message": "...",
  "order_context": "...",
  "reference_answer": "...",
  "human_labels": {}
}
```

The exact JSON structure should be agreed with Person 2 before the dataset is finalized.

---

# 3. Create 150+ Evaluation Scenarios

Build at least **150 items**.

The dataset should contain different types of customer questions.

Suggested categories:

### Order Status

Examples:

- Where is my order?
- Has my order shipped?
- Is my order still processing?
- What is the status of order #1042?

### Order Contents

Examples:

- What did I order?
- What products are included?
- How many phones did I buy?

### Prices and Totals

Examples:

- How much did my order cost?
- What is the price of this item?
- What is the total?

### Multiple Questions

Example:

> Has my order shipped, what did I buy, and how much did it cost?

These are important because the system must answer every part.

### Unsupported / Tricky Questions

Examples:

- When exactly will my package arrive?
- Can I get a refund?
- What is my tracking number?
- Can you change my delivery address?

If the required information is not provided, the correct behavior is to say that the information is unavailable rather than hallucinating.

---

# 4. Create Difficult Cases

Do not make every item obvious.

Include:

- Multiple products
- Repeated products
- Large quantities
- Similar product names
- Multiple questions in one message
- Questions containing irrelevant information
- Questions asking for unavailable information
- Questions where the answer requires combining several fields
- Very short customer messages
- Ambiguous questions
- Long customer messages

The goal is to test whether the system actually uses the supplied order context correctly.

---

# 5. Create the Labeling Guide

Create:

`data/labeling_guide.md`

The guide must explain exactly how a human should evaluate an AI response.

Use this rubric:

| Criterion                | Score |
| ------------------------ | ----: |
| Factual correctness      |   0–2 |
| Completeness             |   0–2 |
| No hallucination         |   0–2 |
| Relevance                |   0–1 |
| Professional/polite tone |   0–1 |
| **Total**                | **8** |

### Factual Correctness

**2:** All factual claims are correct.

**1:** Minor factual issue that does not substantially change the answer.

**0:** Major incorrect information.

### Completeness

**2:** Answers all parts of the customer's request.

**1:** Answers most but not all important parts.

**0:** Fails to answer the main request.

### No Hallucination

**2:** Does not invent unsupported information.

**1:** Slightly unsupported wording with limited impact.

**0:** Invents important information.

### Relevance

**1:** Directly addresses the customer's request.

**0:** Contains irrelevant or distracting information.

### Professional Tone

**1:** Clear, polite, professional.

**0:** Unprofessional, rude, confusing, or inappropriate.

---

# 6. Human Labeling

Every golden item must be evaluated by **two people independently**.

Do not let the second evaluator see the first evaluator's score before submitting their own.

Record:

- Individual criterion scores
- Total score
- Short explanation
- Any disagreement

---

# 7. Measure Human Agreement

Calculate agreement between the two human evaluators.

At minimum report:

- Number of items evaluated
- Number of agreements
- Number of disagreements
- Agreement percentage

If possible, also calculate an appropriate agreement statistic such as Cohen's kappa for categorical labels.

Document disagreements and identify common causes.

---

# 8. Dev/Test Split

Create:

```text
data/dev.jsonl
data/test.jsonl
```

The development set can be used while improving prompts.

The test set should remain protected from prompt tuning as much as possible.

Do not repeatedly modify the system specifically to improve individual test examples.

---

# 9. Deliverables

You are responsible for:

```text
data/golden.jsonl
data/dev.jsonl
data/test.jsonl
data/labeling_guide.md
data/human_labels.jsonl
```

Also provide:

- Human agreement results
- Dataset category breakdown
- Notes about difficult cases
- Dataset generation methodology

---

# 10. Handoffs

### To Person 2 — Harness

Provide:

- Exact dataset schema
- JSONL files
- Required input fields
- Expected output format
- Dataset split information

### To Person 3 — LLM Judge

Provide:

- Final labeling rubric
- Human-labeled examples
- Good and bad response examples
- Human agreement results

### To Person 4 — System

Provide:

- Exact input format
- Examples of customer questions
- Rules the system should follow
- Examples of correct responses

---

# Definition of Done

- [ ] Task definition finalized
- [ ] Dataset schema finalized
- [ ] At least 150 items created
- [ ] Multiple scenario categories represented
- [ ] Difficult/tricky cases included
- [ ] Labeling guide completed
- [ ] Every item labeled by two humans
- [ ] Human agreement calculated
- [ ] Dev/test split created
- [ ] Dataset committed to Git
- [ ] Handoffs completed
