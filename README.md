# Chat2Work Core v0.1

**Thai-first conversation-to-action intelligence for small service businesses.**

> เกิดอะไรขึ้นในแชต ใครรับปากอะไร มีเงินเกี่ยวข้องตรงไหน และธุรกิจควรทำอะไรต่อ — พร้อมหลักฐานจากข้อความจริงทุกข้อ

Chat2Work reads a Thai customer–business chat (air-con, CCTV, electrical, repair, contractors, printing,
freelance design, agencies, solar, interior) and returns structured JSON. The JSON says:

- what happened,
- who promised what,
- where money may be involved,
- which information is still missing,
- which next actions to propose.

Every signal cites the exact source message.

It is an **intelligence engine, not a CRM or chatbot**:
- It never sends messages, never executes anything, and never stores conversations.
- Every recommended action is a *proposal* with `requires_human_approval: true`.
- v0.1 is a deterministic, rule-based Python baseline with **no runtime dependencies and no API keys**.

## Quick start

Requires Python ≥ 3.11.

```bash
git clone https://github.com/boonsamnapat-netizen/Chat2work.git
cd Chat2work
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'

chat2work data/example_conversation.txt                # or: python -m chat2work FILE
printf 'ลูกค้า: สนใจครับ\nร้าน: ราคา 18,500 บาท\nลูกค้า: ขอคิดดูก่อน\n' | chat2work
chat2work data/example_conversation.txt --reference-date 2026-10-07   # resolve unambiguous relative dates
chat2work chat.txt --customer "คุณบี" --business "พี่เอ"                # map extra speaker names
```

### CLI options

| Option | Effect |
| --- | --- |
| `FILE` / stdin | UTF-8 text, one message per line |
| `--reference-date YYYY-MM-DD` | the day the chat happened; without it every `resolved_date` stays `null` |
| `--customer NAME`, `--business NAME` | repeatable mapping of extra speaker labels to roles |
| `--compact` | single-line JSON |

### Python

```python
from datetime import date
from chat2work import analyze

result = analyze("ลูกค้า: ขอราคาหน่อยครับ\nร้าน: เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้",
                 reference_date=date(2026, 10, 7))
result.confirmed_sale          # False
result.to_dict()               # JSON-serialisable output
```

### Input format

One message per line, `Speaker: text`, for example:

```text
ลูกค้า: สนใจครับ
ร้าน: ราคา 9,500 บาท
```

The parser also accepts:
- an optional leading timestamp: `10:30 ลูกค้า: …` or `[10:30] …`;
- tab-separated chat exports: `time<TAB>speaker<TAB>text`;
- labels with a name in brackets: `ลูกค้า (คุณเอ): …`.

Built-in speaker labels:

| Role | Labels |
| --- | --- |
| customer | `ลูกค้า`, `ผู้ซื้อ`, `customer`, `client` |
| business | `ร้าน`, `ช่าง`, `บริษัท`, `ผู้ขาย`, `แอดมิน`, `business`, `seller`, `shop`, `admin` |

Any other speaker is `unknown`, unless you map it with `--customer` or `--business`. An unknown speaker is never guessed to be the customer:
- its signals are capped at confidence 0.65;
- it can never confirm a sale;
- it sets `review_required`.

A line without a speaker is also `unknown`. That includes the continuation line of a multi-line message.

## Example

`data/example_conversation.txt`:

```text
ลูกค้า: สนใจแอร์ Mitsubishi 18000 BTU 2 เครื่องครับ
ร้าน: ราคา 43,000 บาทรวมติดตั้ง
ลูกค้า: ถ้าได้อยากติดวันเสาร์
ร้าน: ได้ครับ เดี๋ยวล็อกคิวไว้ให้
```

Result (full JSON: [`data/example_analysis.json`](data/example_analysis.json)):

