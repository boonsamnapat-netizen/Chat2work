# Chat2Work Core: self-audit

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
