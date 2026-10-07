"""Conservative Thai baseline. Pattern matches are evidence, not proof of payment."""
import re
from ..models import Evidence, Message, Signal
from .dates import DATES, extract_dates
from .money import BUDGET, extract_amounts
from .semantics import classify_clause, clause_at, clauses, event_target

COMMERCIAL = r"ราคา|ใบเสนอราคา|มัดจำ|โอน|ชำระ|เลขบัญชี|ซื้อ|สั่ง|เอา(?:ครับ|ค่ะ|ตัวนี้|อันนี้|รุ่นนี้)|ติดตั้ง|ซ่อม|" + BUDGET + r"|คิดค่า|ค่า(?:ซ่อม|แรง|บริการ|ออกแบบ|ติดตั้ง)|จ้าง|รับงาน|ขาย|สนใจ|รวมติด|แอร์|กล้อง|เดินสาย|โลโก้|โซลาร์|พิมพ์|ตกแต่ง|กี่บาท|แพ็กเกจ|โฆษณา|ช่าง|หน้างาน|สำรวจ"
PENDING = (r"ขอ(?!ราคา|เลข|ใบ|โทษ)\S{1,15}ก่อน|รอ\S{0,15}(?:ก่อน|อนุมัติ)|แล้วจะ(?:ทัก|ติดต่อ|แจ้ง|บอก)|เดี๋ยวทัก|ขอคิด|คิดดู|คิดอีกที|ถามแฟน|(?:ถาม|ปรึกษา)\S{0,15}ก่อน|ขอดู\S{0,12}ก่อน|ขอดูอีกที|ดูอีกที|ยังไม่(?:ซื้อ|เอา|ตัดสินใจ|ตกลง|ยืนยัน|แน่ใจ)"
           r"|ยังไม่ได้(?:ตกลง|ยืนยัน|ตัดสินใจ)|เดี๋ยว(?:ติดต่อ|แจ้ง|บอก)\S{0,6}(?:กลับ|อีกที)|ขอเทียบ|เทียบ\S{0,15}ก่อน|รอตัดสินใจ|ยังลังเล|ยังไม่พร้อม|ขอเวลา(?:ตัดสินใจ|คิด)")
CANCEL = r"ยกเลิก(?!นัด)(?:งาน|คำสั่งซื้อ|ออเดอร์|ทั้งหมด)?|ไม่(?:เอา|ซื้อ|จ้าง|ซ่อม|ติดตั้ง|ทำ)แล้ว|ขอถอน"
ELSEWHERE = r"ไม่(?:ไป)?(?:เอา|ซื้อ|จ้าง|ใช้)\S{0,4}(?:ที่อื่น|ร้านอื่น|เจ้าอื่น|คนอื่น)\S*"  # loyalty, not cancellation
RESCHEDULE = r"เลื่อน(?:นัด|วัน|คิว|เป็น)?|ยกเลิกนัด|ขอเปลี่ยนวัน|เปลี่ยนนัด"
# Where the replacement slot starts inside a reschedule message ("ยกเลิกนัดเสาร์ 09:00 | เลื่อนเป็นศุกร์").
REPLACEMENT_START = r"เลื่อน|ขอเปลี่ยนวัน|เปลี่ยนนัด|เปลี่ยนเป็น"
COMPLETED = (r"(?:ติดตั้ง|ซ่อม|ทำงาน|ทำ|เดินสาย|ตรวจ|สำรวจ|ล้าง)\S{0,8}เสร็จ(?:แล้ว|เรียบร้อย|ละ)|เสร็จเรียบร้อยแล้ว"
             r"|ช่าง(?:มา|เข้า)\S{0,10}แล้ว|เข้าหน้างานแล้ว|มาถึงแล้ว")
# Leading courtesy tokens that may precede an explicit acceptance ("โอเคครับ ตกลงตามนี้").
_LEAD = r"^(?:(?:โอเค|ok|ได้|ครับ|ค่ะ|คะ|จ้า|ค่า|เลย)[\s,!.]*)*"
ACCEPT = (_LEAD + r"(?:ตกลง(?:ครับ|ค่ะ|คะ)?[\s,]*(?:เอา|ซื้อ|สั่ง|จ้าง|ตามนี้|ทำเลย|ซ่อมเลย|ติดตั้งเลย|จัดเลย)|เอา(?:ครับ|ค่ะ|คับ|ค่า|จ้า|จ้ะ)(?:[\s.!]|$)|เอาเลย(?:ครับ|ค่ะ|พี่|นะ|[\s.!]|$)|(?:สั่ง|ซื้อ|จ้าง)เลย(?:ครับ|ค่ะ|พี่|นะ|[\s.!]|$)|เอา(?:ตัวนี้|อันนี้|รุ่นนี้|ตามนี้)(?:แหละ|เลย|ครับ|ค่ะ|พี่|นะ|[\s.!]|$)"
          r"|ยืนยัน(?:ตามราคานี้|ตามนี้|สั่งซื้อ|ซื้อ|จ้าง|เอา)|ตกลง(?:ซื้อ|จ้าง|ตามราคานี้|ตามนี้))")
