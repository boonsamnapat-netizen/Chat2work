# Chat2Work Core v0.1.3

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

## Output schema (v0.1; v0.1.1–v0.1.3 only add signal/action types, money roles and metadata)

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

| Area | Types |
| --- | --- |
| deal state | `commercial_intent`, `customer_interest`, `negotiation`, `decision_pending`, `customer_acceptance`, `possible_acceptance`, `customer_rejection`, `cancellation`, `reported_cancellation` (someone else's words; needs review), `change_of_mind`, `business_cancellation` |
| information | `information_offer` (business offers a catalog, photos, sample, spec, link or quotation, as a question or a statement such as `ส่งแคตตาล็อกให้ครับ`), `information_accepted` (customer accepts that offer; never a purchase; may carry `deferred: true`), `information_requested` (customer asks for it now; a go-ahead), `information_declined`, `information_sent` |
| quotations and prices | `price_enquiry` (customer asks a price), `quotation_request` (customer asks for a quotation **document**), `quotation_question` (asks *about* one), `quotation_declined`, `quotation_sent` (business sent the **document**), `quotation_received` (customer), `price_sent` (a price given in chat) |
| commitments | `business_commitment` (`send_quotation`, `reserve_or_attend_appointment`), `customer_commitment` (`make_payment`, `pay_deposit`, `attend_appointment`; payment ones may carry `amount` and `purpose: "remaining_balance"`) |
| appointments | `appointment`, `reschedule_request` (`reschedule_appointment` or `cancel_appointment_slot`, from either side), `appointment_completed` (asserted report, `verified: false`), `completion_uncertain` (hedged or asked: `เสร็จแล้วมั้ง`) |
| payments | `payment_signal` (incl. `account_number_request`), `payment_pending`, `payment_reported` (`verified: false`, optional `reported_amount`), `payment_reschedule_request` (moves a payment, never the appointment) |
| other reschedules | `deliverable_reschedule_request` (moves photos, a catalog or a quotation; never the appointment) |
| money and dates | `monetary_amount`, `deadline`, `schedule`, `temporal_mention` |
| derived | `missing_information` |

Signals that belong to a superseded appointment slot keep their evidence but carry
`metadata.slot_status: "superseded"` and `superseded_by` (the reschedule signal). Dates inside a reschedule message
are marked `superseded` (before `เลื่อน…`) or `replacement` (after it).

Proposed action types:

| Area | Actions |
| --- | --- |
| quotations and prices | `send_quotation`, `answer_price_enquiry` |
| information | `send_offered_information`, `await_customer_go_ahead` (the customer said not to send yet) |
| commitments and payments | `track_commitment`, `check_payment`, `provide_payment_details`, `confirm_payment_schedule` |
| appointments | `confirm_appointment`, `verify_completion` (completion was hedged or asked) |
| follow-up | `request_missing_information`, `follow_up_customer`, `schedule_follow_up`, `add_to_revenue_radar` |
| deal state | `confirm_deal_status`, `confirm_cancellation` |

`deal_status` is one of:

| Group | Values |
| --- | --- |
| no deal yet | `non_commercial`, `inquiry`, `interested` |
| undecided | `decision_pending`, `negotiating` |
| outcome | `accepted`, `cancelled`, `declined` |
| needs a human to check | `possible_acceptance`, `acceptance_needs_review`, `changed_needs_review`, `cancellation_needs_review` |

## Event classification (v0.1.3)

Before the rules change a deal state, close an obligation, supersede a slot or pick a revenue value,
they classify the event in a small explicit layer ([`chat2work/extractors/semantics.py`](chat2work/extractors/semantics.py)):

1. **Clauses.** A message is split at spaces and clause-starting conjunctions (`แต่`, `และ`, `ที่เหลือ`).
   Latin words, numbers, amounts and particles (`PDF`, `1000`, `บาท`, `ให้`, `ทาง`, `นะ`, `ครับ`) stay in the clause.
2. **Status of the event's clause.** One of these:

   | Status | Example |
   | --- | --- |
   | `asserted` | the plain statement |
   | `negated` | `ยังไม่ได้ส่ง` |
   | `conditional` | `ถ้า…`, `พอ…`, `หลังจาก…`, or the clause after `แต่ถ้า…` |
   | `future` | `พรุ่งนี้จะส่ง…` |
   | `questioned` | `ส่งแล้วใช่ไหม`, `หรือยัง`; polite `…ได้ไหม` requests still count as requests |
   | `reported` | `เพื่อนบอกว่า…` |
   | `uncertain` | `มั้ง`, `น่าจะ`, `คิดว่า`, `ไม่แน่ใจ` |

3. **Target.** The object after the event word: purchase, document, information, payment or appointment.

Only an **asserted, completed** event closes something:
- delivered documents and information;
- received quotations;
- reported payments, using `แล้ว` or the colloquial clause-final `ละ`;
- completed work.

Decisions, i.e. refusal and cancellation, are read per clause after courtesy and pronouns (`ขอโทษครับ ไม่จ้างครับ`, `ผมไม่ซื้อครับ`). An unrelated `แล้ว` elsewhere in the message no longer suppresses them.
The layer is a heuristic for Thai chat, not a parser.

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
- **What is being accepted.** A generic yes (`เอาครับ`, `ได้ครับ`, `ตกลงครับ`, `ส่งมาเลย`, or longer forms
  such as `เอาครับ ส่งมาเลย`) is read against the shop's latest open offer. That offer can be
  up to three messages back, as long as the customer hasn't already answered it. An offer doesn't have to be a question:
  `ส่งแคตตาล็อกให้ได้นะครับ` and `เดี๋ยวส่งรูปแอร์ให้ดูครับ` offer information too. A delivered item (`ส่ง…ให้แล้ว`) is history, not an open offer.
  The offer is classified by what it offers:

  | Shop offers | Example | Customer's yes becomes |
  | --- | --- | --- |
  | information | `รับแคตตาล็อกพร้อมราคาไหม`, `ส่งรูปแอร์ 18000 BTU ให้ดูไหม`, `ราคา 18,500 บาท ให้ส่งใบเสนอราคาให้ไหม`, `เดี๋ยวส่งรูปให้ดูครับ` | `information_accepted`, never a sale. An accepted quotation offer also becomes a `quotation_request`. |
  | purchase | `เอาตัวนี้ราคา 18,500 บาทไหม`, `สั่งเลยไหม`, `ราคา 9,000 บาท รับไหม` | acceptance (same guards as below) |
  | both | `จะเอาตัวนี้เลยไหม หรือให้ส่งรูปให้ดูก่อน`, `ราคา 18,500 บาท เดี๋ยวส่งรูปให้ดูครับ`, `ส่งรูปให้ดู ถ้าโอเคก็สั่งได้เลย` | `possible_acceptance` (0.60, needs review) |
  | scheduling | `นัดดูหน้างานวันเสาร์สะดวกไหม` | no acceptance signal; appointment signals cover it |
  | something else | `รับน้ำไหม`, `โทรคุยได้ไหม` | `possible_acceptance` (0.60, needs review) |

  A price, quantity or specification inside the question does **not** make it a purchase question.
  A reply that names the purchase itself (`ยืนยันตามราคานี้`, `ยืนยันซ่อมตามราคานี้`, `ตกลงซื้อ`) is acceptance whatever was asked.
  A reply that picks a product after an information offer (`ไม่ต้องครับ เอาตัวนี้เลย`) gets `possible_acceptance`.
  So does a reply that mixes yes with a document request (`เอาครับ แต่ส่งใบเสนอราคามาด้วย`).
  - **Declining** offered information (`ไม่เอาครับ` to `ส่งแคตตาล็อกให้ดูไหม`, or `ไม่เอาแคตตาล็อก ตกลงซื้อเลย`) is not a deal rejection.
    An explicit transaction refusal (`ไม่ซื้อ`, `ไม่จ้าง`, `ไม่ตกลง`) always is, whatever the shop just offered. Refusing *competitors* (`ไม่ซื้อที่อื่น`) is not.
  - **Deferral** (`เอาครับ แต่ยังไม่ต้องส่ง`) keeps the acceptance with `deferred: true`. It proposes `await_customer_go_ahead` instead of send-now; a later explicit request reopens sending.
- **Later messages change the current state.** Examples:
  - cancellation (`ขอยกเลิกออเดอร์`, `ไม่ซ่อมแล้ว`);
  - rejection (`ไม่เอาครับ`, `ไม่สนใจ`);
  - renewed pending (`ขอคิดใหม่`);
  - change of mind (`เปลี่ยนใจ…`): needs review;
  - **someone else's** rejection (`เพื่อนบอกว่าไม่เอาแล้ว`): `reported_cancellation`, needs review, never a cancellation.
    If the customer reaffirms (`…แต่ผมยังเอาตามเดิม`), nothing changes. First-person `ผมบอกว่าไม่เอาแล้ว` is the customer's own cancellation.
  - a business cancellation: needs review.

  The earlier acceptance evidence is kept.
- **Not treated as cancellation:** rescheduling (`ยกเลิกนัด…เลื่อนเป็นวันศุกร์`) or `เวลาเดี๋ยวแจ้งอีกที` about the new time, a question about
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
| `discount` | `ส่วนลด`, `ลด 500`, `ลดให้ 1,500` (`ลดให้เหลือ 17,000` is the revised net **price**) |
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
| identifiers | phone numbers (`089-000-0000`, `+66 89 000 0000`, `+66890000000`, anything with a leading zero), any unseparated run of 9+ digits, LINE IDs, account/order/model numbers right after their label (`รุ่นนี้ 18,500 บาท` is still a price) |
| unsupported shorthand | `18.5k`, `2 หมื่น`, `1.8 ล้าน`. These produce **no amount**; they are never silently turned into 18.5. |

**Amounts that are not a selling price** keep their evidence but are never revenue:

| Role | Example |
| --- | --- |
| `gift_value` | `แถมขาแขวนมูลค่า 500 บาท` |
| `included_component` | `ค่าแรง 1500 บาทรวมอยู่ในราคาแล้ว`, `รวมค่าแรงไว้แล้ว 1500 บาท` (but `ราคานี้รวมค่าแรงแล้ว 18,500 บาท` is the total) |
| `expense` | `จ่ายค่าอะไหล่ 1500 บาท` said by the shop (said by the customer, it is a `payment`) |

A budget needs a real budget word: `งบ` at a word start or after `มี`/`ใช้`/`ตั้ง`/`ใน`/`ได้`. So `ช่างบอกราคา 18,500 บาท` and `ทั้งบ้าน 22,000 บาท` are prices.
A bare number counts as a price only when the shop's whole reply is price-shaped (`3,200 ครับ`, `ประมาณ 3,200 ค่ะ`) and answers a price question. A phone number in that reply is not a price.

**Potential revenue:**
- It is the most recent unambiguous **business** price or total, and an explicit total wins over component prices.
- An explicit total from an earlier message is kept when a later separate message gives a plain price without revision wording
  (`ราคาใหม่`, `ลดเหลือ`, `ปรับ…`), so splitting one quote into chat bubbles doesn't change the value. Such cases get the warning
  `later_price_relation_unclear` for review.
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
- After a reschedule (by either side), only the **latest arrangement** counts.
  - The earlier slot, its times, and its attendance commitments stay in `signals` but are marked `superseded`.
  - `appointment_time` is requested again unless a time is given in or after the reschedule message.
    For example, `ยกเลิกนัดวันเสาร์ เลื่อนเป็นวันศุกร์แทน แต่ยังไม่ทราบเวลา` requests a new time; the old `09:00` does not count.
  - A reschedule never cancels the deal.
- `agreed_price` appears only when the customer explicitly accepted and no single business price exists.

## Commitment and request lifecycle

Each open item closes only on evidence about that same item:

| Open item | Closed by |
| --- | --- |
| quotation request / document promise | `quotation_sent` (the business says the **document** was sent) or `quotation_received` after it, or `quotation_declined`. A price typed or "sent" in chat (`ส่งราคาให้แล้ว 18,500 บาท`) is `price_sent` and does **not** close it. A later new request reopens it. |
| price promise (`เดี๋ยวส่งราคาให้`) | `price_sent` or a delivered quotation |
| price enquiry | a business amount, `price_sent`, or a delivered quotation after it |
| payment commitment | a later **asserted** `payment_reported` (`ถ้าโอนแล้วจะส่งสลิป` is not one). Reported payment is still unverified, so `check_payment` stays proposed. A **partial** report (`โอนแล้ว 1000 บาท` against a 5,000 promise) keeps the commitment open with the warning `partial_payment_reported`. A stated remainder (`ที่เหลืออีก 4000 จะโอนพรุ่งนี้`) becomes its own open commitment, with its amount, deadline and the original purpose. |
| deferred quotation / information | a deferral (`เอาครับ แต่ยังไม่ต้องส่ง`, also inside the request itself) puts the promise or request on hold. That gives `await_customer_go_ahead` with the promise as evidence, and no send-now or follow-up-date proposal. A later go-ahead (`ส่ง…มาได้แล้ว`, `ขอ…ตอนนี้เลย`) reopens the send action. |
| attendance / visit commitment | a later **asserted** `appointment_completed`, or a reschedule that supersedes its slot. A payment report never closes it. Conditional, future, hedged, negated or questioned completion (`ถ้าติดตั้งเสร็จแล้วจะโทรแจ้ง`, `พอทำเสร็จแล้ว…`, `น่าจะเสร็จแล้ว`, `เสร็จหรือยัง`) does not. |
| payment timing | a payment reschedule (`ขอเลื่อนโอนมัดจำไปวันศุกร์`, `ขอเลื่อนวันที่โอนมัดจำ…`) proposes `confirm_payment_schedule`. It never supersedes the appointment, even when both are moved in one message. Moving photos, a catalog or a quotation (`ขอเลื่อนส่งรูป…`, `ขอเลื่อนวันส่งใบเสนอราคา…`) is a `deliverable_reschedule_request` and leaves the installation untouched. |
| uncertain completion | `completion_uncertain` keeps the commitment tracked and proposes `verify_completion` |
| cancelled document | `ยกเลิกใบเสนอราคา…` withdraws the quotation request (`quotation_declined`), not the purchase |
| accepted information offer | a later `information_sent` |

A customer request alone never creates a business promise. For example, `send_quotation` triggered by a request says so in its description.
Questions about a quotation (`ใบเสนอราคามีอายุกี่วัน`) and receipt reports (`ได้รับใบเสนอราคาแล้ว`) are not requests. A receipt report never counts as agreeing to buy.
An address withdrawn later (`ที่อยู่เมื่อกี้ผิด`, `ขอเปลี่ยนที่อยู่`) no longer counts as provided, so `installation_address` is requested again.

**Final-output checks.** Validation runs again on the finished output, including nodes the core derives itself:
- signal IDs are unique (core-generated IDs never collide with an adapter's);
- every action references existing signals;
- evidence matches its source message exactly;
- derived signals never exceed their source's confidence or the 0.65 unknown-speaker ceiling.
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
python -m pytest -q                     # 538 tests
python evaluate.py                      # JSON report: five label splits + the action-scenario set
python evaluate.py --check              # exit 1 if any technical gate is unmet
python evaluate.py --dataset data/holdout2.jsonl --output report.json
```

`evaluate.py` exits 2 with a message on stderr, and evaluates nothing, in these cases:
- an explicitly selected dataset is missing or empty;
- a required default split in `--data-dir` is missing;
- the same dataset is selected twice.

A missing split is never skipped silently.

GitHub Actions (`.github/workflows/ci.yml`) runs on Python 3.11, 3.12, and 3.13. Each run does the tests, the gated benchmark, and a sample CLI analysis, and uploads the JSON reports as artifacts.

### Datasets

171 hand-written **synthetic** conversations (147 label cases + 24 action scenarios) across 10 industries plus non-commercial chat. Every case is labelled `synthetic: true`.

| File | Cases | How it was written | Blind? |
| --- | --- | --- | --- |
| `data/conversations.jsonl` (dev) | 46 | written together with the original rules (mostly 1–3 turns) | no, in-sample |
| `data/holdout.jsonl` | 35 | written before running the engine on it; longer, more natural turns | first run only |
| `data/holdout2.jsonl` | 26 | written after holdout-1 fixes, deliberately using phrasing the rules did not yet cover | first run only |
| `data/holdout3.jsonl` | 20 | written for v0.1.1 after the five review fixes; labels frozen (SHA-256 in `blind_first_runs.json`) before the first run; targets informational vs purchase acceptance, quotations, payments + visits, rescheduling | first run only |

| `data/holdout4.jsonl` | 20 | written for v0.1.2 after the expanded-review fixes; labels frozen before the first run; targets statement offers, explicit vs reported rejection, quotation speech acts, asserted completion, payment vs appointment rescheduling, phone/gift/expense/budget money traps, short years, address changes | first run only |

| `data/action_scenarios.jsonl` | 24 | written for v0.1.3 after the nine-group fixes; labels frozen before the first run. Each case lists required actions, forbidden actions and the exact set of still-open obligations. | first run only |

Review reproductions and their variations are regression tests (`tests/test_v011_safety.py`, `tests/test_v012_semantics.py`), not benchmark data.

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
- quotation promises, requests, and sent or received quotations; vague appointments, rescheduling, completed visits;
- information offers (catalog, photos, samples, specs, links) accepted, declined, or mixed with a purchase question;
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
| Sale recall | correctly confirmed sales ÷ conversations labelled a sale |
| Review rate | conversations with `review_required` ÷ all. This includes the routine "dates unresolved, no reference date" warning, so it is not the same as abstaining. |
| Sale abstention rate | conversations whose deal state is a needs-a-human state (`possible_acceptance`, `*_needs_review`) ÷ all |
| Action case accuracy (action scenarios) | scenarios where the sale decision matches, every required action is proposed, no forbidden action is proposed, **and** the still-open obligations match exactly ÷ all (gate ≥ 0.90, and 0 false sales) |

### Results

These were measured locally on Python 3.13.16 and are reproduced by CI. Current results ([`data/benchmark_results.json`](data/benchmark_results.json)):

| Metric (target) | dev, 46 cases | holdout, 35 | holdout2, 26 | holdout3, 20 | holdout4, 20 |
| --- | --- | --- | --- | --- | --- |
| Commitments F1 (≥ 0.90) | 1.000 (8 events) | 1.000 (12) | 1.000 (5) | 1.000 (7) | 1.000 (4) |
| Amounts F1 (≥ 0.95) | 1.000 (31) | 1.000 (34) | 0.982 (P 1.00, R 0.96; 28 gold) | 1.000 (20) | 1.000 (20) |
| Amount roles F1 | 1.000 | 1.000 | 0.982 | 1.000 | 1.000 |
| Dates F1 (≥ 0.90) | 1.000 (10) | 1.000 (18) | 1.000 (11) | 1.000 (12) | 1.000 (8) |
| Commercial intent F1 | 1.000 (44 pos.) | 1.000 (33) | 1.000 (25) | 1.000 (20) | 1.000 (19) |
| Decision pending F1 | 1.000 (10 pos.) | 1.000 (8) | 1.000 (5) | 1.000 (2) | 1.000 (3) |
| Confirmed sale F1 | 1.000 (6 pos.) | 1.000 (6) | 1.000 (7) | 1.000 (7) | 1.000 (5) |
| False confirmed-sale rate (< 3%) | 0 / 40 | 0 / 29 | 0 / 19 | 0 / 13 | 0 / 15 |

Sale decisions per set (v0.1.3):

| Set | False sales | Sale recall | Review rate | Sale abstention |
| --- | --- | --- | --- | --- |
| dev (46) | 0 / 40 | 6 / 6 | 0.261 | 0.000 |
| holdout (35) | 0 / 29 | 6 / 6 | 0.457 | 0.029 |
| holdout2 (26) | 0 / 19 | 7 / 7 | 0.462 | 0.038 |
| holdout3 (20) | 0 / 13 | 7 / 7 | 0.400 | 0.150 |
| holdout4 (20) | 0 / 15 | 5 / 5 | 0.250 | 0.050 |
| action scenarios (24) | 0 / 19 | 5 / 5 | 0.458 | 0.042 |

Action scenarios (v0.1.3): action case accuracy **1.000**; required-action recall 1.000; forbidden actions proposed 0; open-obligation exact match 1.000.

Each release from v0.1.1 to v0.1.3 left the earlier splits' label scores byte-identical. v0.1.3 also changed no proposed action or deal state on the 147 earlier label cases.
The label benchmark only scores labels, money, dates and booleans. Action correctness is measured by the action-scenario set.
The remaining semantics (eligibility, fulfilment, deferral, event status) are covered by regression tests (`tests/test_v012_semantics.py`, `tests/test_v013_events.py`) and by the 28-check script from the v0.1.1 review, which passes 28/28.

**These current numbers are not blind.** The rules were changed after studying the errors on every holdout. The more honest estimate is the **first run on each holdout, before any fix it informed** ([`data/blind_first_runs.json`](data/blind_first_runs.json)):

| First blind run | Commitments F1 | Amounts F1 | Dates F1 | Pending F1 | Sale F1 | False sales |
| --- | --- | --- | --- | --- | --- | --- |
| holdout (unmodified candidate engine) | 0.909 | 0.986 | 0.914 | 0.769 | 0.727 | **1 / 29 (3.4%)** |
| holdout2 (after holdout-1 fixes) | **0.800** | 0.982 | **0.706** | 0.500 | 0.923 | 0 / 19 |
| holdout3 (v0.1.1 after the review fixes) | **0.857** | 1.000 | 1.000 | 0.800 | 0.727 | 0 / 13 |
| holdout4 (v0.1.2 after the expanded-review fixes) | **0.667** (4 events) | 1.000 | 1.000 | 1.000 | 0.750 | 0 / 15 |

The first run of the action scenarios (v0.1.3, before any scenario-informed change) gave:
- action case accuracy **0.958** (23/24);
- open obligations 0.958, sale recall 5/5, false sales 0/19.

The one miss: a deposit's stated remainder was tracked as a generic payment.

On each first run, at least one metric **missed its target** on phrasing the rules hadn't seen. Expect similar drops on real chats.
On holdout3 and holdout4, every miss was on the cautious side: real sales not confirmed, or appointment commitments missed. None were false sales.

Across all six sets, 0 false confirmed sales were found in 135 negative conversations.
Under IID random sampling, the exact one-sided 95% upper bound would be about 2.2% (rule of three: 2.22%).
Those assumptions **do not hold**: the cases were hand-picked, most sets were used for tuning, and all are synthetic. So this **does not demonstrate the < 3% target**.
Independent reviews also found false sales outside these sets:
- four in v0.1, fixed in v0.1.1;
- two more in v0.1.1, fixed in v0.1.2;
- one more pattern in v0.1.2 (plain information statements), fixed in v0.1.3.

Each round of review found something the sets did not cover. Treat the sets as development coverage, and see [PILOT_EVALUATION_PLAN.md](PILOT_EVALUATION_PLAN.md) for how real-world reliability should be measured.

**Human-rated next-action usefulness (target ≥ 80%) has not been measured.** It is `null` in every report, and no claim is made about it.

## Limitations

- **Synthetic, small, and Thai-rule-specific.** Small samples (5–12 commitment events per set). The real-world accuracy is unknown.
- **The event layer is small and heuristic.**
  - Clause splitting relies on spaces and a few conjunctions.
  - A delivery split across two messages (`ส่งใบเสนอราคา` / `ให้แล้วนะครับ`) is not recognised as a delivery (conservative).
  - A deferral that doesn't name its object (`ไว้ค่อยส่งทีหลัง`) is not recorded.
  - A rescheduled quotation delivery (`ขอเลื่อนวันส่งใบเสนอราคาเป็นวันศุกร์`) keeps the installation correctly, but the `send_quotation` proposal does not carry the new date.
- **Semantics are still rule-based.**
  - v0.1.2 adds explicit checks for *what* is accepted, rejected, rescheduled, completed or priced, and *whether* it is asserted, conditional, deferred or reported.
  - These checks are still Thai patterns, not a parser, so new phrasing can slip past them. The 28-check review script and holdout4 found adjacent cases after each fix.
- **Offer classification is keyword-based.**
  - The "what is being accepted" logic only looks at the shop's latest open offer, up to three messages back.
  - It recognizes a fixed list of information objects: catalog, photos/video, sample, spec/details/PDF, link, quotation.
  - Offers phrased without those words, or without a send/receive verb, fall back to the older rules.
  - Accepting information after an earlier, separate purchase offer is not linked to that offer.
- **Money eligibility is heuristic.**
  - Gift, included-component and expense roles come from nearby words.
  - Unseparated 9+ digit numbers are always treated as identifiers, so a price that large must be written with commas.
  - When a later separate price's relation to an earlier total is unclear, the total is kept and flagged; the engine does not decide.
- **Appointment lifecycle is single-slot.**
  - Only the latest reschedule is active.
  - Completion reports (`ติดตั้งเสร็จแล้ว`) are unverified and close every earlier attendance commitment.
  - There is no notion of several visits for one job.
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

See [SELF_AUDIT.md](SELF_AUDIT.md) for the audit log, and [PILOT_EVALUATION_PLAN.md](PILOT_EVALUATION_PLAN.md) for the real-world evaluation plan.

## License

MIT. See [LICENSE](LICENSE).
