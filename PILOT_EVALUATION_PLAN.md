# Chat2Work pilot evaluation plan

Status: plan for review. Nothing in this document has been run yet.

## 1. Why this is needed

Every Chat2Work number so far comes from **hand-written synthetic conversations**, and most of those sets were also used to tune the rules. Each independent review then found failures those sets did not contain:

| Version | Review findings outside the sets |
| --- | --- |
| v0.1 | four false sales |
| v0.1.1 | two false sales, a phone number read as 66.89 billion baht |
| v0.1.2 | plain information statements read as purchases |

A green synthetic benchmark therefore says little about real chats. This plan describes how to measure real-world behaviour and usefulness honestly before anyone relies on the sale flag or the proposed actions.

Out of scope: no deployment, no automatic replies, no CRM or LINE integration, and no contacting customers on Chat2Work's behalf. Proposed actions are only shown to the participating business for rating. They are never executed.

## 2. Participants and consent

- **Businesses.** Recruit 6–10 small Thai service businesses across at least five of the target industries: air-con, CCTV, electrical, repair, contractor, printing, design, agency, solar, interior. Each signs a written data-sharing agreement covering:
  - the purpose;
  - who can see the data;
  - the retention period;
  - deletion on request;
  - that no data is used to train any third-party model.
- **Customers in the chats.** The business must have a lawful basis under Thailand's PDPA to share the conversations. Where customer consent is required, it is collected by the business before export. Conversations whose consent status is unclear are excluded, not anonymised and used.
- **Withdrawal.** A business or customer can withdraw at any time. Their conversations, labels and derived results are deleted, and the reported metrics are recomputed.

## 3. Data handling and anonymisation

1. **Export.** The business exports chats itself, for example as a LINE text export. Chat2Work staff never log in to a business's chat account.
2. **Anonymise before labelling.** On the business's own machine, or a controlled machine, replace:

   | Data | Replace with |
   | --- | --- |
   | names | `[ชื่อลูกค้า]`, `[ชื่อร้าน]` |
   | phone numbers, LINE IDs, emails | `[เบอร์]`, `[ไลน์]`, `[อีเมล]` |
   | bank accounts | `[บัญชี]` |
   | addresses and map links | `[ที่อยู่]` |
   | ID/tax numbers, licence plates, photos | `[เลขประจำตัว]`, `[ทะเบียน]` (photos dropped) |

   Keep prices, quantities, dates and times, since they are what the engine is evaluated on. Shift absolute dates by a fixed per-business offset if they could identify someone.
3. **Second-person check.** A second person reviews every anonymised conversation for remaining personal data before it enters the evaluation store. Any conversation that cannot be cleaned is excluded.
4. **Storage.** Keep the store encrypted, access-controlled, and outside this repository. **Never commit real conversations, even anonymised ones, to the Chat2Work repository or its CI.** CI keeps using synthetic data only.
5. **Retention.** Delete raw exports after anonymisation is verified. Delete anonymised data at the end of the agreed retention period.

## 4. Separate development and evaluation sets

- **Unit of splitting.** Split **by business**, not by conversation. Choose two or three businesses as development and keep the others entirely for evaluation. This keeps business-specific wording from leaking into the evaluation.
- **Freeze before use.** Before any rule changes:
  - freeze the evaluation set and record a SHA-256 of the anonymised files and of the labels;
  - commit the hashes (not the data) to the repository.
- **Development set.** Use it freely for error analysis and rule changes.
- **Evaluation set.** Run once per release candidate. Anyone who changes rules must not read evaluation conversations or their errors. A designated evaluator reports only aggregate metrics and failure categories.
- **When the evaluation set is spent.** If it is ever used for tuning, report it as development coverage from then on, the same way the synthetic holdouts are labelled today. Then collect a fresh one.
- **Size.** Aim for at least 300 evaluation conversations, including at least 60 with a genuine confirmed sale.
  - With 0 false sales observed, about 300 non-sale conversations are needed before the one-sided 95% upper bound on the false-sale rate falls below 1% under random sampling.
  - Real chats are not IID, so report per-business results as well.

## 5. Human labels

Two trained annotators label each evaluation conversation independently, following a written guideline. A third person adjudicates disagreements.

Per conversation:

| Field | Values |
| --- | --- |
| confirmed sale | yes / no / unclear. Unclear means even a person cannot tell; the engine should abstain on these. |
| deal state at the end | the README states |
| open obligations at the end | who owes what: send quotation, attend visit, pay deposit (amount if stated), etc. |
| money | each amount with its role; the deal value if one is clear |
| dates and times | each scheduling or deadline expression, and whether it is still active |
| next actions | which proposals a careful staff member would make, and which would be wrong or harmful |

Report inter-annotator agreement (Cohen's κ) for confirmed sale, deal state and open obligations. Revise the guideline if κ < 0.7 on any of them.

## 6. Usefulness ratings

For each evaluation conversation, the business owner or the staff member who handled the chat rates every proposed action. They see only the conversation and the proposal, not Chat2Work's internal signals.

| Rating | Meaning |
| --- | --- |
| useful | I would do this now |
| correct but not needed | true, but not worth doing |
| wrong | not true, or not my obligation |
| harmful | doing it would upset or mislead the customer, or lose money |

They also note anything important that Chat2Work did not propose, to measure missed actions.

**Primary usefulness metric:** the share of proposed actions rated *useful* or *correct but not needed*. Target ≥ 80% for "next-action usefulness". Report the *harmful* rate separately; target 0.

## 7. Metrics to report

Report every metric on the evaluation set, per release, overall and per business, with 95% confidence intervals (Wilson for rates):

| Metric | Target / note |
| --- | --- |
| false confirmed-sale rate (engine said sale, human said no) | < 3%, with the upper confidence bound reported |
| sale recall (engine confirmed ÷ human-confirmed sales) | report; low recall is acceptable only if those cases go to review |
| sale abstention rate (needs-a-human states) | report; also report sale recall **within** abstentions, i.e. how many abstentions were real sales |
| open-obligation accuracy (engine's open set matches the human set) | report |
| action precision (useful or correct ÷ all proposed) and missed-action rate | ≥ 80% precision |
| harmful-action rate | 0 |
| money: deal-value accuracy, and amount-role accuracy | report |
| dates: active scheduling and deadline expressions | report |
| review rate and time-to-review per conversation, from the pilot staff log | report |

Also publish the confusion examples by failure category: information-vs-purchase, refusal, document events, deferral, payments, rescheduling, money roles, completion, and attribution. Real data will add categories.

## 8. Procedure and stop criteria

1. Freeze the evaluation set (section 4).
2. Run the current release once on it. Record the results as the **baseline**, including all failures by category.
3. Rule changes may use **only** the development set. Re-run the evaluation set only for a release candidate, and at most once per candidate.
4. **Stop and fix before any wider use if any of these occur:**
   - the false-sale upper bound is ≥ 3%;
   - any harmful action;
   - action precision < 70%.
5. A release may be called "pilot-validated" only if it passes the targets on a frozen evaluation set it was not tuned on, and the businesses agree the actions are useful. Even then it remains human-reviewed: actions are proposals and are never executed automatically.

## 9. What remains unproven until this is done

- Real-world false-sale rate, sale recall, and action usefulness.
- Behaviour on real Thai chat: slang, typos, stickers, voice-message transcripts, long multi-deal threads, group chats and forwarded messages.
- Confidence calibration. Today's confidences are hand-set heuristics; calibrate them on the development set and check them on the evaluation set.