# Short replies that might accept a price but are not explicit: require human confirmation.
POSSIBLE_ACCEPT = r"^(?:ตกลง|โอเค|ok|okay|จัดไป|ได้)(?:ครับ|ค่ะ|คะ|จ้า|เลย|[\s,!.])*"
UNSAFE_ACCEPT = r"ถ้า|หาก|สมมติ|ตัวอย่าง|เขาบอก|เค้าบอก|เพื่อนบอก|ลูกค้าบอก|บอกว่า|พูดว่า|หมายถึง|ไม่|ยัง|ก่อน|ไหม|มั้ย|หรือเปล่า|หรือยัง|\?|[\"“”‘’]"
YES_NO_QUESTION = r"ไหม|มั้ย|ไม๊|หรือเปล่า|\?"
# What a shop question offers. A price, quantity or spec in the question does not make it a
# purchase question: "ราคา 18,500 บาท ให้ส่งใบเสนอราคาให้ไหม" offers a document.
PURCHASE_QUESTION = r"ตกลง|ยืนยัน|สั่ง|ซื้อ|จ้าง|เอา(?:ตัว|รุ่น|แพ็ก|ชุด|อัน|เลย)|จัดเลย|ทำเลย|รับงาน"
TAKE_IT_QUESTION = r"(?:รับ|เอา)\s*(?:ไหม|มั้ย|ไม๊)"  # purchase question only together with an amount
INFO_OBJECTS = (("quotation", r"ใบเสนอราคา|ใบเสนอ|quotation"),
                ("catalog", r"แคต(?:ต)?าล็อ[กค]|catalog|โบรชัวร์|brochure"),
                ("photos", r"รูป|ภาพ|วิดีโอ|คลิป|video"),
                ("sample", r"ตัวอย่าง|sample"),
                ("specification", r"สเปค|สเปก|spec|รายละเอียด|ข้อมูล|pdf"),
                ("link", r"ลิงก์|link"))
INFO_OBJECT = "|".join(p for _, p in INFO_OBJECTS)
INFO_VERB = r"ส่ง|รับ|แนบ|ดู|ขอ"
SCHEDULING_QUESTION = r"นัด|ว่าง|สะดวก|เข้าไป|มาดู|คิว|กี่โมง|วันไหน"
# Explicit purchase wording that names the purchase itself, so it can stand anywhere in a reply.
_JOB_VERB = r"(?:ซ่อม|ติดตั้ง|ทำ|ติด|เดินสาย|ออกแบบ|พิมพ์)"
NAMED_PURCHASE = (r"ยืนยัน(?:ตามราคานี้|ตามนี้|สั่งซื้อ|สั่ง|ซื้อ|จ้าง)|ตกลง(?:ซื้อ|จ้าง|สั่ง|ตามราคานี้)"
                  r"|(?:ยืนยัน|ตกลง)" + _JOB_VERB + r"(?:ตามราคานี้|ตามนี้|เลย|ครับ|ค่ะ|$)")
AFFIRM_START = r"^(?:ส่งมา|ส่งให้|ขอดู|รบกวนส่ง)"
OPEN_QUESTION_WORDS = r"ไหน|อะไร|ยังไง|อย่างไร|เท่าไร|เท่าไหร่"
PROMISE = r"เดี๋ยว|(?<!น่า)จะ|รับปาก|สัญญา|ให้แล้ว|ไว้แล้ว|ไว้ให้|ล็อกคิว|จองคิว|ยืนยันคิว|ส่งให้พรุ่งนี้|ส่งราคาให้"
APPOINTMENT = r"เข้าทำ|รอช่าง|นัด|ติดตั้ง|รวมติด|อยากติด|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าซ่อม|มาติด|มาซ่อม|มาดู|ล็อกคิว|จองคิว|คิว|ว่างไหม|ว่างมั้ย|เข้าไป|เข้าวัด|เข้ามา"
PAYMENT = r"โอน|มัดจำ|ชำระ|จ่าย|เลขบัญชี|สลิป"
MISSED = r"ยังไม่(?:ได้)?โอน|ยังไม่(?:ได้)?ชำระ|เลย(?:กำหนด|นัด)|ผิดนัด|ยังไม่เข้า|เงินยังไม่|ยังไม่เห็น(?:ยอด|เงิน|สลิป)|ยังไม่ได้รับ(?:ยอด|เงิน)"
PRICE_QUESTION = r"ขอราคา|ราคา.*(?:เท่าไร|เท่าไหร่|ยังไง)|(?:คิดค่า|ค่า).*(?:เท่า|ยังไง)|กี่บาท|คิดยังไง"
QUOTE_DOCUMENT = r"ใบเสนอราคา|ใบเสนอ|quotation"
QUOTE_RECEIVED = r"ได้รับ\S{0,12}(?:ใบเสนอ|quotation)\S*\s*แล้ว|(?:ใบเสนอราคา|ใบเสนอ)\S{0,12}ได้รับแล้ว|ได้ใบเสนอราคาแล้ว"
# --- v0.1.2 semantic qualifiers -------------------------------------------------
# Reported speech: someone else's words ("เพื่อนบอกว่าไม่เอาแล้ว") are not the customer's own decision.
ATTRIBUTION = (r"(?:เพื่อน|แฟน|แม่|พ่อ|หัวหน้า|ภรรยา|สามี|เขา|เค้า|ที่บ้าน|เจ้านาย|ลูกค้า)\S{0,6}บอก"
               r"|(?<!ผม)(?<!ฉัน)(?<!เรา)(?<!หนู)(?<!ผมก็)(?:บอกว่า|พูดว่า)")  # "ผมบอกว่า…" is the customer's own word