| Field | Value |
| --- | --- |
| `deal_status` | `interested` |
| `confirmed_sale` | `false`. Interest plus a reserved slot is not a sale. |
| `potential_revenue.amount` | `"43000"` THB, from the shop's quote. This is potential, not booked revenue. |
| money | `43,000` → `{"amount": "43000", "role": "price"}`. `18000 BTU` and `2 เครื่อง` are ignored. |
| dates | `วันเสาร์` kept raw. `resolved_date` is `null`, or `2026-10-10` with `--reference-date 2026-10-07`. |
| commitments | business `reserve_or_attend_appointment` (`เดี๋ยวล็อกคิวไว้ให้`) |
| missing information | `installation_address` and `appointment_time`, because an on-site job is being scheduled |
| proposed actions | `track_commitment`, `confirm_appointment`, `request_missing_information`, `follow_up_customer`, `add_to_revenue_radar` |

Each signal has the form:

```json
{
  "id": "s4", "type": "monetary_amount", "actor": "business",
  "value": {"amount": "43000", "currency": "THB", "role": "price", "raw": "43,000"},
  "confidence": 0.96, "confidence_level": "high",
  "evidence": {"message_id": 1, "speaker": "ร้าน", "text": "ราคา 43,000 บาทรวมติดตั้ง",
               "raw_line": "ร้าน: ราคา 43,000 บาทรวมติดตั้ง"},
  "metadata": {}
}
```

Each action has the form:

```json
{
  "type": "track_commitment",
  "description": "ตรวจติดตามสิ่งที่รับปากไว้ โดยยืนยันกับผู้รับผิดชอบก่อนดำเนินการ",
  "signal_ids": ["s9"], "evidence": [{"message_id": 3, "speaker": "ร้าน", "text": "ได้ครับ เดี๋ยวล็อกคิวไว้ให้", "raw_line": "…"}],
  "confidence": 0.93, "confidence_level": "high",
  "approval_status": "proposed", "requires_human_approval": true
}
```

`message_id` starts at 0. Signal IDs are only unique within one analysis.

## Output schema (v0.1)

| Field | Meaning |
| --- | --- |
| `signals[]` | `id`, `type`, `actor` (`customer`/`business`/`unknown`), normalized `value`, `confidence`, `confidence_level`, `evidence` (exact source message + `message_id`), `metadata` |
| `commercial_intent`, `customer_interest` | conversation contains commercial discussion / customer interest at any point |
| `decision_pending`, `confirmed_sale`, `deal_status` | **current** state after the latest customer signal |
| `status_signal_ids` | signals that justify the current state |
| `potential_revenue` | `{amount, currency, signal_ids, confidence, reason}`; `amount` is a decimal string or `null` |
| `missing_information[]` | contextual missing fields, as signals with evidence of why they are needed |
| `recommended_actions[]` | proposals, each referencing `signal_ids` and `evidence` |
| `review_required`, `warnings[]` | review flags (unknown speakers, unresolved dates, multiple price options, unverified payment, uncertain deal state, any signal < 0.80) |
| `reference_date`, `provider`, `schema_version` | provenance |

Signal types emitted by the Thai rules:
`commercial_intent`, `customer_interest`, `quotation_request`, `negotiation`, `decision_pending`,
`customer_acceptance`, `possible_acceptance`, `customer_rejection`, `cancellation`, `change_of_mind`,
`business_cancellation`, `reschedule_request`, `business_commitment` (`send_quotation`,
`reserve_or_attend_appointment`), `customer_commitment` (`make_payment`, `pay_deposit`,
`attend_appointment`), `quotation_sent`, `appointment`, `payment_signal` (incl. `account_number_request`),
`payment_pending`, `payment_reported` (`verified: false`), `monetary_amount`, `deadline`, `schedule`,
`temporal_mention`, and derived `missing_information`.

`deal_status` is one of:

| Group | Values |
| --- | --- |
| no deal yet | `non_commercial`, `inquiry`, `interested` |
| undecided | `decision_pending`, `negotiating` |
| outcome | `accepted`, `cancelled`, `declined` |
| needs a human to check | `possible_acceptance`, `acceptance_needs_review`, `changed_needs_review`, `cancellation_needs_review` |

## Sales safety (no false confirmed sales)

The following **never** produce `confirmed_sale: true`:

