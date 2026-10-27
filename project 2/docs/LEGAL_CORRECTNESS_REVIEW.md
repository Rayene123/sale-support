# First-pass legal correctness review

## Scope and method

This is a corpus-relative screening of 16 cases from the full Qdrant-backed
GPT-6 Luna standard-tier run (`data/eval/generation_openai_gpt6_luna_qdrant_standard.json`).
It is not legal advice or qualified legal sign-off. The comparison uses the
question, generated answer and citations, approved expected answer, and cited
or gold articles in `data/processed/corpus.jsonl`. Cases were selected to
cover conditions, exceptions, cross-references, legal conclusions, and
clear low-citation or abstention failures; this is a targeted sample, not a
random or representative estimate of the 109-question set.

The corpus is a Tunisian Commercial Code edition reviewed through 15 February
2024 and notes amendments through Law No. 2019-47. This review checks answers
against that frozen corpus only. It does not establish that the edition is
current law today. “Correct” means consistent with the cited corpus in this
case, not legally verified by counsel.

## Findings

| Question ID | Legal issue | First-pass finding | Reason |
|---|---|---|---|
| `fr-single-006` | Accounting duty and exception | Mostly correct; one omission | Article 7 is cited and the answer states the physical-person turnover exception. It omits the requirement to follow professional practice and Articles 8–13. |
| `fr-single-008` | Which person authenticates accounting books | Incorrect | The question asks who initials the books. The answer instead gives the separate rule for seller and buyer to initial the seller's books on a business sale (Article 219); the requested rule is Article 9. |
| `fr-single-014` | Drafting business-sale contracts; exceptions | Correct but underspecified | Article 189 bis supports the stated default and the answer signals exceptions, but does not name the public-body, lien-release, and legally-authentic-act exceptions. The question asks who drafts “in principle,” so the default is answered. |
| `fr-single-015` | Written form and nullity | Missed answer (abstained) | The model abstains although Article 190 in the evaluation corpus lists the covered transactions and says writing is required on pain of nullity. |
| `fr-single-017` | Sale document available to creditors | Incorrect | The answer cites Article 250 on creditor notification and priority. The requested deposited sale deed and 20-day access period are in Article 192. |
| `fr-single-021` | Sixth-bid conditions, deadline, and exclusions | Correct | The answer combines Articles 194, 198, and 196. It includes the creditor/shortfall condition, ten-day period, exclusions, and same-conditions-and-deadlines rule. |
| `fr-single-027` | Permitted ways to draw a bill of exchange | Incorrect | The answer gives maturity forms from Article 290. The asked drawing forms are in Article 270, including drawing to the drawer's own order, on the drawer, for a third party, or payable at a third party's domicile. |
| `fr-single-030` | Effect of an invalid signature on other signatures | Ambiguous question; answer follows cheque law | The answer cites Article 356 and explicitly answers for a cheque. The approved expected answer is the analogous bill-of-exchange rule in Article 273. The question does not name the instrument, so the discrepancy exposes an underspecified question as well as an instrument-specific answer. |
| `fr-single-039` | Endorsement after protest | Correct under the stated facts; expected answer is incomplete | Article 282 says an endorsement after protest for nonpayment has only the effects of an ordinary assignment. The expected answer gives the general post-maturity rule but omits this explicit exception, despite the question specifying post-protest. |
| `fr-single-048` | Interest clause on a cheque | Missed answer (abstained) | Article 353 says an interest stipulation in a cheque is deemed unwritten; the model abstains. |
| `fr-single-051` | Who can receive an endorsement | Incomplete; retrieved/cited evidence misses the requested rule | The answer discusses named, blank, and non-order cheques. It does not answer that endorsement may be made to the drawer or another obligated person (Article 360). |
| `fr-single-057` | Identifying general crossing | Correct | The answer accurately describes two parallel front-side bars with no designation, or “banker”/equivalent between them, as provided in Article 383. |
| `fr-single-061` | Joint liability of cheque obligors | Missed answer (abstained) | Article 390 makes all cheque obligors jointly liable to the holder and allows individual or collective action without order; the model abstains. |
| `fr-cross-005` | Publication and creditor opposition deadlines | Missed answer (abstained) | Articles 191 and 193 supply the 15-day publication and 20-day opposition periods; the answer abstains. These are linked deadlines, so both conditions should be retained. |
| `fr-cross-015` | Certified-cheque provision and presentation period | Missed answer (abstained) | Articles 350 and 372 link the blocked provision to the presentation period: eight days for a cheque issued and payable in Tunisia, or 60 days if issued outside Tunisia, counted from its stated issue date. The model abstains. |
| `fr-cross-020` | Holder's remedies and reimbursement recourse | Partially correct; omits a requested conclusion | The reimbursement claim, interest, and costs are supported by Article 392. The question also asks whether the holder may proceed individually or collectively without order; that rule is in Article 390 and is not answered. |

## Tally and limitations

Of these 16 targeted cases, 5 are correct or mostly correct, 2 are correct
with material detail missing, 3 are incorrect or materially misdirected, 1
has an ambiguous question/instrument mismatch, and 6 are answerable questions
that the system abstained on. Categories are assigned at the case level and
are not a legal-accuracy score for the full evaluation set.

The review also found a gold-answer issue in `fr-single-039`: its expected
answer states the general post-maturity rule but does not capture the
post-protest exception that directly answers the question. `fr-single-030`
needs an instrument named in the question. These should be corrected in the
evaluation dataset before interpreting answer-quality metrics as legal
correctness. No amendment-history audit against newer legislation or review
by a qualified Tunisian lawyer is included here.

## Next validation

Have a qualified Tunisian legal reviewer independently verify the cases
marked incorrect, incomplete, ambiguous, or abstained, the two
question/answer-key issues, and the relevant article text and amendment status
before presenting this as a final legal correctness result. Preserve reviewer
role, review date, and disagreements; do not turn this targeted first pass
into a full-set accuracy claim.