REAFFIRM = r"แต่\S{0,6}ยัง(?:เอา|ซื้อ|จ้าง|ยืนยัน)"
# A shop statement that offers information without asking ("ส่งแคตตาล็อกให้ได้นะครับ", "เดี๋ยวส่งรูปให้ดู").
OFFER_STATEMENT = r"เดี๋ยว|(?<!น่า)จะ|ได้นะ|ให้ได้|ขอส่ง|ถ้าสนใจ|ให้ดู"
# Deferral of offered information: keep the interest, but not "send now".
DEFER = r"ยังไม่ต้อง|ไม่ต้อง(?:ส่ง)?\S{0,6}(?:ตอนนี้|ก่อน)|ไว้ค่อย|ค่อยส่ง|ทีหลัง|ไว้ก่อน"
# Customer speech acts about a quotation document.
QUOTE_DECLINED = r"(?:ไม่|ยังไม่)(?:ต้อง|เอา|ขอ)\S{0,8}(?:ใบเสนอ|quotation)"
QUOTE_REQUEST = (r"(?:ขอ|อยากได้|ต้องการ|รบกวน|ช่วย|ออก|ทำ)\S{0,15}(?:ใบเสนอ|quotation)"
                 r"|(?<!ที่)ส่ง\S{0,2}(?:ใบเสนอ|quotation)\S{0,12}มา|(?:ใบเสนอราคา|ใบเสนอ|quotation)\S{0,3}(?:หน่อย|ด้วย)"
                 r"|(?:ใบเสนอ|quotation).{0,30}ยังไม่ได้")
RECEIPT = r"^ได้(?:รับ|ใบ)"
QUESTION = r"ไหม|มั้ย|หรือยัง|หรือเปล่า|\?|เมื่อไร|เมื่อไหร่"
# A reply that is just a price ("3,200 ครับ", "ประมาณ 3,200 ค่ะ") — the only shape where a bare number is a price.
BARE_PRICE_REPLY = r"^\s*(?:ประมาณ|อยู่ที่|ราว|ราวๆ|ก็)?\s*\d[\d,]*(?:\.\d{1,2})?\s*(?:บาท)?\s*(?:ครับ|ค่ะ|คะ|นะ|จ้า|ค่า)*[\s.!]*$"
# "เวลาเดี๋ยวแจ้งอีกที" / "เดี๋ยวบอกเวลาอีกที": the time is pending, not the purchase decision.
TIMING_PENDING = r"(?:เวลา|วัน|นัด|คิว)\S{0,6}(?:เดี๋ยว|ขอ)?\S{0,3}(?:แจ้ง|บอก)|(?:แจ้ง|บอก)(?:เวลา|วัน)"
# Hedges that contain negative/future markers but are not negation ("ไม่เกิน" = no later than).
# Declining an information object ("ไม่เอาแคตตาล็อก") negates that object, not the purchase.
DECLINED_INFO = r"(?:ไม่|ยังไม่)(?:ต้อง|เอา|ขอ)\S{0,8}(?:" + INFO_OBJECT + r")\S*"
_HEDGE_MASK = re.compile(r"ไม่เกิน|น่าจะ|ไม่ต้อง|" + ELSEWHERE + "|" + DECLINED_INFO)  # incl. loyalty ("ไม่ซื้อร้านอื่น")


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def classify_offer(message: Message) -> str | None:
    """What a business message offers: information, purchase, mixed, appointment or other.

    Yes/no questions are classified by their object. A statement counts only when it offers
    information ("เดี๋ยวส่งรูปให้ดูครับ"); other statements, such as a price, return None."""
    t = message.text
    info = has(INFO_OBJECT, t) and has(INFO_VERB, t)
    if not has(YES_NO_QUESTION, t):
        # An offer need not be a question. A delivered item is history, not an open offer.
        if info and (has(OFFER_STATEMENT, t) or has(r"(?:ส่ง|แนบ)\S{0,25}ให้", t)) and not asserted_delivery(t):
            # With a price or ordering wording in the same message, a yes may accept either.
            return "mixed" if extract_amounts(t) or has(PURCHASE_QUESTION, t) else "information"
        return None
    purchase = has(PURCHASE_QUESTION, t) or (bool(extract_amounts(t)) and has(TAKE_IT_QUESTION, t))
    if info and purchase:
        return "mixed"
    if info:
        return "information"
    if purchase:
        return "purchase"
    return "appointment" if has(SCHEDULING_QUESTION, t) else "other"


