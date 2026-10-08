# Chat2Work Core: self-audit

## v0.1.4 correctness and safety patch (2026-10-08)

### Starting point

- **Baseline:** v0.1.3 at `563eb8a7e674fd974fb762f779b7ddcb4ecf4032` (538 tests, CI green). HEAD equalled the remote, the working tree was clean, and there was no newer work, no other branch and no repository instructions.
- **Input:** 13 finding groups (P1-01 to P2-10) from an independent audit of that commit.
- **Scripts:** no new audit or reviewer script was supplied with this brief. Only the earlier 28-check script from the v0.1.1 review exists, and it was run. Every case in the brief was reproduced with a new script written for this patch.
- **The synthetic URL** `https://maps.app.goo.gl/synthetic-audit` was never opened. It appears only as test text that a regular expression reads.

### Method

1. **Reproduce.** Ran every case from the brief on `563eb8a`. All of P1-01 to P2-08 reproduced as described, plus a `KeyError: 'role'` for an empty adapter value (see the table).
2. **Tests first.** Wrote `tests/test_v014_correctness.py` before changing behavior. It has regression families with neighbouring variants and positive controls for each group. On `563eb8a`, **94 of its 140 tests failed**. Seven more tests were added later: two variants found while probing, and five for the new harness.
3. **Safety scenarios first.** Wrote `data/safety_scenarios.jsonl` (28 cases) with structured obligations and harm tags. Froze its labels (SHA-256 `b14cbdc7…`, in `data/blind_first_runs.json`), then ran it on the unmodified engine: **9/28 passed**, with **4 false sales / 24** and 2 genuine sales dropped without review.
   - One label correction was made before the freeze and before that run. The first draft of s21 listed no open obligation, but the shop's `นัดติดตั้งวันเสาร์` is a stated booking.
   - No label in any earlier dataset was changed, and no case was removed.
4. **Shared causes, not strings.** Fixed each group at its shared cause in the semantic layer, the rules or the engine. No exact-string exception was added, and sale detection was not disabled. See "Shared causes" below.
5. **Verification.**
   - Diffed proposed actions and deal states on all 171 earlier label and action cases against `563eb8a`: **0 changed**.
   - Label metrics are byte-identical on the five label splits; review and abstention rates are unchanged.
   - Re-checked invariants on all 199 conversations (421 actions): IDs, exact evidence, actors, references, confidence, and human approval on every action.

### The 13 groups: before and after

| ID | Reproduction (summary) | v0.1.3 (`563eb8a`) | v0.1.4 |
| --- | --- | --- | --- |
| P1-01 | after `ราคา 18500 บาทครับ`: `เอาครับ มั้งนะ`, `เอาครับ น่าจะเอานะ`, `ตกลงซื้อเลยครับมั้ง` | **confirmed sale** (0.96) in all three | `possible_acceptance` (`hedged_acceptance`, 0.60), review, `confirm_deal_status` with the reply as evidence. Control `ยืนยันตามราคานี้ครับ` still confirms. |
| P1-02 | after an acceptance: `ถ้าใบเสนอราคาส่งไม่ทันไม่เป็นไร ผมยกเลิกงานนี้ครับ` | sale stayed confirmed | `cancelled`; the acceptance and the cancellation are both kept as evidence; `confirm_cancellation`. Control `ถ้าลดได้ เอาครับ` is still not acceptance. |
| P1-03 | after an acceptance: `เพื่อนบอกว่าดี แต่ผมไม่ซื้อครับ` | sale stayed confirmed | `declined`. `เพื่อนบอกว่าไม่เอาแล้ว` alone is still `changed_needs_review`, not a cancellation; `…แต่ผมยังเอาตามเดิม` keeps the sale. |
| P2-01 | booked Saturday 09:00, then `ไม่เลื่อนนัดครับ ใช้วันเดิม` / `อาจจะเลื่อนนัดครับ ยังไม่ได้ยืนยันวันใหม่` / `ไม่เลื่อนวันที่โอนมัดจำครับ ใช้วันเดิม` | slot superseded and `appointment_time` requested (first two); `confirm_payment_schedule` (third) | slot and its time kept; the shop's booking still tracked; no payment-schedule change. The hedged one adds `possible_reschedule` and a clarification note on `confirm_appointment`. Genuine reschedules still supersede; a payment reschedule still leaves the installation. |
| P2-02 | PDF request, then `ส่งรูปให้แล้วครับ ส่วน/แต่ใบเสนอราคาจะส่งพรุ่งนี้`, `ส่งราคาให้แล้วครับ ใบเสนอราคาจะส่งพรุ่งนี้` | quotation closed; no `send_quotation` | quotation stays open: `send_quotation` plus the tracked promise (deadline `พรุ่งนี้`). Photos are `information_sent`; the price is `price_sent`. An actual document delivery still closes it. |
| P2-03 A | deposit promise 5000, then `โอนค่าอะไหล่ 5000 บาทแล้วครับ มัดจำยังค้างอยู่` | deposit closed | deposit open; the report carries `purpose: "ค่าอะไหล่"` |
| P2-03 B | promise 2000, `โอนแล้ว 1000 บาทครับ`, then `โอน 1000 บาทแล้วครับ ยอดเดียวกับเมื่อกี้` | counted twice, deposit closed | the repeat is `repeat_of_previous`; 1000 of 2000 is paid, so the deposit stays open with `partial_payment_reported` |
| P2-03 C | `โอนแล้วครับ แต่ยังไม่ครบ` | deposit closed | stays open, `partial: true`, warning; no remaining amount invented |
| P2-04 | `ช่างมาถึงแล้วครับ ยังไม่ได้เริ่มติดตั้ง` | installation commitment closed | `technician_arrived`; the installation stays tracked. Real completion still closes it; negated, conditional and hedged completion don't. |
| P2-05 | `นัดติดตั้งวันเสาร์`, then `ผมว่างคุยโทรศัพท์วันนี้ 18:00 ครับ` | 18:00 filled the installation time | the time carries `event: "call"`; `appointment_time` is still requested |
| P2-06 | `ร้านอื่นราคา 18500 บาทครับ ร้านผมยังไม่ได้คิดราคา` | opportunity 18,500 | role `competitor_price`, opportunity `null`, the price enquiry stays open. A later `ร้านเราราคา 17900 บาท` gives 17,900. |
| P2-07 | fake adapters: amount `-1000` USD; `NaN` / `Infinity`; `{}`; acceptance 0.99 on `ขอคิดดูก่อนครับ` | ignored silently; ignored silently; **`KeyError: 'role'`**; **confirmed sale** | `ValueError` naming the type and problem for every malformed value. USD is never relabelled THB or used for the THB opportunity. The contradicted acceptance gives `acceptance_needs_review` with evidence-backed `confirm_deal_status`. Valid adapters work unchanged. The README no longer implies that evidence and confidence prove semantics. |
| P2-08 | `นัดติดตั้งวันเสาร์ 09:00`, then the map URL vs `[ที่อยู่]` | URL: address present; placeholder: `installation_address` missing | both: address present (typed placeholders, `chat2work/redaction.py`); redaction-invariance tests for address, phone, name and bank-account placeholders |
| P2-09 | pilot plan defined usefulness as (useful + correct) ÷ proposed | metrics conflated | usefulness = useful ÷ rated; correctness = (useful + correct-but-not-needed) ÷ rated; wrong and harmful separate; missed useful actions; review/correction time; denominators and unrated handling fixed in advance; no usefulness claim without human ratings; supervised air-conditioning pilot recommended first |
| P2-10 | obligations scored as value strings only; no harm-specific gates | — | structured obligations (actor, amount, purpose, target, deadline); optional opportunity, money-role, missing-information and review labels; harm-tagged safety cases must all pass; new gate: genuine sales dropped without review = 0, on every set |

