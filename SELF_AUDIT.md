# Chat2Work Core v0.1: self-audit

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