DELIVERY_VERB = r"ส่ง|แนบ|แจ้ง"
# Completion marker: "แล้ว", or colloquial "ละ" at the end of a clause ("โอนละนะคะ", "เสร็จละครับ").
DONE = r"แล้ว|ละ(?=\s*(?:นะ|ครับ|ค่ะ|คะ|จ้า|น้า|คับ)*\s*$)"
# Courtesy and pronouns that may open a decision clause ("ขอโทษครับ ไม่จ้างครับ", "ผมไม่ซื้อครับ").
_CLAUSE_LEAD = r"^(?:ขอโทษ\S*|ขอบคุณ\S*|ผม|หนู|เรา|ฉัน|ดิฉัน|กระผม|ก็|คือ|แต่|ครับ|ค่ะ|คะ|นะ|จ้า)*"
REFUSAL = (r"(?:ไม่ซื้อ|ไม่จ้าง|ไม่ตกลง|ไม่ยืนยัน|ไม่เอาแล้ว)"
           r"(?!\S{0,4}(?:ที่อื่น|ร้านอื่น|เจ้าอื่น|คนอื่น|เพิ่ม))")
# A customer releasing deferred information ("ส่งแคตตาล็อกมาได้แล้วครับ", "ขอแคตตาล็อกตอนนี้เลย").
GO_AHEAD = r"(?:ส่ง|ขอ)\S{0,14}(?:มาได้|มาเลย|ได้แล้ว|ตอนนี้|มา(?=\S{0,3}(?:ครับ|ค่ะ|คะ|นะ|$)))"
REMAINDER = r"ที่เหลือ|ส่วนที่เหลือ|ค้างอีก|ที่ค้าง"


def event_status(text: str, pattern: str, *, completed: bool = False) -> tuple[str | None, re.Match | None]:
    """Status of the first occurrence of ``pattern``; an asserted occurrence wins over others.

    With ``completed=True`` only occurrences followed by ``แล้ว`` in the same clause count."""
    found = []
    for m in re.finditer(pattern, text, re.I):
        i, parts = clause_at(text, m.start())
        if completed and not re.search(DONE, text[m.start():parts[i].end]):
            continue
        found.append((classify_clause(text, m.start(), completed=completed), m))
    if not found:
        return None, None
    return next((f for f in found if f[0] == "asserted"), found[0])


def asserted_delivery(text: str) -> bool:
    status, _ = event_status(text, DELIVERY_VERB, completed=True)
    return status == "asserted"


def decision_clause(text: str, pattern: str) -> re.Match | None:
    """An asserted decision (refusal, cancellation...) opening one of the message's clauses."""
    for c in clauses(text):
        lead = re.match(_CLAUSE_LEAD, c.text)
        m = re.match(pattern, c.text[lead.end():])
        if m:
            at = c.start + lead.end()
            if classify_clause(text, at) == "asserted":
                return m
    return None


def info_kind(text: str) -> str:
    return next((kind for kind, pattern in INFO_OBJECTS if has(pattern, text)), "information")


def is_affirmation(text: str) -> bool:
    if has(RECEIPT, text):  # "ได้รับใบเสนอราคาแล้ว" reports receipt; it agrees to nothing
        return False
    return has(ACCEPT, text) or has(POSSIBLE_ACCEPT, text) or has(AFFIRM_START, text)


def reported_by_someone_else(text: str, at: int) -> bool:
    """True when the phrase at ``at`` is someone else's reported words."""
    return has(ATTRIBUTION, text[:at])


def unanswered_business_messages(messages: list[Message], i: int) -> list[Message]:
    """Business messages (newest first) in the three messages before ``i`` that the customer
    has not answered yet; a customer yes/no reply closes everything before it."""
    found = []
    for j in range(i - 1, max(-1, i - 4), -1):
        m = messages[j]
        if m.actor == "business":
            found.append(m)
        elif m.actor == "customer" and (is_affirmation(m.text) or has(r"^(?:ไม่|ยังไม่|ขอบคุณ)", m.text)):
            break
    return found


def open_offer(messages: list[Message], i: int) -> tuple[Message | None, str | None]:
    """The shop message a customer reply answers and what it offers.

    A later price statement does not close an earlier unanswered information offer
    ("ส่งแคตตาล็อกให้ดูไหม" / "ราคา 9,000 บาท" / "เอาครับ" is ambiguous)."""
    pending = unanswered_business_messages(messages, i)
    if not pending:
        return None, None
    latest, offer = pending[0], classify_offer(pending[0])
    if offer is None and any(classify_offer(m) in {"information", "mixed"} for m in pending[1:]):
        return latest, "mixed"
    return latest, offer