### Shared causes and fixes

- **Clause scope** (`semantics.py`).
  - A condition with its own consequent (`…ไม่เป็นไร`, `…ก็ได้`) no longer governs the next clause (P1-02). The same scoping lets a genuine acceptance after such a clause count.
  - Reported speech ends at a contrastive first-person clause (`แต่ผม…`), for clause status, cancellation attribution and negotiation (P1-03).
- **Assertion status.**
  - `hedged()` ties a hedge to a decision when it is in the decision's clause or in a neighbouring hedge-only clause (P1-01).
  - Negated and uncertain reschedules move nothing (P2-01).
  - `อาจ` no longer matches inside `เอาจ้า`.
- **Event–object binding.**
  - A completed delivery closes only the objects in its own clause (P2-02).
  - Arrival is separated from completion (P2-04).
  - Call or chat times are tied to the call (P2-05).
  - Competitor amounts get their own role (P2-06).
- **Payment matching** (P2-03): purpose from `มัดจำ` or a `ค่า…` word in the report clause, explicit repeat wording, and incomplete reports without an amount.
- **Boundary validation** (P2-07): `chat2work/validation.py` runs inside `_validate`; references are checked again on the final graph. The engine's acceptance cross-check uses the same `acceptance_contradicted()` as the rules.

### Schema and behavior changes

- New signal types: `technician_arrived`, `possible_reschedule`.
- New values and metadata: `possible_acceptance` value `hedged_acceptance`; `payment_reported` metadata `purpose`, `repeat_of_previous`, `partial`; date metadata `event: "call"`.
- New money role: `competitor_price`.
- New warnings: `acceptance_contradicted_by_evidence; confirm_with_customer`, `non_thb_amount; not_used_for_thb_opportunity`, `reschedule_not_confirmed; existing_slot_kept`.
- The opportunity uses only THB `price`/`total` amounts from the shop.
- Adapter values that were previously accepted, or that crashed, now raise `ValueError` before derivation.
- `evaluate.py` evaluates `safety_scenarios.jsonl` by default (7 reports instead of 6). Every report gains `genuine_sales_dropped_without_review`, and scenario reports gain `safety_cases` and `safety_case_failures`. `tests/test_v011_safety.py` was updated for the seventh report.
- Version 0.1.4; provider `thai_rules_v0.1.4`.

### Results (local, Python 3.13.16; CI steps also run verbatim in clean 3.11 and 3.13 environments)

- **Tests:** `python -m pytest -q` → **685 passed** (538 in v0.1.3).
- **Benchmark:** `python evaluate.py --check` → exit 0 on all seven sets. Label scores are byte-identical to v0.1.3.
- **Reviewer script:** the 28-check script from the v0.1.1 review gives **28/28**. No newer script was supplied, so none other was run.
- **False sales:** 0 / 159 non-sale conversations across all seven sets: 135 in the six earlier sets and 24 in the safety scenarios. The safety scenarios were written from the audit and used to check the fixes, so they are not blind.
- **Sale recall:** 40 / 40. Every labelled sale is confirmed, and **0 genuine sales are dropped without review**.
- **Safety scenarios:**

  | Run | Case accuracy | Open obligations | Sale recall | False sales | Silent sale drops | Safety failures | Review rate | Sale abstention |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | first run, v0.1.3 engine | 0.321 (9/28) | 0.714 | 2/4 | 4/24 | 2 | 19/22 | 0.643 | 0.036 |
  | v0.1.4 | 1.000 | 1.000 | 4/4 | 0/24 | 0 | 0/22 | 0.714 | 0.107 |

- **Earlier action scenarios:** unchanged at 1.000.
- **Usefulness:** human usefulness is **not measured**, and nothing here supports a real-world or unattended-use claim.

### Remaining weaknesses (found while probing, not fixed in this patch)

- **Reported speech without `แต่`.** `เพื่อนบอกว่าร้านนี้ดี ผมเอาครับ` is not read as the customer's acceptance. The engine stays at `inquiry` with no review (conservative, but silent).
- **Hedged refusal.** `คงไม่เอาครับ` changes nothing and is not flagged.
- **Payment identity.** Transfer identity comes only from explicit repeat wording; payment purpose only from `มัดจำ` or `ค่า…`.
- **Event times.** Call words decide them, so `โทรมาก่อนเข้า 10:00` re-asks for the visit time.
- **Arrival vs completed survey.** A survey visit reported only as `ช่างเข้ามาดูหน้างานแล้ว` stays tracked.
- **Competitor prices** are recognised only next to a few explicit words.
- **Adapters.** The acceptance cross-check reads the evidence with the same Thai rules, so an adapter acceptance on wording the rules cannot read is still trusted.