| Case | Examples |
| --- | --- |
| interest | `สนใจครับ`, `น่าสนใจ` |
| price request or negotiation | `ขอราคาหน่อย`, `ลดได้ไหม` |
| decision pending | `ขอคิดดูก่อน`, `ถามแฟนก่อน`, `ขอปรึกษาที่บ้านก่อน`, `รอเงินเดือนออกก่อน` |
| will get back | `เดี๋ยวติดต่อกลับ` |
| appointments, reserved slots, quotation promises | `วันเสาร์ว่างไหม` |
| account-number request | `ขอเลขบัญชีหน่อย` |
| payment promise | `เดี๋ยวเย็นนี้โอน` |
| reported payment | `โอนแล้วครับ` is unverified |

A sale requires an **explicit acceptance from the customer speaker** with confidence ≥ 0.90. Examples:
`เอาครับ`, `ตกลงครับ เอาตัวนี้`, `เอาตัวนี้แหละพี่`, `ยืนยันตามราคานี้ครับ`, `ตกลงจ้างครับ`, `ตกลงครับ ทำเลย`, `เอาเลยพี่`.
The rules guard these conservatively:

- **Questions, conditions, hedges** (`เอาตัวนี้ได้ไหม`, `ถ้าสินเชื่อผ่านเอาเลย`, `น่าจะเอานะ แต่…`):
  not acceptance.
- **Quoted or reported speech** (`ภรรยาบอกว่าเอาครับ`, `"ตกลงครับ เอาตัวนี้" คือประโยคที่…`):
  not acceptance. The acceptance phrase must open the customer's own message.
- **Short agreement after a price** (`ok ครับ`, `ตกลงครับ`, `ได้ครับ`): `possible_acceptance`, confidence 0.70.
  This needs review and proposes `confirm_deal_status`.
- **Yes to an unrelated question.** If the shop asks a yes/no question that is not about buying
  (`ส่งแคตตาล็อกให้ดูไหม`, `รับน้ำไหม`), a bare `เอาครับ` answers that question. It is not treated as a sale.
- **Later messages change the current state.** Examples:
  - cancellation (`ขอยกเลิกออเดอร์`, `ไม่ซ่อมแล้ว`);
  - rejection (`ไม่เอาครับ`, `ไม่สนใจ`);
  - renewed pending (`ขอคิดใหม่`);
  - change of mind (`เปลี่ยนใจ…`): needs review;
  - a business cancellation: needs review.

  The earlier acceptance evidence is kept.
- **Not treated as cancellation:** rescheduling (`ยกเลิกนัด…เลื่อนเป็นวันศุกร์`), a question about
  cancelling (`ยกเลิกได้ไหม`), a conditional (`ถ้า…ขอยกเลิกได้นะ`), or a negation (`ไม่ยกเลิก`).
- **Who said it.** Business statements (`ลูกค้าตกลงซื้อแล้ว`, `ล็อกคิวไว้ให้แล้ว`) and unknown speakers can never confirm a sale.
  An unknown speaker after an acceptance moves the deal to `acceptance_needs_review`.
- **Same message, conflicting signals:** the firmer one wins. For example, `แพงไป ไม่ซ่อมแล้ว` is a cancellation, not a negotiation.

## Confidence

| Confidence | `confidence_level` |
| --- | --- |
| ≥ 0.90 | `high` |
| 0.80 – < 0.90 | `medium` |
| < 0.80 | `needs_review` |

**Rule confidence is a hand-set heuristic, not a calibrated probability.** It ranks how specific a pattern is. It does not tell you how often that pattern is right on real chats.

All actions are proposals that require human approval. Execution is outside v0.1. The intended path is:

> suggest → evidence → confidence → human approve → (future) execute

## Money

Amounts are decimal **strings**, never floats. Each amount carries a role:

| Role | Example |
| --- | --- |
| `price` | `ราคา 18,500 บาท` |
| `total` | `ยอดรวม`, `ราคารวม`, `…รวม 3,000` |
| `deposit` | `มัดจำ 5,000` |
| `budget` | `งบไม่เกิน 45000` (customer) |
| `unit_price` | `ตัวละ`, `เดือนละ`, `ผืนละ`, `บาท/เครื่อง` |
| `balance` | `ส่วนที่เหลือ`, `ยอดค้างชำระ` |
| `previous_price` | `ราคาเดิม` |
| `discount` | `ส่วนลด`, `ลด 500` |
| `payment` | `โอน 5,000 บาท` |