class RuleExtractor:
    name = "thai_rules_v0.1.3"

    def extract(self, messages: list[Message]) -> list[Signal]:
        signals: list[Signal] = []
        business_amount_seen = False

        def emit(m: Message, kind: str, value: object, confidence: float, **metadata: object) -> None:
            if m.actor == "unknown":
                confidence = min(confidence, 0.65)
            signals.append(Signal(f"s{len(signals)+1}", kind, m.actor, value, confidence,
                                  Evidence(m.id, m.speaker, m.text, m.raw_line), metadata))

        conversation_commercial = any(has(COMMERCIAL, m.text) or extract_amounts(m.text) for m in messages)
        for i, m in enumerate(messages):
            t = m.text
            guard = _HEDGE_MASK.sub("", t)  # text used for negation/condition guards
            previous = messages[i - 1] if i else None
            answers_price_question = (m.actor == "business" and previous is not None and has(BARE_PRICE_REPLY, t)
                                      and previous.actor == "customer" and has(PRICE_QUESTION, previous.text))
            amounts = extract_amounts(t, allow_bare=answers_price_question)
            dates = extract_dates(t)
            commercial = has(COMMERCIAL, t) or bool(amounts)
            if commercial:
                emit(m, "commercial_intent", "commercial_discussion", 0.90)
            if m.actor == "customer":
                if has(r"ไม่(?:ค่อย)?สนใจ", t):
                    emit(m, "customer_rejection", "declined", 0.92)
                elif has(r"สนใจ|อยากได้|อยากติด", t):
                    emit(m, "customer_interest", "interested", 0.94)
                about_timing = has(RESCHEDULE + "|" + APPOINTMENT, t) and has(TIMING_PENDING, t) and not has(r"จะเอา|ซื้อ|ตัดสินใจ|ตกลง", t)
                pending = re.search(PENDING, t)
                # "หากโอนเรียบร้อยแล้วจะแจ้งอีกที" promises a notice about the payment, not a pending decision.
                about_notice = pending is not None and pending.group().startswith("แล้วจะ") and has(PAYMENT + "|ส่ง", t[:pending.start()])
                if pending and not about_timing and not about_notice:
                    emit(m, "decision_pending", "awaiting_customer_decision", 0.96)
                cancel = re.search(CANCEL, t)
                cancel_status = classify_clause(t, cancel.start()) if cancel else None
                # What is cancelled: "ยกเลิกใบเสนอราคา" withdraws a document, not the purchase.
                cancel_target = event_target(t[:clause_at(t, cancel.start())[1][clause_at(t, cancel.start())[0]].end], cancel.start()) if cancel else None
                if cancel and cancel_target in {"document", "information"} and cancel_status == "asserted":
                    emit(m, "quotation_declined" if cancel_target == "document" else "information_declined",
                         "customer_withdraws_" + cancel_target, 0.90, cancelled_object=cancel_target)
                    cancel = None
                cancelled = (cancel is not None and cancel_status in {"asserted", "reported"}
                             and not has(r"ไม่ยกเลิก|ห้ามยกเลิก|" + ELSEWHERE, t))
                if cancelled and reported_by_someone_else(t, cancel.start()):
                    # Someone else's rejection: never a cancellation; review unless the customer reaffirms.
                    if not has(REAFFIRM, t):
                        emit(m, "reported_cancellation", "third_party_reports_cancellation", 0.70,
                             reason="cancellation_attributed_to_someone_else; confirm_with_customer")
                elif cancelled:
                    emit(m, "cancellation", "cancelled", 0.96)
                elif has(r"เปลี่ยนใจ", t) and not reported_by_someone_else(t, t.find("เปลี่ยนใจ")):
                    emit(m, "change_of_mind", "change_of_mind", 0.85)
                question, offer = open_offer(messages, i)
                # "ไม่เอาครับ" to "ส่งแคตตาล็อกให้ดูไหม" declines the catalog, not the deal; but an explicit
                # "ไม่ซื้อ"/"ไม่จ้าง" names the transaction and is never overridden by the previous offer.
                explicit_reject = decision_clause(t, REFUSAL) is not None
                bare_reject = (offer not in {"information", "appointment", "other"} and not has(r"^" + DECLINED_INFO, t)
                               and decision_clause(t, r"ไม่เอา(?!\S{0,4}(?:ที่อื่น|ร้านอื่น|เจ้าอื่น))") is not None)
                if (explicit_reject or bare_reject) and not cancelled:
                    emit(m, "customer_rejection", "declined", 0.94)
                self._acceptance(m, t, guard, question, offer, business_amount_seen, emit)
                haggle = re.search(r"ลด(?:ได้|ราคา|หน่อย|ให้)|ต่อราคา|แพง|เหลือ.*ได้ไหม", t)
                # "ถ้าแพงกว่านี้ผมไม่ซื้อ" is a hypothetical, not haggling; "ลดได้ไหม" still is.
                if haggle and classify_clause(t, haggle.start()) != "conditional":
                    emit(m, "negotiation", "price_negotiation", 0.90)
                already = any(s.type == "quotation_request" and s.evidence.message_id == m.id for s in signals)
                if has(QUOTE_DECLINED, t):
                    emit(m, "quotation_declined", "customer_declines_or_defers_quotation", 0.90)
                elif has(QUOTE_RECEIVED, t) and event_status(t, QUOTE_RECEIVED)[0] == "asserted":
                    emit(m, "quotation_received", "customer_reports_quotation_received", 0.90)
                elif has(QUOTE_RECEIVED, t):
                    pass  # "ถ้าได้รับใบเสนอราคาแล้วจะ…": a plan about the document, not a receipt or a request
                elif has(QUOTE_REQUEST, t) and not already:
                    deferral = {"deferred": True, "constraint": "customer_asked_not_to_send_yet"} if has(DEFER, t) else {}
                    emit(m, "quotation_request", "request_quotation", 0.85 if deferral else 0.95, **deferral)
                elif has(QUOTE_DOCUMENT, t) and has(QUESTION + "|กี่|อะไร", t) and not already:
                    emit(m, "quotation_question", "asks_about_quotation", 0.85)
                if has(PRICE_QUESTION, t):
                    emit(m, "price_enquiry", "asks_for_price", 0.95)
                kind = info_kind(t)
                if (has(INFO_OBJECT, t) and kind != "quotation" and has(GO_AHEAD, t) and not has(DEFER, t)
                        and event_status(t, GO_AHEAD)[0] == "asserted"):
                    emit(m, "information_requested", kind, 0.90, reason="customer_asks_for_information_now")
            if m.actor == "business":
                offer = classify_offer(m)
                if offer in {"information", "mixed"}:
                    emit(m, "information_offer", info_kind(t), 0.90, offer_class=offer)
                elif has(INFO_OBJECT, t) and not has(QUOTE_DOCUMENT, t) and asserted_delivery(t):
                    emit(m, "information_sent", info_kind(t), 0.90)
                # A delivered quotation needs the document and an asserted, completed "sent" — not
                # "ถ้าส่ง…แล้วจะ", "พรุ่งนี้จะส่ง… แล้ว…", "ส่งแล้วใช่ไหม" or "ยังไม่ได้ส่ง". A chat price is only a price.
                document = has(QUOTE_DOCUMENT, t)
                delivered = asserted_delivery(t)
                if delivered and document:
                    emit(m, "quotation_sent", "quotation_document_sent", 0.93)
                elif delivered and has(r"ราคา", t):
                    emit(m, "price_sent", "price_given_in_chat", 0.90)
                elif (document or has(r"ส่งราคา", t)) and has(PROMISE, t) and not has(r"ไม่ส่ง|ยังส่งไม่ได้|ส่งไม่ได้|อาจ|ถ้า|หาก|\?|ไหม|มั้ย", t):
                    emit(m, "business_commitment", "send_quotation", 0.96, deliverable="document" if document else "price")
                if has(r"ยกเลิก(?!นัด)", t) and not has(r"ถ้า|หาก|ไม่ยกเลิก|ได้ไหม|ได้มั้ย|\?|ลูกค้า", t):
                    emit(m, "business_cancellation", "business_mentions_cancellation", 0.85)
            # Each "เลื่อน" moves one target: an appointment, a payment, or a deliverable (photos, a quotation).
            reschedule_at = replacement_end = None
            moves = []
            if conversation_commercial and m.actor != "unknown":
                for x in re.finditer(RESCHEDULE, t):
                    status = classify_clause(t, x.start())
                    # "เลื่อนเป็นวันศุกร์ได้ไหม" is a polite request, not a question about the past.
                    polite_request = status == "questioned" and has(r"ได้ไหม|ได้มั้ย|ได้ไม๊|ขอ", t)
                    if status in {"conditional", "reported"} or (status == "questioned" and not polite_request):
                        continue
                    i_c, parts = clause_at(t, x.start())
                    target = event_target(t[:parts[i_c].end], x.start()) or "appointment"
                    moves.append((x.start(), "appointment" if target in {"appointment", "purchase"} else target))
            for target in dict.fromkeys(tg for _, tg in moves):
                if target == "payment":
                    emit(m, "payment_reschedule_request", "payment_timing_change", 0.88)
                elif target in {"document", "information"}:
                    emit(m, "deliverable_reschedule_request", target, 0.85, reason="moves_a_deliverable_not_the_appointment")
            slot_moves = [pos for pos, tg in moves if tg == "appointment"]
            if slot_moves:
                starts = [x.start() for x in re.finditer(REPLACEMENT_START, t) if x.start() in slot_moves or any(abs(x.start() - p) <= 3 for p in slot_moves)]
                reschedule_at = starts[-1] if starts else len(t)
                replacement_end = min((p for p, tg in moves if tg != "appointment" and p > reschedule_at), default=len(t))
                emit(m, "reschedule_request", "reschedule_appointment" if starts else "cancel_appointment_slot", 0.90)
            done_status, done = event_status(t, COMPLETED, completed=True)
            mentions_completion = done is not None
            if conversation_commercial and done_status == "asserted":
                emit(m, "appointment_completed", "work_or_visit_reported_complete", 0.88, verified=False)
            elif conversation_commercial and done_status in {"uncertain", "questioned"}:
                # "เสร็จแล้วมั้ง" / "เสร็จแล้วหรือยัง": keep tracking and ask someone to verify.
                emit(m, "completion_uncertain", "completion_not_confirmed", 0.70, status=done_status,
                     reason="completion_is_hedged_or_asked; verify_before_closing")
            # An inclusive installation price is not an appointment arrangement.
            scheduling_context = bool(dates) or has(r"นัด|ล็อกคิว|จองคิว|ยืนยันคิว|ว่างไหม|ว่างมั้ย|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าซ่อม|มาติด|มาซ่อม|เข้าไป|เข้าวัด|เข้ามา|รอช่าง|เข้าทำ", t) or (has(PROMISE, t) and has(r"ติดตั้ง|ซ่อม", t))
            # A message about finishing work ("ถ้าติดตั้งเสร็จแล้วจะโทรแจ้ง") does not arrange a visit.
            appointment = has(APPOINTMENT, t) and scheduling_context and not (mentions_completion and not dates)
            if appointment and conversation_commercial:
                tentative = has(r"ไหม|มั้ย|ถ้า|หาก|อยาก|\?|กี่โมง|เมื่อไร|เมื่อไหร่", guard)
                emit(m, "appointment", "schedule_discussion", 0.88 if tentative else 0.93)
                stated_booking = has(r"นัด", t) and bool(dates)
                # "จะโอนค่าสำรวจพรุ่งนี้" promises a payment for the visit, not attendance at it.
                paying_fee = has(r"โอน|จ่าย|ชำระ", t) and not has(r"เข้า|มา|ไป|รอ|อยู่บ้าน", t)
                if m.actor == "business" and (has(PROMISE, t) or stated_booking) and not has(r"ไม่|ถ้า|หาก|อาจ|\?|ไหม|มั้ย|เลื่อน", guard):
                    emit(m, "business_commitment", "reserve_or_attend_appointment", 0.93)
                elif m.actor == "customer" and not paying_fee and has(r"(?<!น่า)จะ|เดี๋ยว|ยืนยัน", t) and not has(r"ไม่|ถ้า|หาก|อาจ|\?|ไหม|มั้ย|เลื่อน", guard):
                    emit(m, "customer_commitment", "attend_appointment", 0.93)
            if conversation_commercial and has(PAYMENT, t):
                if has(r"(?:ขอ|ส่ง)\S{0,6}เลขบัญชี|เลขบัญชี\S{0,6}(?:หน่อย|ด้วย)", t):
                    emit(m, "payment_signal", "account_number_request", 0.92)
                else:
                    emit(m, "payment_signal", "deposit" if "มัดจำ" in t else "payment", 0.92)
                kind_value = "pay_deposit" if "มัดจำ" in t else "make_payment"
                # A remaining balance continues the earlier payment it belongs to ("…มัดจำ" then "ที่เหลือ 4,000").
                earlier = [s.value for s in signals if s.type == "customer_commitment" and s.value in {"pay_deposit", "make_payment"}]
                remainder_kind = kind_value if "มัดจำ" in t or not earlier else earlier[-1]
                money_here = [a for a in amounts]
                report_status, report = event_status(t, r"(?:โอน|ชำระ|จ่าย).{0,25}(?:" + DONE + r")|(?:ส่ง|แนบ)สลิป")
                remainder = re.search(REMAINDER, t)
                if has(MISSED, t):
                    emit(m, "payment_pending", "payment_unverified_or_overdue", 0.95)
                elif m.actor == "customer" and report is not None and report_status == "asserted":
                    # Only an asserted report counts, and it is still not bank-verified.
                    head = t[:remainder.start()] if remainder else t
                    paid = [a["amount"] for a in extract_amounts(head) if a["role"] in {"payment", "price", "deposit"}]
                    emit(m, "payment_reported", "customer_reports_payment", 0.92, verified=False,
                         **({"reported_amount": paid[0]} if paid else {}))
                if (m.actor == "customer" and remainder is not None and has(PAYMENT, t[remainder.start():])
                        and classify_clause(t, remainder.start()) in {"asserted", "future"}):
                    rest = [a["amount"] for a in extract_amounts(t[remainder.start():])]
                    emit(m, "customer_commitment", remainder_kind, 0.90, purpose="remaining_balance",
                         **({"amount": rest[0]} if rest else {}))
                elif (m.actor == "customer" and report is None and has(r"(?:เดี๋ยว|(?<!น่า)จะ|รับปาก|สัญญา|เย็นนี้|พรุ่งนี้|วันนี้|ภายใน|ไม่เกิน).*(?:โอน|จ่าย|ชำระ)|(?:โอน|จ่าย|ชำระ).*(?:เย็นนี้|พรุ่งนี้|ภายใน|ให้)", t)
                      and not has(r"ไม่|อาจ|ถ้า|หาก|ไหม|มั้ย|\?|แล้ว", guard)):
                    committed = [a["amount"] for a in money_here if a["role"] in {"deposit", "payment", "price"}]
                    emit(m, "customer_commitment", kind_value, 0.95, **({"amount": committed[0]} if committed else {}))
            for value in amounts:
                if value["role"] == "paid":  # money the shop spends is not revenue; a customer's is a payment
                    value = {**value, "role": "expense" if m.actor == "business" else "payment"}
                bare = not has(r"บาท|฿|\.-", t) and answers_price_question
                emit(m, "monetary_amount", value, 0.82 if bare else 0.96 if "บาท" in t else 0.90)
                if m.actor == "business":
                    business_amount_seen = True
            # Dates in noncommercial chat or about the past are plain temporal mentions.
            for match, value in zip(DATES.finditer(t), dates):
                slot = {}
                if reschedule_at is not None and match.start() < reschedule_at:
                    slot = {"slot_status": "superseded"}
                elif reschedule_at is not None and match.start() < replacement_end:
                    slot = {"slot_status": "replacement"}  # dates after a later payment move belong to the payment
                if not conversation_commercial or has(r"ตั้งแต่|เมื่อ(?!ไร|ไหร่)|ที่แล้ว|ที่ผ่านมา", t):
                    kind = "temporal_mention"
                elif has(PROMISE + "|" + PAYMENT + r"|ภายใน|ก่อน|ไม่เกิน|ทัน", t):
                    kind = "deadline"
                else:
                    kind = "schedule"
                emit(m, kind, value, 0.91, **slot)
        return signals

    @staticmethod
    def _acceptance(m: Message, t: str, guard: str, question: Message | None, offer: str | None,
                    business_amount_seen: bool, emit) -> None:
        """Decide what a customer reply accepts: the purchase, offered information, or unclear."""
        safe = not has(UNSAFE_ACCEPT, guard) and not has(PENDING + "|" + CANCEL, t)
        named_purchase = has(NAMED_PURCHASE, t) and safe and not has(OPEN_QUESTION_WORDS, t)
        product_pick = has(r"เอา(?:ตัวนี้|อันนี้|รุ่นนี้|ตามนี้)", t) and not has(r"ถ้า|หาก|บอกว่า|ไหม|มั้ย|\?", guard)
        if not (is_affirmation(t) or named_purchase or product_pick):
            return
        offer_meta = {"offer_message_id": question.id} if question is not None else {}
        # A document the customer declines ("ไม่ต้องส่งใบเสนอราคา") is not something the reply asks for.
        reply_names_info = has(INFO_OBJECT, re.sub(DECLINED_INFO, "", t))
        if named_purchase and not reply_names_info:
            emit(m, "customer_acceptance", "explicit_acceptance", 0.96, **offer_meta)
        elif offer == "information" and product_pick:
            emit(m, "possible_acceptance", "ambiguous_purchase_or_information", 0.60, **offer_meta,
                 reason="reply_to_information_offer_also_picks_a_product; confirm_explicitly")
        elif offer == "information":
            kind = info_kind(question.text)
            # "เอาครับ แต่ยังไม่ต้องส่ง": keep both the acceptance and the timing constraint.
            deferral = {"deferred": True, "constraint": "customer_asked_not_to_send_yet"} if has(DEFER, t) else {}
            emit(m, "information_accepted", kind, 0.85 if deferral else 0.90, **offer_meta, **deferral,
                 reason="customer_accepted_offered_information; not_a_purchase")
            if kind == "quotation":
                emit(m, "quotation_request", "request_quotation", 0.85 if deferral else 0.90,
                     via="accepted_quotation_offer", **offer_meta, **deferral)
        elif offer == "mixed" or (reply_names_info and offer in {None, "purchase"}):
            emit(m, "possible_acceptance", "ambiguous_purchase_or_information", 0.60, **offer_meta,
                 reason="reply_may_accept_information_or_purchase; confirm_explicitly")
        elif offer == "appointment":
            return  # agreeing to a time is captured by appointment signals, not as a purchase
        elif offer == "other":
            emit(m, "possible_acceptance", "reply_to_unrelated_question", 0.60, **offer_meta,
                 reason="yes_to_a_non_purchase_question; confirm_explicitly")
        elif has(ACCEPT, t) and safe:
            emit(m, "customer_acceptance", "explicit_acceptance", 0.96, **offer_meta)
        elif business_amount_seen and has(POSSIBLE_ACCEPT, t) and safe:
            emit(m, "possible_acceptance", "ambiguous_agreement", 0.70, **offer_meta,
                 reason="short_agreement_after_price; confirm_explicitly")