## v0.1.3 event-classification patch (2026-10-07)

### Starting point

- **Baseline:** v0.1.2 at `3ae8778` (427 tests, CI green, 28/28 on the v0.1.1 reviewer script). HEAD equalled the remote; there was no newer work, no other branch and no repository instructions.
- **Input:** nine problem groups from a new independent review.
- **Missing script:** the brief mentions a **new 32-check reviewer script, but it was not supplied**. Only the earlier 28-check script is available, and it was run.

### Method

1. **Reproduce.** Reproduced all nine groups on v0.1.2 (see the before/after table).
2. **Tests first.** Wrote `tests/test_v013_events.py` before changing behavior, as regression families with natural variants and positive controls:
   - pronouns, courtesy, informal endings;
   - clause order, split and merged messages;
   - negation, conditions, reported speech.

   On v0.1.2, **48 of its 93 behavioral tests failed**. The 9 semantic-layer unit tests could not run, because the layer did not exist yet.
3. **Semantic layer.** Added `chat2work/extractors/semantics.py`:
   - a clause splitter;
   - a clause classifier, returning asserted / negated / conditional / future / questioned / reported / uncertain;
   - a target classifier, returning purchase / document / information / payment / appointment.

   Every affected decision now classifies the event first: refusals, cancellations, deliveries, receipts, payment reports, completions, reschedules and negotiation. No exact-string blacklist was added.
4. **Action scenarios.** Added `data/action_scenarios.jsonl` (24 scenarios), with labels frozen (SHA-256 `b31df0fb…`) before the first run. A new scorer, `evaluate_actions`, checks:
   - the sale decision;
   - required actions;
   - forbidden actions;
   - the exact set of still-open obligations.

   Recorded the first run, then fixed only what it showed.
5. **Probes.** Ran natural-variant probes and fixed the general gaps they exposed.
6. **Verification.**
   - Diffed proposed actions and deal states on the 147 earlier label cases against v0.1.2: **0 changed**.
   - Re-checked evidence, IDs, references, confidence and approval invariants on all 171 conversations (349 actions).

### The nine groups: before and after

| # | Reproduction (summary) | v0.1.2 | v0.1.3 |
| --- | --- | --- | --- |
| 1 | `ส่งแคตตาล็อกให้ครับ` / `ส่งรูปให้ครับ` → `เอาครับ` | confirmed sale | `information_accepted` and `send_offered_information`; never a sale |
| 2 | after a sale: `ผมไม่ซื้อครับ`, `ขอโทษครับ ไม่จ้างครับ`, `ไม่ซื้อครับ ขอบคุณที่ส่งรูปมาแล้วนะครับ` | sale stayed confirmed | `declined`; acceptance kept as history. Refusals are read per clause after courtesy and pronouns; an unrelated `แล้ว` no longer suppresses them. |
| 3 | PDF request → `ถ้าส่งใบเสนอราคาแล้วจะโทรแจ้ง`, `พรุ่งนี้จะส่งใบเสนอราคา แล้วโทรแจ้ง`, `ส่งใบเสนอราคาแล้วใช่ไหม`, `ถ้าได้รับใบเสนอราคาแล้วจะ…` | request closed in all four | request stays open with `send_quotation`. Only an asserted, completed delivery or receipt closes it. |
| 4 | `เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้` → `เอาครับ แต่ยังไม่ต้องส่ง`; deferral inside the request; later go-ahead | `send_quotation` **and** `await_customer_go_ahead` together; in-request deferral ignored; go-ahead did not reopen | the promise is on hold: only `await_customer_go_ahead`, with the promise as evidence. In-request deferral is honoured. A go-ahead reopens `send_offered_information` / `send_quotation`. |
| 5 | `ถ้าโอนแล้วจะส่งสลิปให้`; `โอนแล้ว 1000 บาท ที่เหลืออีก 4000 จะโอนพรุ่งนี้` | conditional counted as a payment report; partial payment closed everything | no report for the conditional. The partial payment records `reported_amount: 1000`; the remainder becomes an open commitment (4,000, `remaining_balance`, deadline `พรุ่งนี้`). A partial report without a remainder keeps the original open, with a warning. |
| 6 | `ขอเลื่อนส่งรูป…`, `ขอเลื่อนวันที่โอนมัดจำ…`, `ขอเลื่อนวันส่งใบเสนอราคา…` | installation superseded in all three | installation untouched; `deliverable_reschedule_request` or `payment_reschedule_request` |
| 7 | `ราคารวม 18500` → `ลดให้เหลือ 17000`; `ราคา 18500` → `รวมค่าแรงไว้แล้ว 1500` | opportunity 18,500 (net price missed); then **1,500** | opportunity 17,000 (revised net price); then 18,500 (labour is `included_component`) |
| 8 | `ติดตั้งเสร็จแล้วมั้งครับ` | completion closed tracking | `completion_uncertain`: tracking kept, plus `verify_completion` |
| 9 | after a sale: `ยกเลิกใบเสนอราคาครับ แต่ยังซื้อสินค้าเหมือนเดิม` | **deal cancelled** | quotation request withdrawn (`quotation_declined`); sale kept |

### Extra defects found during verification (fixed, with tests)

- **Clause splitting broke phrases.** `แนบไฟล์ใบเสนอราคา PDF ให้แล้ว` split at spaces and lost the delivery. Latin words, numbers and particles now continue the clause. This also fixed one holdout4 regression it had caused.
- **Polite reschedule requests were dropped.** `…เลื่อนเป็นวันศุกร์ได้ไหม` is a request, not a question.
- **`แต่ถ้า…` conditions were missed.** They now govern the next clause.
- **Hypothetical haggling revoked a sale.** `ถ้าแพงกว่านี้ผมไม่ซื้อ` revoked the sale through the negotiation rule. Hypothetical negotiation no longer counts.
- **Action scenarios, first run.** A deposit's remainder was tracked as a generic payment; remainders now inherit the purpose.
- **Informal and colloquial forms.**
  - `เอาจ้า` / `เอาคับ` were missed as acceptance.
  - Colloquial `ละ` (`โอนละนะคะ`, `เสร็จละครับ`) now marks completion.
  - `หากโอนเรียบร้อยแล้วจะแจ้งอีกที` was misread as decision pending.
  - A `ขอบคุณ` (thanks) reply now answers an information offer.