**Supported formats:**
- `18,500`, `18500`, `43,000 บาท`, `45000 บาท`, `฿185,000`, `18,500.-`, `1,850.50 บาท`, Thai digits `๑๘,๕๐๐`.
- A number needs a price keyword, a currency marker, or a business reply to a direct price question (`3,200 ครับ`).
  The last case gets confidence 0.82 (medium).

**Never treated as money:**

| Category | Examples |
| --- | --- |
| quantities and specs | `18000 BTU`, `2 เครื่อง`, `550 วัตต์`, `5kW`, `120 แกรม`, `ส่วนลด 10%` |
| times and dates | `18:00`, `18/5`, `15 ต.ค.`, `2 ทุ่ม` |
| identifiers | phone numbers (`089-000-0000`, anything with a leading zero), account or order numbers |
| unsupported shorthand | `18.5k`, `2 หมื่น`, `1.8 ล้าน`. These produce **no amount**; they are never silently turned into 18.5. |

**Potential revenue:**
- It is the most recent unambiguous **business** price or total, and an explicit total wins over component prices.
- Deposits are never added to the total, and unit prices are never multiplied by quantity.
- A customer budget or price question is not revenue.
- Several price options give `null` plus a review warning.
- A cancellation or decline gives `null`.

## Dates and times

Relative expressions are always preserved as `raw`:
- days: `พรุ่งนี้`, `วันเสาร์`, `เสาร์นี้`;
- parts of today: `เย็นนี้`, `บ่ายนี้`;
- weeks and months: `อาทิตย์หน้า`, `เดือนหน้า`, `สิ้นเดือน`;
- absolute dates: `15 ต.ค.`, `18/10/2569`;
- times: `10:00`, `10.30 น.`, `บ่าย 2`, `2 ทุ่ม`, `9 โมง`.

- **Without `--reference-date`, `resolved_date` is always `null`.**
- **With a reference date, only unambiguous forward-looking dates resolve.** Examples: `วันนี้`, `พรุ่งนี้`, `มะรืนนี้`, `เย็นนี้`,
  a bare weekday that isn't today, `15 ต.ค.` on or after the reference, `18/10/2569` (Buddhist Era converted).
- Each unresolved date carries a `resolution` reason:

  | Reason | Applies to |
  | --- | --- |
  | `ambiguous` | `เสาร์หน้า`, the reference day's own weekday, a past day-month without a year |
  | `unsupported_or_range` | `อาทิตย์หน้า`, `สิ้นเดือน` |
  | `time_only` | a time with no date |
  | `invalid_date` | an impossible date |
  | `not_resolved_context_may_be_past` | plain temporal mentions such as `ตั้งแต่วันจันทร์` |

- The engine never infers that something is overdue.

Date signals are typed by context:

| Type | When |
| --- | --- |
| `deadline` | promise, payment, `ภายใน`, `ก่อน`, `ไม่เกิน`, `ทัน` |
| `schedule` | other dates in a commercial conversation |
| `temporal_mention` | non-commercial chat, or past references |

## Contextual missing information

Missing information is asked for only when the context needs it:

- `installation_address` and `appointment_time` appear only when **on-site work is being arranged**.
  That covers an install, repair visit, or site survey with a date, queue, or appointment.
  Discussing an installation-inclusive price or asking `รวมติดตั้งหรือยัง` doesn't trigger them.
- `agreed_price` appears only when the customer explicitly accepted and no single business price exists.
- "Missing" means *not found in the supplied messages*, not that the business lacks it.

## Architecture

```text
chat2work/
  models.py              Message / Signal / Evidence / Action / Opportunity / Analysis + Extractor Protocol
  parsing.py             speaker labels, timestamps, speaker mapping; raw lines preserved
  extractors/
    rules.py             Thai semantic signals (deterministic, no I/O)
    money.py             explicit THB amounts with roles
    dates.py             Thai date/time expressions + reference-date resolution
  engine.py              validate provider output → deal state → revenue → missing info → proposed actions
  cli.py                 UTF-8 file/stdin → JSON
  evaluation/harness.py  precision/recall/F1 against hand-written labels
evaluate.py              runs all datasets; --check enforces gates
data/                    synthetic datasets, results, example
tests/                   pytest suites (engine, regressions, evaluation)
```

