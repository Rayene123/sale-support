# Evaluation Dataset Labeling and Review Guide

## Scope and status

`questions.jsonl` is the single maintained dataset. It has 110 rows: 109 active questions marked `approved` and one historical row marked `excluded_duplicate` (`fr-cross-009`). The active set contains 89 answerable and 20 unanswerable-from-this-corpus items. All questions and available evidence are French; this French-only corpus cannot support Arabic-evidence retrieval evaluation.

The project owner reported that qualified legal experts reviewed and approved the current corrected active dataset. Reviewer names, credentials, and dates were not supplied and are not invented here. Structural checks and exact quote matches do not independently establish legal correctness. Excluded duplicates must not enter scoring.

The corpus is a bounded edition of the Tunisian Commercial Code. An unanswerable label means only that the documented corpus does not establish the requested answer; it is not a claim that the rule does not exist elsewhere or in current Tunisian law.

## Canonical record fields and categories

Each JSONL row uses `schema_version`, `question_id`, `question`, `language`, `category`, `answerability`, `answerability_reason`, `expected_answer`, `gold_evidence`, and `review`. Evidence points to stable article-level `record_id` values and exact excerpts from normalized corpus text.

- `single_article_factual`: one article suffices, even if several facts in that article are needed.
- `multi_article_cross_reference`: at least two distinct articles are necessary to answer the whole question.
- `unanswerable_from_corpus`: the scoped corpus cannot establish the answer.

For answerable questions, every required evidence item must support a necessary part of the reference answer. Do not use empty or repealed article text to establish a legal rule. For unanswerable questions, `expected_answer` is null and `gold_evidence` is empty; explain the corpus boundary in `answerability_reason` and/or the review issue.

## Labeling rules

1. Write an autonomous, natural, specific question. Do not copy distinctive article wording or reveal the answer in the prompt. Necessary legal terms may remain.
2. Answer the question directly and concisely. Preserve actors, triggers, conditions, exceptions, deadlines, and qualifications that affect meaning.
3. Cite every article needed for a complete answer. For multi-article questions, state which distinct answer component each article establishes. Do not add merely adjacent provisions.
4. Establish unanswerability by reviewing the documented corpus, not by observing retrieval failure or absence from one selected passage. State the precise scope limitation; do not generalize to Tunisian law.
5. Flag unclear wording, outdated or conflicting provisions, missing corpus dependencies, legal sensitivity, and language concerns.
6. Arabic-query evaluation requires Arabic evidence plus fluent Arabic review. French evidence cannot validate an Arabic legal answer.

## Review procedure and outcomes

A reviewer reads the question first, then checks all cited articles and searches relevant corpus context. Check clarity, whether evidence entails every answer clause, preservation of qualifications, necessity and completeness of each multi-article citation, corpus-level answerability, and language suitability for intended users. Unanswerable questions require a corpus-wide scope check rather than a retrieval-only check.

Use outcomes `approved`, `needs_revision`, and `rejected`. Only a qualified legal reviewer may approve legal correctness. A linguistic or structural review alone is not legal approval. Keep unresolved items out of official scoring. Automated parsing, record-ID checks, and substring matches are structural checks only.

A privacy-preserving review note contains only `question_id`, `outcome`, `issue_category`, brief `rationale`, generic `reviewer_role`, and ISO `review_date`. Do not collect names, contact details, case facts, or other personal/sensitive data. If reviewers disagree, preserve both decisions and rationales, mark the item `needs_revision`, and request qualified legal adjudication. Revisions preserve the canonical question ID and record prior/new decisions in the review audit trail. Changes to question, answer, category, answerability, or evidence require a new review of affected labels.

## Exclusions and audit trail

`fr-cross-009` remains in the canonical JSONL with status `excluded_duplicate` because it duplicates `fr-single-029` on the conflicting-amount rule in article 272. Preserve this ID and rationale for history, but exclude it from active candidate counts and all scoring. `fr-single-034` and `fr-cross-012` remain distinct: blank endorsement options versus the effect of a non-order clause.

## Limits of automatic validation

Structural validation can verify JSONL syntax, required fields/enums, unique IDs, corpus record existence/status, and exact quote occurrence. It cannot establish that a question is natural, that an answer is complete, that an article is legally necessary, that a quotation semantically supports a claim, or that a legal interpretation is correct. Human semantic and qualified legal review remain authoritative for those judgments.