### Results (local, Python 3.13.16)

- **Tests:** `python -m pytest -q` → **538 passed** (427 in v0.1.2).
- **Benchmark:** `python evaluate.py --check` → exit 0 on the five label splits plus the action-scenario gate. Label scores are byte-identical to v0.1.2.
- **Reviewer script:** 28-check script from the v0.1.1 review: **28/28**. The 32-check script was **not run**, because it was not supplied.
- **Action scenarios:**

  | Run | Case accuracy | Open obligations | Sale recall | False sales | Review rate | Sale abstention |
  | --- | --- | --- | --- | --- | --- | --- |
  | first run, before fixes | 0.958 (23/24) | 0.958 | 5/5 | 0/19 | 0.458 | 0.042 |
  | now | 1.000 | 1.000 | 5/5 | 0/19 | — | — |

  The review rate is mostly the routine "no reference date" warning; sale abstention is the share of cases left for a human to decide.
- **Sale decisions, all six sets:** 0 false sales in 135 non-sale conversations and full sale recall. The review and abstention rates per set are in the README. With IID sampling the one-sided bound would be about 2.2%, but the sets are hand-written and mostly tuned, so **this is not real-world evidence**.
- **Usefulness:** human usefulness is **not measured**.

### CI note

The first push of v0.1.3 (`911ae43`) **failed CI** on all three Python versions. Tests and the gated benchmark passed; the workflow's summary-print step failed with `KeyError: 'metrics'`. That step assumed every report has label metrics, and the new action-scenario report does not.

The step was fixed to print both report types. Every workflow step was then run verbatim from a clean copy before the fix was pushed. Lesson: run the workflow's own commands locally, not just pytest and `evaluate.py`.

### Remaining weaknesses

- **Small heuristic event layer.**
  - Clause splitting depends on spaces and a few conjunctions.
  - A delivery split across messages is not recognised.
  - A deferral without a named object (`ไว้ค่อยส่งทีหลัง`) is not recorded.
  - A rescheduled quotation delivery leaves `send_quotation` without the new date.
- **Payments.** Partial-payment arithmetic only uses amounts stated in the same message, and nothing is bank-verified.
- **Inherited.** Thai patterns, not a parser; one deal and one appointment slot per conversation; synthetic data only; uncalibrated confidence.

### Recommended next step

Execute [PILOT_EVALUATION_PLAN.md](PILOT_EVALUATION_PLAN.md):
- consented, anonymised real conversations;
- development and evaluation sets split by business and frozen before use;
- double human labels with adjudication;
- usefulness ratings by the businesses themselves.

Until then, no claim of real-world reliability or production readiness.

---

## v0.1.2 semantic patch (2026-10-07)

### Starting point

- **Baseline:** v0.1.1 at `7dfab32` (282 tests, CI green), plus a later summary-only commit `3ba36d5`.
- **Input:** an independent read-only review of `7dfab32` (`Chat2Work_v0.1.1_review.md`) and its expanded version, which came with a 28-check script and raw results.
- **Reproduction:** I reproduced every finding. The reviewer's script gave **9/28 passed, 19 failed** on the baseline, identical to the review.
- **Scope:** fix the 15 findings without adding product features. No UI, CRM, database, integration, execution, or paid LLM.

### Corrections to v0.1.1 claims

v0.1.1 made two claims that were not fully true:

- **Typed prices and quotations.** The v0.1.1 README, SELF_AUDIT and Thai summary said a price typed in chat never counts as a delivered quotation. In fact the old `ส่งราคา…แล้ว` pattern still emitted `quotation_sent`, which closed a requested PDF quotation (finding 3).
- **Rule-of-three bound.** v0.1.1 described the bound as "about 3.0%, at the target". The correct figure is 2.97%, and the IID sampling assumption behind it does not hold for this corpus.

Both are corrected below and in the README.

### Method

1. **Tests first.** Wrote `tests/test_v012_semantics.py` before changing behavior. It is organized by semantic invariant: what is accepted, rejected, rescheduled, completed or priced, and whether it is asserted, negated, conditional, deferred or reported. It includes variations and purchase controls, not just the reviewer's strings. On the v0.1.1 baseline, **89 of its 129 tests failed**.
2. **Fixes.** Each fix makes the event/object and the assertion status explicit before a state change, fulfilment, supersession or revenue value. Re-run the reviewer's script: **28/28**.
3. **Adjacent probes.** Probed around each fix and found four more defects, one of them my own regression: broadening the identifier rule to `รุ่น…` swallowed `รุ่นนี้ 18,500 บาท` ("this model, 18,500 baht"). All four are fixed, with tests.
4. **Holdout4.** Wrote 20 cases with labels frozen (SHA-256 `82c29a53…`) before the first run. Recorded that run, then fixed only the general weaknesses it showed. Holdout4 is now development coverage.
5. **Diff and invariants.** Compared proposed actions on all 127 earlier benchmark conversations against v0.1.1: only two changed, both intended (see below). Re-checked the structural invariants.

### Findings: before and after