**Provider independence.** A future OpenAI, Gemini, Claude, or Ollama adapter only needs:
- a `name`;
- `extract(messages) -> list[Signal]`.

It is passed in as `analyze(text, extractor=MyAdapter())`. The core then:

1. **Validates** what the adapter returns before using it:
   - signal IDs are unique;
   - every signal's evidence equals its source message exactly;
   - `actor` matches the message's speaker;
   - confidence is finite and within 0–1;
   - unknown speakers stay below 0.80;
   - acceptance comes from the customer with confidence ≥ 0.90.

   Anything else raises `ValueError`.
2. Derives deal state, revenue, missing information, and actions itself.

So adapters can't inject ungrounded actions, and they can't confirm a sale on their own authority. No adapter or network code ships in v0.1.

## Tests and benchmark

```bash
python -m pytest -q                     # 207 tests
python evaluate.py                      # JSON report for all datasets
python evaluate.py --check              # exit 1 if any technical gate is unmet
python evaluate.py --dataset data/holdout2.jsonl --output report.json
```

GitHub Actions (`.github/workflows/ci.yml`) runs on Python 3.11, 3.12, and 3.13. Each run does the tests, the gated benchmark, and a sample CLI analysis, and uploads the JSON reports as artifacts.

### Datasets

107 hand-written **synthetic** conversations across 10 industries plus non-commercial chat. Every case is labelled `synthetic: true`.

| File | Cases | How it was written | Blind? |
| --- | --- | --- | --- |
| `data/conversations.jsonl` (dev) | 46 | written together with the original rules (mostly 1–3 turns) | no, in-sample |
| `data/holdout.jsonl` | 35 | written before running the engine on it; longer, more natural turns | first run only |
| `data/holdout2.jsonl` | 26 | written after holdout-1 fixes, deliberately using phrasing the rules did not yet cover | first run only |

Gold labels per case:
- `commercial_intent`, `decision_pending`, `confirmed_sale`;
- `amounts` as `[amount, role]` pairs;
- `dates` as raw deadline/schedule expressions;
- `commitments` as `[type, actor, value]`;
- `potential_revenue`.

Scenarios covered:
- interest, inquiry, negotiation, pending decisions;
- acceptance (explicit, casual, conditional, reported);
- deposit promises, missed and reported payments;
- quotation promises and sent quotations, vague appointments and rescheduling;
- multiple amounts, total + deposit + balance, unit prices, quantity/time/phone traps;
- cancellation and change of mind;
- prompt-injection text, unknown speakers, timestamped exports, non-commercial chat.

### How metrics are computed

| Metric | Definition / denominator |
| --- | --- |
| Commitments | micro P/R/F1 over unique `(type, actor, value)` per conversation, detection only; a fulfilled promise still counts as detected |
| Amounts | micro P/R/F1 over the multiset of extracted amount values |
| Amount roles | same, but `(amount, role)` must both match |
| Dates | micro P/R/F1 over raw `deadline` + `schedule` expressions; resolution is tested separately in unit tests |
| Commercial intent, decision pending, confirmed sale | per-conversation boolean P/R/F1 |
| False confirmed-sale rate | conversations with `confirmed_sale: true` predicted ÷ conversations labelled not a sale |

### Results

These were measured locally on Python 3.13.16 and are reproduced by CI. Current results ([`data/benchmark_results.json`](data/benchmark_results.json)):

| Metric (target) | dev, 46 cases | holdout, 35 | holdout2, 26 |
| --- | --- | --- | --- |
| Commitments F1 (≥ 0.90) | 1.000 (8 events) | 1.000 (12) | 1.000 (5) |
| Amounts F1 (≥ 0.95) | 1.000 (31) | 1.000 (34) | 0.982 (P 1.00, R 0.96; 28 gold) |
| Amount roles F1 | 1.000 | 1.000 | 0.982 |
| Dates F1 (≥ 0.90) | 1.000 (10) | 1.000 (18) | 1.000 (11) |
| Commercial intent F1 | 1.000 (44 pos.) | 1.000 (33) | 1.000 (25) |
| Decision pending F1 | 1.000 (10 pos.) | 1.000 (8) | 1.000 (5) |
| Confirmed sale F1 | 1.000 (6 pos.) | 1.000 (6) | 1.000 (7) |
| False confirmed-sale rate (< 3%) | 0 / 40 | 0 / 29 | 0 / 19 |