| # | Sev. | Reproduction (summary) | v0.1.1 | v0.1.2 |
| --- | --- | --- | --- | --- |
| 1 | P1 | `ส่งแคตตาล็อกให้ได้นะครับ` / `เดี๋ยวส่งรูปแอร์ให้ดูครับ` → `เอาครับ` | confirmed sale | `information_accepted`, no sale. Statement offers are classified by object; with a price or ordering wording they are `mixed` and need review. |
| 2 | P1 | accepted sale → catalog/photo offer → `ไม่ซื้อครับ` / `ไม่จ้างครับ` | sale stayed confirmed | `declined`. Explicit transaction refusal is never overridden by the previous offer; a bare `ไม่เอา` to an offer still only declines the object. |
| 3 | P2 | PDF request → `ส่งราคาให้แล้วครับ 18500 บาท` | `quotation_sent`, request closed | `price_sent`; `send_quotation` stays until the document is sent or received |
| 4 | P2 | `ถ้าติดตั้งเสร็จแล้วจะโทรแจ้งครับ` | completion closed the install commitment | not asserted, so no completion; the commitment stays tracked and no phantom appointment is created |
| 5 | P2 | `ขอเลื่อนโอนมัดจำไปวันศุกร์ครับ` | installation superseded, new time requested | `payment_reschedule_request` and `confirm_payment_schedule`; the appointment is untouched (also when both move in one message) |
| 6 | P2 | `เอาครับ แต่ยังไม่ต้องส่งครับ` | send-now proposal | `deferred: true` and `await_customer_go_ahead`; a later explicit request reopens sending |
| 7 | P1 | `เบอร์โทร +66890000000 ครับ` after a price question | 66,890,000,000 THB opportunity | no amount. Phone-like identifiers are masked first; a bare number is a price only in a price-shaped reply. |
| 8 | P2 | gift `แถม…มูลค่า 500`, included `ค่าแรง 1500 บาทรวมอยู่ในราคาแล้ว`, expense `จ่ายค่าอะไหล่ 1500` | replaced or became the opportunity | `gift_value` / `included_component` / `expense` roles are never revenue. An earlier explicit total is kept against an unrevised later price, with a warning. |
| 9 | P2 | `ช่างบอกราคา 18500 บาท` | role `budget`, opportunity null | `price`; `งบ` must be a real budget word |
| 10 | P2 | `15 ต.ค. 70` with a reference date | raw `15 ต.ค.`, resolved 2026-10-15 | raw `15 ต.ค. 70`, unresolved (`ambiguous`) |
| 11 | P2 | `ไม่ต้องส่งใบเสนอราคา`, `ใบเสนอราคามีอายุกี่วัน`, `ได้รับใบเสนอราคาแล้ว` | request plus send action; receipt read as possible acceptance | `quotation_declined` / `quotation_question` / receipt; no send action, no deal-state change |
| 12 | P2 | `เพื่อนบอกว่าไม่เอาแล้ว แต่ผมยังเอาตามเดิม` | cancelled | sale kept. Without the reaffirmation it becomes `reported_cancellation`, needs review, never cancels. |
| 13 | P2 | unknown speaker `นัดติดตั้งวันเสาร์ครับ` | derived missing-info at 0.84 | ≤ 0.65; derived nodes never exceed their source |
| 14 | P2 | custom adapter signal `s2` | final IDs `s2, s2, s3` | unique IDs; final-output validation also checks action references |
| 15 | P2 | address then `ที่อยู่เมื่อกี้ผิดครับ` | address treated as present | `installation_address` requested again until a new address follows |

### Extra defects found during verification (all fixed, with tests)

- **Adjacent probes:**
  - `รุ่นนี้ 18,500 บาท` lost its price, and `id`/`line` could match inside English words. These were my regressions, now fixed.
  - `ไม่ซื้อที่อื่นแน่นอน` (won't buy elsewhere) was read as rejecting the deal. This was inherited from v0.1.
  - A statement offer plus ordering wording counted as pure information. It is now mixed and needs review.
  - A message postponing both the appointment and the payment lost the appointment change.
  - First-person `ผมบอกว่าไม่เอาแล้ว` must remain an own cancellation.
- **Holdout4 first run:**
  - `จะเข้าทำวันพุธ` was missed as a visit commitment, twice.
  - `ไม่ต้องทำใบเสนอราคา ตกลงจ้างเลย` and `เอาครับ ไม่ซื้อร้านอื่นแล้ว` were missed as sales.
  - `ไม่เอาแคตตาล็อก ตกลงซื้อเลย` (found while fixing those) was read as a rejection.

### Results (local, Python 3.13.16)

- **Tests:** `python -m pytest -q` → **427 passed**.
- **Benchmark:** `python evaluate.py --check` → exit 0 on all five required splits. Earlier splits are byte-identical to v0.1.1.
- **Reviewer's script:** **28/28**, up from 9/28.
- **Action diff on the 127 earlier conversations:** two changed, both intended.
  - `h3_contractor_quote_received`: the receipt report no longer creates a possible-acceptance review.
  - `h3_solar_survey_completed`: the completion message no longer spawns a new appointment and its missing-info requests.
- **Holdout4 first blind run:**

  | Commitments F1 | Amounts | Amount roles | Dates | Pending | Sale | False sales |
  | --- | --- | --- | --- | --- | --- | --- |
  | **0.667, below the 0.90 gate** (4 events) | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 0/15 |

  Every miss was on the cautious side.
- **False confirmed sales:** 0 in 116 negative synthetic conversations. The exact one-sided bound would be about 2.6% under IID sampling, which does not apply here. **The < 3% target is not demonstrated.**
- **Usefulness:** human usefulness remains **unmeasured**.

### Remaining weaknesses

- **Still patterns.** Semantic qualifiers (object, attribution, assertion, deferral) are Thai patterns, not a parser. Each review round found adjacent cases.
- **Heuristic money roles.**
  - Gift, component and expense roles come from nearby words.
  - 9+ digit unseparated numbers are always treated as identifiers.
  - An unclear later price is kept and flagged, not resolved.
- **Offer detection.** It needs listed information objects and a send/receive verb, and looks back only three messages.
- **Inherited from v0.1.1.** Single appointment slot, one deal per conversation, synthetic-only evaluation, uncalibrated confidence.

### Recommended next step

1. Stop adding rules for synthetic probes.
2. Freeze a separately authored, consented and anonymized **real-world** set before changing anything.
3. Have humans rate next-action usefulness on it.
4. Only then decide whether to strengthen the semantic contract further, for example an LLM extractor behind the same `Extractor` protocol and final-output gates.

---

## v0.1.1 safety patch (2026-10-07)

### Starting point

- **Baseline:** commit `7c6a8fd` on `claude/chat2work-core-v0-1-nvtlab`: 207 tests, CI green.
- **Newer work:** the only later commit (`3d64ffd`) added a Thai summary text file. It was preserved.
- **Repository state:** there are no other branches, no PRs, and no repository instructions.
- **Scope:** fix the five defects from the independent review (`Chat2Work_review.md`), without expanding the product.
  The output schema is unchanged apart from added signal and action types and `metadata.slot_status`.

### Method

1. **Tests first.** Wrote `tests/test_v011_safety.py` before changing behavior. It holds the five review reproductions plus systematic variations:
   - prices, quantities and specs inside offers;
   - expanded replies and intervening messages;
   - mixed information-or-purchase questions;
   - positive purchase controls;
   - quotation lifecycle;
   - payment and attendance together;
   - evaluator CLI exit codes;
   - single and repeated reschedules.

   On the unmodified baseline, **36 of its 52 tests failed**. The 16 that passed were positive controls and behaviors that were already correct.
2. **Fixes.** Fixed the defects, then ran the full suite and all benchmark splits.
3. **New blind set.** Wrote **holdout3** (20 cases) and froze its labels (SHA-256 `f5b0fcf7…`, recorded in `data/blind_first_runs.json`) before its first run. Recorded that first run, then fixed only general weaknesses it exposed, using regression tests worded differently from holdout3. Holdout3 is now development coverage.
4. **Probes and invariants.** Ran free-form adversarial probes. Checked structural invariants over all 127 dataset conversations and their 253 proposed actions: exact evidence, grounded actions, no auto-approval, no date resolution without a reference date.

### The five defects: before and after

| # | Reproduction | Before (7c6a8fd) | After (v0.1.1) |
| --- | --- | --- | --- |
| 1 | `รับแคตตาล็อกพร้อมราคาไหมครับ` → `เอาครับ`, plus the photo, quotation-offer and `เอาครับ ส่งมาเลย` cases | `confirmed_sale: true` in all four | `confirmed_sale: false`; `information_accepted` with `offer_message_id`; `send_offered_information`, or `send_quotation` plus `quotation_request` for the quotation offer. Positive controls still confirm. |
| 2 | `ราคา 18500 บาทครับ` → `ขอใบเสนอราคาเป็น PDF หน่อยครับ` | only `add_to_revenue_radar` | `send_quotation` cites the customer's request and does not claim a business promise |
| 3 | `จะเข้าหน้างานวันเสาร์ครับ` → `โอนแล้วครับ` | `track_commitment` disappeared | `track_commitment` keeps `attend_appointment`; `check_payment` remains (payment unverified) |
| 4 | `evaluate.py --dataset /tmp/…does-not-exist.jsonl --check` | printed `[]`, exit 0 | `error: dataset not found: …`, exit 2. Missing required defaults, empty files and duplicates also exit 2. A failing metric still exits 1. |
| 5 | `จะเข้าติดตั้งวันเสาร์ 09:00` → `ยกเลิกนัดวันเสาร์ เลื่อนเป็นวันศุกร์แทน แต่ยังไม่ทราบเวลา` | only `installation_address` missing; old `09:00` reused; old commitment still tracked | both `installation_address` and `appointment_time` missing; old slot, `09:00` and commitment marked `superseded` with evidence kept; `confirm_appointment` cites the reschedule; deal not cancelled |

### How each defect was fixed

1. **Informational acceptance.**
   - The extractor classifies the shop's latest open yes/no question by **what it offers**: information, purchase, both, scheduling, or other. A price word or digit no longer makes a question purchase-related.
   - A generic yes of any length is read against that offer.
   - Wording that names the purchase (`ยืนยันตามราคานี้`, `ยืนยันซ่อมตามราคานี้`) is acceptance regardless of the question.
   - Ambiguous replies become `possible_acceptance` (0.60, needs review).
   - Declining offered information no longer declines the deal.
2. **Quotation request.**
   - A price enquiry (`price_enquiry`) is now separate from a request for a quotation document (`quotation_request`).
   - Requests and promises close only on `quotation_sent` or `quotation_received`; a typed price does not close them.
   - An unanswered price enquiry proposes `answer_price_enquiry`.
3. **Payment report and attendance.** Commitments close only on evidence of their own kind:
   - payment commitments by a payment report;
   - attendance commitments by a reported completion (`appointment_completed`) or by a superseding reschedule;
   - quotation promises by delivery.
4. **Evaluator.** `evaluate.py` validates its selection before evaluating anything. `holdout3.jsonl` is a fourth required split.
5. **Reschedules.**
   - A reschedule from either side supersedes earlier slot signals.
   - Inside the reschedule message, dates before `เลื่อน…` are the old slot and dates after it are the replacement.
   - Only times from the active arrangement satisfy `appointment_time`.
   - `ยกเลิกนัด…` without a new date also supersedes the slot and asks for a new time; the deal stays open.

### Extra defects found during verification (all fixed, with tests)

- **holdout3 first run** (5 failing cases):
  - `เลื่อนเป็นวันพฤหัส เวลาเดี๋ยวแจ้งอีกที` counted as deal pending and undid a sale.
  - `ยืนยันซ่อมตามราคานี้` and `สั่งเลยครับ` were missed as acceptances.
  - `จะโอนค่าสำรวจพรุ่งนี้` became an attendance commitment.
  - `จะรอช่างที่บ้าน` was missed as attendance.
- **Probe: a false sale of the same family as defect 1.** `ส่งแคตตาล็อกให้ดูไหม` / `ราคา 9,000 บาท` / `เอาครับ` confirmed a sale. An unanswered information offer now stays open behind a later shop statement, so this is `possible_acceptance`.
- **Probe: product pick after an information offer.** `ไม่ต้องครับ เอาตัวนี้เลย` after a photo offer produced nothing. It now needs review.

### Results (local, Python 3.13.16)

- **Tests:** `python -m pytest -q` → **282 passed**.
- **Benchmark:** `python evaluate.py --check` → exit 0 on all four required splits.
  - Dev, holdout, and holdout2 metrics are **byte-identical to v0.1**.
  - Holdout3 now scores 1.000 on every metric, after tuning.
- **Holdout3 first blind run:**

  | Commitments F1 | Amounts F1 | Dates F1 | Pending F1 | Sale F1 | False sales |
  | --- | --- | --- | --- | --- | --- |
  | **0.857, below the 0.90 gate** | 1.000 | 1.000 | 0.800 | 0.727 | 0/13 |

- **False confirmed sales:** 0 in 101 negative synthetic conversations, a 95% upper bound of about 3.0%. This is synthetic and mostly tuned data, and the review found false sales outside these sets, so **the < 3% target is not demonstrated**.
- **Usefulness:** human-rated next-action usefulness remains **unmeasured** (`null`).

### Remaining weaknesses

- **Offer classification uses keywords.**
  - Information objects outside the list, or offers without a send/receive verb (`ส่ง`, `รับ`, `แนบ`, `ดู`, `ขอ`), fall back to the older rules.
  - Only the three messages before a reply are considered.
- **Possibly too cautious.** `ราคา 5,000 บาท ตกลงไหม` → `ได้ครับ` is `possible_acceptance`, not a sale. `ไม่เอาแล้ว` after accepting photos is read as cancelling the deal.
- **Single appointment slot.** Completion reports are unverified and close every earlier attendance commitment. There is no multi-visit or multi-job model.
- **Inherited from v0.1.** Synthetic-only evaluation, regex coverage limits, uncalibrated confidence, one deal per conversation.

### Recommended next step

1. Freeze a fresh, independently authored evaluation set, ideally consented and anonymized real chats, before changing any rule.
2. Get human ratings of next-action usefulness on it.
3. Only then expand features or add an LLM extractor behind the existing `Extractor` protocol, held to the same evidence and acceptance gates.

---

# v0.1 self-audit (original release, kept for history)

Date: 2026-10-07. Repository: `boonsamnapat-netizen/Chat2work`, branch `claude/chat2work-core-v0-1-nvtlab`.

## 1. Starting point

- **Repository.** The GitHub repository existed but was empty: no refs, no history, no files, and no repository instructions. Nothing needed preserving or merging.
- **Candidate archive.** `Chat2work-v0.1.zip` was supplied as a candidate implementation:
  - 762 lines of Python;
  - 113 tests;
  - a 46-case synthetic set.

  Its own `SELF_AUDIT.md` says it could **not** be published: GitHub returned `403 Resource not accessible by integration`. So it had never run in CI.
- **How it was handled.** The archive was audited before import: every source, test, dataset, and workflow file was read. It was then copied into the empty repository. Nothing pre-existing was overwritten.

## 2. Reproduction of the candidate's claims

| Claim in archive | Reproduced (Python 3.13.16) |
| --- | --- |
| 113 tests pass | ✅ 113 passed |
| 100% on every benchmark metric, 0/40 false sales | ✅ identical to shipped `benchmark_results.json` |

That 100% came from a 46-case set written together with the rules. The denominators were tiny: 8 commitment events, 10 dates, 6 sales. It showed the rules fit their own examples, not that they generalize.

## 3. Blind holdout evaluation

### Holdout 1

A new 35-case holdout (`data/holdout.jsonl`) was written **before** running the engine on it. It uses longer, more natural multi-turn chats. Its first run, on the **unmodified candidate**, is recorded in `data/blind_first_runs.json`:

| Commitments F1 | Amounts F1 | Dates F1 | Pending F1 | Sale F1 | False sales |
| --- | --- | --- | --- | --- | --- |
| 0.909 | 0.986 | 0.914 | 0.769 | 0.727 | **1 / 29 (3.4%), target missed** |

### Holdout 2

After the holdout-1 fixes, a second 26-case holdout (`data/holdout2.jsonl`) was written. It deliberately uses phrasing the rules did not yet cover. Its first run:

| Commitments F1 | Amounts F1 | Dates F1 | Pending F1 | Sale F1 | False sales |
| --- | --- | --- | --- | --- | --- |
| **0.800** | 0.982 | **0.706** | 0.500 | 0.923 | 0 / 19 |

Both holdouts were then used for error analysis. Their current scores (100% / 98.2%) are therefore **no longer blind**. The first-run numbers above are the honest generalization estimate.

## 4. Defects found and fixed

Each item below has a regression test in `tests/test_regressions.py`.

### False confirmed sales

1. **A "yes" to an unrelated question counted as a sale.**
   - Case 1: the shop asked `ส่งแคตตาล็อกให้ดูไหมครับ` ("shall I send a catalog?") and the customer replied `เอาครับ`.
   - Case 2, found in free-form probing: the shop asked `รับน้ำเปล่าไหมครับ` ("want some water?") and the customer replied `เอาครับ`.
   - Fix: a bare yes to a shop yes/no question that has no purchase or price content is now `possible_acceptance` (0.60, needs review).
2. **Short agreements were silently ignored.** `ok ครับ` / `ตกลงครับ` / `ได้ครับ` after a price produced nothing. They now give `possible_acceptance` (0.70), which proposes `confirm_deal_status`. They are never treated as a sale.

### Money

3. **Times became prices.** `เดี๋ยวโอน 18:00` gave **18 baht**. Numbers glued to `:`, `/`, `-` or a decimal are now rejected.
4. **Phone numbers could become prices.** `โอน 0812345678` would have been read as a price. Numbers with a leading zero are now rejected.
5. **Thai substring trap.** The "budget" pattern `งบ` matched inside `ทั้งบ้าน` ("whole house"), so a shop price was labelled a customer budget and dropped from revenue.
6. **Missing roles.** Added unit-price roles (`เดือนละ`, `ผืนละ`, and others), totals written as `…รวม 39,800`, balances (`ส่วนที่เหลือ`, `ยอดค้างชำระ`), `฿`-prefixed amounts, and `18,500.-`.
7. **Bare reply prices.** `3,200 บาทครับ` was already handled. `3,200 ครับ` in direct reply to a price question is now accepted at medium confidence (0.82) only.

### Commitments, state, and negation

8. **Over-broad negation guard.** In `ไม่เกินพรุ่งนี้โอนให้` ("transfer no later than tomorrow"), the guard on `ไม่` (not) hid a real payment promise.
9. **"Probably" read as a promise.** `น่าจะ` (probably) contains `จะ` (will), so a hedge counted as a promise.
10. **"Not interested" counted as interest.** `ไม่สนใจ` was treated as interest. It is now `declined`, with no revenue.
11. **Rescheduling cancelled a deal.** `ยกเลิกนัด… เลื่อนเป็นวันศุกร์` ("cancel the appointment, move it to Friday") cancelled an accepted deal. It is now a `reschedule_request`.
12. **Change of mind was treated as cancellation.** `เปลี่ยนใจ` alone counted as a cancellation. It now gives `changed_needs_review`. A business cancellation now gives `cancellation_needs_review`.
13. **Same-message conflicts used signal order.** `แพงไป ไม่ซ่อมแล้ว` ("too expensive, not repairing anymore") came out as negotiating. A per-message priority now makes the firmer signal win (cancel > reject > pending/accept > negotiate > interest).
14. **Missed pending phrasings.** Added `ปรึกษา…ก่อน`, `ขอดู…ก่อน`, `ขอเช็ก…ก่อน`, `รอ…ก่อน`, `รออนุมัติ`, `แล้วจะทัก`, and `ดูอีกที`.
15. **Missed acceptance phrasings.** Added `ตกลงครับ ทำเลย`, `โอเคครับ ตกลงตามนี้`, `เอาเลยพี่`, and `เอาครับ ไม่ต้องลดแล้ว`. The candidate's own audit had listed `เอาเลยพี่` as a known miss.
16. **Football "นัด" became an appointment commitment.** `พรุ่งนี้มีอีกนัด` (a football fixture) in non-commercial chat became a business commitment. Appointments now require a commercial conversation.

### Dates

17. **Commercial context was cumulative.** A deadline in the first message, before any price keyword, was lost. Commercial context is now judged across the whole conversation.
18. **New date forms.** Added `15 ต.ค.`, `เสาร์นี้`, `บ่าย 2`, `2 ทุ่ม`, `10.30 น.`, and `เดือนหน้า`.
19. **No reference timestamp support.** Added optional `reference_date` / `--reference-date`. Only unambiguous forward dates resolve; everything else stays `null` with a reason. Past-context mentions (`ตั้งแต่วันจันทร์`) are never resolved forward.

### Actions and parsing

20. **Cancelled deals produced no action.** They now propose `confirm_cancellation`, so a human can release slots and handle deposits.
21. **New proposals.** Account-number requests now propose `provide_payment_details`. An explicit acceptance with no single price now flags `agreed_price` as missing.
22. **Parser coverage.** Added leading timestamps, tab-separated exports, `ลูกค้า (name):` labels, and explicit `--customer`/`--business` speaker mapping, with a conflict check.

### Evaluation

23. **Amount roles were not scored.** Gold amounts are now `[amount, role]` pairs and `amount_roles` is a separate metric. The 26 dev-set role labels were reviewed by hand.
24. **One evaluation test passed by accident.** The duplicate-amount test appended a bare string where the gold now holds pairs. It was rewritten, and a wrong-role test was added.

## 5. Final verification

All of the following ran locally on Python 3.13.16. CI repeats them on 3.11, 3.12, and 3.13.

- **Tests:** `python -m pytest -q` → **207 passed**.
- **Benchmark:** `python evaluate.py --check` → exit 0. All gates are met on dev, holdout, and holdout2 (see README table).
- **Remaining benchmark miss:** one, `h2_cctv_compare`. A competitor's bare price, `อีกร้านให้ 13,500`, is intentionally not extracted.
- **False confirmed sales:** 0 across 88 negative conversations. The 95% upper bound is about 3.4%, so the < 3% target is **not statistically demonstrated**.
- **CLI:** checked with a file, stdin, `--reference-date`, speaker flags, and `--compact`. The installed `chat2work` entry point and `python -m chat2work` both work.
- **README:** every behavioral claim was spot-checked against the engine.
- **Secrets and PII:**
  - No matches for token, API-key, AWS, or private-key patterns.
  - Phone-like numbers in tests were replaced with the placeholder `089-000-0000`.
  - Addresses are fictional.
  - This is a pattern scan, not a guarantee.
- **Complexity:**
  - Standard library only, no runtime dependencies.
  - Six core modules, about 750 lines.
  - No server, database, UI, integrations, or provider SDKs.

## 6. Not proven

- **Accuracy:** real-world accuracy is unknown, because all data is synthetic and hand-written by the same author as the rules.
- **Usefulness:** human-rated next-action usefulness (target ≥ 80%) is **not measured**. Reports carry `null`.
- **Confidence:** confidence values are hand-set heuristics, not calibrated probabilities.

## 7. Remaining weaknesses

- **Coverage:** regex coverage of Thai phrasing is the main limitation. The holdout2 first run shows commitment and date recall drop sharply on unseen wording.
- **Conservatism:** guards trade recall for safety. For example, `เอาครับ เดี๋ยวโอนก่อน` is not counted as a sale, because of `ก่อน`.
- **Scope:**
  - One deal per conversation.
  - No partial cancellation, refunds, multiple quotes for different jobs, or coreference.
  - Multi-line messages become `unknown`.
- **Money:** no spelled-out Thai numbers or `k`/`หมื่น` shorthand (deliberately produces nothing), no percent-deposit computation, THB only.
- **Dates:** no timezone handling; ambiguous expressions (`เสาร์หน้า`, `อาทิตย์หน้า`) are left unresolved by design.
- **Intent:** commercial intent is keyword-based.

## 8. Recommended v0.2 work

1. **Real data, collected properly.** Gather consented, anonymized real conversations and freeze a holdout *before* touching rules. Use a written human-rating rubric for next-action usefulness, and audit every confirmed sale.
2. **An LLM extractor adapter** behind the existing `Extractor` protocol (Claude, OpenAI, Gemini, Ollama). It should:
   - use strict JSON schemas;
   - pass the same evidence validation and acceptance gate;
   - be compared against the rules on the frozen holdout, ideally as an ensemble where the rules veto false sales.
3. **Confidence calibration** on labelled real data, plus a review and approval lifecycle (still without execution).
4. **Multi-opportunity tracking.** Handle several jobs or quotes in one chat, partial cancellation, revised quotes, and refunds.
5. **Per-message timestamps** from chat exports, with Asia/Bangkok timezone resolution, follow-up timing, and overdue detection.
6. **More Thai coverage:** spelled-out numbers, `k`/`หมื่น` shorthand with explicit confirmation, and a slang and misspelling corpus.