**These current numbers are not blind.** The rules were changed after studying the errors on both holdouts. The more honest estimate is the **first run on each holdout, before any fix it informed** ([`data/blind_first_runs.json`](data/blind_first_runs.json)):

| First blind run | Commitments F1 | Amounts F1 | Dates F1 | Pending F1 | Sale F1 | False sales |
| --- | --- | --- | --- | --- | --- | --- |
| holdout (unmodified candidate engine) | 0.909 | 0.986 | 0.914 | 0.769 | 0.727 | **1 / 29 (3.4%)** |
| holdout2 (after holdout-1 fixes) | **0.800** | 0.982 | **0.706** | 0.500 | 0.923 | 0 / 19 |

On holdout2's first run, commitment and date detection **missed the targets** on phrasing the rules hadn't seen. Expect similar drops on real chats.

Across all three sets, 0 false confirmed sales were found in 88 negative conversations. With 88 negatives, the 95% upper bound on the true rate is about 3.4% (rule of three). So **this sample cannot prove the < 3% target** even on synthetic data.

**Human-rated next-action usefulness (target ≥ 80%) has not been measured.** It is `null` in every report, and no claim is made about it.

## Limitations

- **Synthetic, small, and Thai-rule-specific.** Small samples (5–12 commitment events per set). The real-world accuracy is unknown.
- **Pattern coverage.** Regex rules miss unseen phrasing, slang, misspellings, sarcasm, dialects, and emoji-only replies.
  Commercial intent is keyword-based. Conservative guards (any `ไม่`, `ยัง`, `ก่อน`, or question in an acceptance message) trade recall for safety. For example, `เอาครับ เดี๋ยวโอนก่อน` is not counted as a sale.
- **Money.**
  - Unlabelled bare numbers are ignored unless they answer a price question. For example, a competitor price `อีกร้านให้ 13,500` is missed.
  - Spelled-out Thai numbers (`หมื่นแปดห้า`) and `k`/`หมื่น` shorthand produce no amount.
  - Only THB is supported.
  - Percent deposits (`มัดจำ 50%`) are not converted.
- **One deal per conversation.** No multi-job, multi-customer, partial-cancellation, refund, or coreference handling.
  Multi-line messages without a speaker on each line become `unknown`.
- **Dates.**
  - No timezone handling.
  - `อาทิตย์หน้า` and `เสาร์หน้า` are deliberately left unresolved.
  - No follow-up timing or inactivity inference.
- **Validation scope.** Evidence validation proves traceability, not that the interpretation is correct.

## Privacy

- **Never commit real customer conversations, personal data, credentials, or API keys.**
  - All benchmark text is invented. Addresses are fictional, and the phone number is the placeholder `089-000-0000`.
  - Keep local conversations in the git-ignored `local-conversations/` directory or outside the repository.
- The core makes no network calls, has no telemetry, and writes nothing to disk. But its output repeats the source text inside `evidence`,
  so treat output, logs, and CI artifacts as containing whatever personal data you feed in. Do not send real chats through CI.
- If you contribute real data, it must be consented and anonymized first.

## Contributing

1. Add a failing regression test first, especially for any false confirmed sale, then fix the rule.
2. Don't invent amounts or dates, and never weaken an evidence or safety check to make a test pass.
3. Keep synthetic and real-world results separate. Report blind numbers from a fresh holdout before tuning on it.
4. Update this README and `data/benchmark_results.json` (`python evaluate.py --output data/benchmark_results.json`) when behavior changes.
5. Out of scope for the core: UI, CRM, chat integrations, auth, invoices, payments, databases, billing, autonomous replies.

See [SELF_AUDIT.md](SELF_AUDIT.md) for the audit log and the recommended v0.2 work.

## License

MIT. See [LICENSE](LICENSE).
