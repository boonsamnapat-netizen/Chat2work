"""Conservative Thai baseline. Pattern matches are evidence, not proof of payment."""
import re
from ..models import Evidence, Message, Signal
from .dates import extract_dates
from .money import BUDGET, extract_amounts

COMMERCIAL = r"ราคา|ใบเสนอราคา|มัดจำ|โอน|ชำระ|เลขบัญชี|ซื้อ|สั่ง|เอา(?:ครับ|ค่ะ|ตัวนี้|อันนี้|รุ่นนี้)|ติดตั้ง|ซ่อม|" + BUDGET + r"|คิดค่า|ค่า(?:ซ่อม|แรง|บริการ|ออกแบบ|ติดตั้ง)|จ้าง|รับงาน|ขาย|สนใจ|รวมติด|แอร์|กล้อง|เดินสาย|โลโก้|โซลาร์|พิมพ์|ตกแต่ง|กี่บาท|แพ็กเกจ|โฆษณา|ช่าง|หน้างาน|สำรวจ"
PENDING = (r"ขอ(?!ราคา|เลข|ใบ|โทษ)\S{1,15}ก่อน|รอ\S{0,15}(?:ก่อน|อนุมัติ)|แล้วจะ(?:ทัก|ติดต่อ|แจ้ง|บอก)|เดี๋ยวทัก|ขอคิด|คิดดู|คิดอีกที|ถามแฟน|(?:ถาม|ปรึกษา)\S{0,15}ก่อน|ขอดู\S{0,12}ก่อน|ขอดูอีกที|ดูอีกที|ยังไม่(?:ซื้อ|เอา|ตัดสินใจ|ตกลง|ยืนยัน|แน่ใจ)"
           r"|ยังไม่ได้(?:ตกลง|ยืนยัน|ตัดสินใจ)|เดี๋ยว(?:ติดต่อ|แจ้ง|บอก)\S{0,6}(?:กลับ|อีกที)|ขอเทียบ|เทียบ\S{0,15}ก่อน|รอตัดสินใจ|ยังลังเล|ยังไม่พร้อม|ขอเวลา(?:ตัดสินใจ|คิด)")
CANCEL = r"ยกเลิก(?!นัด)(?:งาน|คำสั่งซื้อ|ออเดอร์|ทั้งหมด)?|ไม่(?:เอา|ซื้อ|จ้าง|ซ่อม|ติดตั้ง|ทำ)แล้ว|ขอถอน"
RESCHEDULE = r"เลื่อน(?:นัด|วัน|คิว|เป็น)?|ยกเลิกนัด|ขอเปลี่ยนวัน|เปลี่ยนนัด"
# Leading courtesy tokens that may precede an explicit acceptance ("โอเคครับ ตกลงตามนี้").
_LEAD = r"^(?:(?:โอเค|ok|ได้|ครับ|ค่ะ|คะ|จ้า|ค่า|เลย)[\s,!.]*)*"
ACCEPT = (_LEAD + r"(?:ตกลง(?:ครับ|ค่ะ|คะ)?[\s,]*(?:เอา|ซื้อ|สั่ง|จ้าง|ตามนี้|ทำเลย|ซ่อมเลย|ติดตั้งเลย|จัดเลย)|เอา(?:ครับ|ค่ะ)(?:[\s.!]|$)|เอาเลย(?:ครับ|ค่ะ|พี่|นะ|[\s.!]|$)|เอา(?:ตัวนี้|อันนี้|รุ่นนี้|ตามนี้)(?:แหละ|เลย|ครับ|ค่ะ|พี่|นะ|[\s.!]|$)"
          r"|ยืนยัน(?:ตามราคานี้|ตามนี้|สั่งซื้อ|ซื้อ|จ้าง|เอา)|ตกลง(?:ซื้อ|จ้าง|ตามราคานี้|ตามนี้))")
BARE_ACCEPT = r"^(?:เอา(?:ครับ|ค่ะ)|ได้(?:ครับ|ค่ะ))[\s.!]*$"
# Short replies that might accept a price but are not explicit: require human confirmation.
POSSIBLE_ACCEPT = r"^(?:ตกลง|โอเค|ok|okay|จัดไป|ได้)(?:ครับ|ค่ะ|คะ|จ้า|เลย|[\s,!.])*"
UNSAFE_ACCEPT = r"ถ้า|หาก|สมมติ|ตัวอย่าง|เขาบอก|เค้าบอก|เพื่อนบอก|ลูกค้าบอก|บอกว่า|พูดว่า|หมายถึง|ไม่|ยัง|ก่อน|ไหม|มั้ย|หรือเปล่า|หรือยัง|\?|[\"“”‘’]"
YES_NO_QUESTION = r"ไหม|มั้ย|ไม๊|หรือเปล่า|\?"
# A shop question that is itself about buying ("เอาตัวนี้ไหม", "ตกลงไหม", "ราคา 9,000 รับไหม").
PURCHASE_QUESTION = r"ตกลง|ยืนยัน|สั่ง|ซื้อ|จ้าง|เอา(?:ตัว|รุ่น|แพ็ก|ชุด|อัน)|ราคา|บาท|\d"
PROMISE = r"เดี๋ยว|(?<!น่า)จะ|รับปาก|สัญญา|ให้แล้ว|ไว้แล้ว|ไว้ให้|ล็อกคิว|จองคิว|ยืนยันคิว|ส่งให้พรุ่งนี้|ส่งราคาให้"
APPOINTMENT = r"นัด|ติดตั้ง|รวมติด|อยากติด|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าซ่อม|มาติด|มาซ่อม|มาดู|ล็อกคิว|จองคิว|คิว|ว่างไหม|ว่างมั้ย|เข้าไป|เข้าวัด|เข้ามา"
PAYMENT = r"โอน|มัดจำ|ชำระ|จ่าย|เลขบัญชี|สลิป"
MISSED = r"ยังไม่(?:ได้)?โอน|ยังไม่(?:ได้)?ชำระ|เลย(?:กำหนด|นัด)|ผิดนัด|ยังไม่เข้า|เงินยังไม่|ยังไม่เห็น(?:ยอด|เงิน|สลิป)|ยังไม่ได้รับ(?:ยอด|เงิน)"
PRICE_QUESTION = r"ขอ(?:ราคา|ใบเสนอราคา)|ราคา.*(?:เท่าไร|เท่าไหร่|ยังไง)|(?:คิดค่า|ค่า).*(?:เท่า|ยังไง)|กี่บาท|คิดยังไง"
# Hedges that contain negative/future markers but are not negation ("ไม่เกิน" = no later than).
_HEDGE_MASK = re.compile(r"ไม่เกิน|น่าจะ|ไม่ต้อง")


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


class RuleExtractor:
    name = "thai_rules_v0.1"

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
            answers_price_question = (m.actor == "business" and previous is not None
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
                if has(PENDING, t):
                    emit(m, "decision_pending", "awaiting_customer_decision", 0.96)
                if has(RESCHEDULE, t):
                    emit(m, "reschedule_request", "reschedule_appointment", 0.90)
                cancelled = has(CANCEL, t) and not has(r"ไม่ยกเลิก|ห้ามยกเลิก|ถ้า|หาก|สมมติ|ได้ไหม|ได้มั้ย|\?", t)
                if cancelled:
                    emit(m, "cancellation", "cancelled", 0.96)
                elif has(r"เปลี่ยนใจ", t):
                    emit(m, "change_of_mind", "change_of_mind", 0.85)
                if has(r"^(?:ไม่เอา|ไม่ซื้อ|ไม่ตกลง|ไม่ยืนยัน|ไม่จ้าง)", t) and not has(r"ไหม|มั้ย|\?|ถ้า|หาก|แล้ว", t):
                    emit(m, "customer_rejection", "declined", 0.94)
                explicit = has(ACCEPT, t) and not has(UNSAFE_ACCEPT, guard) and not has(PENDING + "|" + CANCEL, t)
                # "เอาครับ" after "ส่งแคตตาล็อกให้ดูไหม" / "รับน้ำไหม" answers that question, not the sale.
                replies_to_offer = (has(BARE_ACCEPT, t) and previous is not None and previous.actor == "business"
                                    and has(YES_NO_QUESTION, previous.text) and not has(PURCHASE_QUESTION, previous.text))
                if explicit and not replies_to_offer:
                    emit(m, "customer_acceptance", "explicit_acceptance", 0.96)
                elif replies_to_offer:
                    emit(m, "possible_acceptance", "reply_to_unrelated_question", 0.60,
                         reason="bare_yes_to_a_non_purchase_question; confirm_explicitly")
                elif (business_amount_seen and has(POSSIBLE_ACCEPT, t)
                      and not has(UNSAFE_ACCEPT, guard) and not has(PENDING + "|" + CANCEL, t)):
                    emit(m, "possible_acceptance", "ambiguous_agreement", 0.70,
                         reason="short_agreement_after_price; confirm_explicitly")
                if has(r"ลด(?:ได้|ราคา|หน่อย|ให้)|ต่อราคา|แพง|เหลือ.*ได้ไหม", t):
                    emit(m, "negotiation", "price_negotiation", 0.90)
                if has(PRICE_QUESTION, t):
                    emit(m, "quotation_request", "request_quotation", 0.95)
            if m.actor == "business":
                if has(r"ใบเสนอราคา|ส่งราคา|ส่งใบเสนอ", t):
                    if has(r"ส่ง(?:ราคา|ใบเสนอราคา).*แล้ว|ส่งให้แล้ว", t) and not has(r"ยังไม่|ไม่ได้|ไม่ส่ง", t):
                        emit(m, "quotation_sent", "quotation_sent", 0.93)
                    elif has(PROMISE, t) and not has(r"ไม่ส่ง|ยังส่งไม่ได้|ส่งไม่ได้|อาจ|ถ้า|หาก|\?|ไหม|มั้ย", t):
                        emit(m, "business_commitment", "send_quotation", 0.96)
                if has(r"ยกเลิก(?!นัด)", t) and not has(r"ถ้า|หาก|ไม่ยกเลิก|ได้ไหม|ได้มั้ย|\?|ลูกค้า", t):
                    emit(m, "business_cancellation", "business_mentions_cancellation", 0.85)
            # An inclusive installation price is not an appointment arrangement.
            scheduling_context = bool(dates) or has(r"นัด|ล็อกคิว|จองคิว|ยืนยันคิว|ว่างไหม|ว่างมั้ย|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าซ่อม|มาติด|มาซ่อม|เข้าไป|เข้าวัด|เข้ามา", t) or (has(PROMISE, t) and has(r"ติดตั้ง|ซ่อม", t))
            appointment = has(APPOINTMENT, t) and scheduling_context
            if appointment and conversation_commercial:
                question = has(r"ไหม|มั้ย|ถ้า|หาก|อยาก|\?|กี่โมง|เมื่อไร|เมื่อไหร่", guard)
                emit(m, "appointment", "schedule_discussion", 0.88 if question else 0.93)
                stated_booking = has(r"นัด", t) and bool(dates)
                if m.actor == "business" and (has(PROMISE, t) or stated_booking) and not has(r"ไม่|ถ้า|หาก|อาจ|\?|ไหม|มั้ย|เลื่อน", guard):
                    emit(m, "business_commitment", "reserve_or_attend_appointment", 0.93)
                elif m.actor == "customer" and has(r"(?<!น่า)จะ|เดี๋ยว|ยืนยัน", t) and not has(r"ไม่|ถ้า|หาก|อาจ|\?|ไหม|มั้ย|เลื่อน", guard):
                    emit(m, "customer_commitment", "attend_appointment", 0.93)
            if conversation_commercial and has(PAYMENT, t):
                if has(r"(?:ขอ|ส่ง)\S{0,6}เลขบัญชี|เลขบัญชี\S{0,6}(?:หน่อย|ด้วย)", t):
                    emit(m, "payment_signal", "account_number_request", 0.92)
                else:
                    emit(m, "payment_signal", "deposit" if "มัดจำ" in t else "payment", 0.92)
                if has(MISSED, t):
                    emit(m, "payment_pending", "payment_unverified_or_overdue", 0.95)
                elif m.actor == "customer" and has(r"(?:เดี๋ยว|(?<!น่า)จะ|รับปาก|สัญญา|เย็นนี้|พรุ่งนี้|วันนี้|ภายใน|ไม่เกิน).*(?:โอน|จ่าย|ชำระ)|(?:โอน|จ่าย|ชำระ).*(?:เย็นนี้|พรุ่งนี้|ภายใน|ให้)", t) and not has(r"ไม่|อาจ|ถ้า|หาก|ไหม|มั้ย|\?|แล้ว", guard):
                    emit(m, "customer_commitment", "pay_deposit" if "มัดจำ" in t else "make_payment", 0.95)
                elif m.actor == "customer" and has(r"(?:โอน|ชำระ|จ่าย).{0,25}แล้ว|(?:ส่ง|แนบ)สลิป", t) and not has(r"ยังไม่|ไม่", guard):
                    emit(m, "payment_reported", "customer_reports_payment", 0.92, verified=False)
            for value in amounts:
                bare = not has(r"บาท|฿|\.-", t) and answers_price_question
                emit(m, "monetary_amount", value, 0.82 if bare else 0.96 if "บาท" in t else 0.90)
                if m.actor == "business":
                    business_amount_seen = True
            # Dates in noncommercial chat or about the past are plain temporal mentions.
            for value in dates:
                if not conversation_commercial or has(r"ตั้งแต่|เมื่อ(?!ไร|ไหร่)|ที่แล้ว|ที่ผ่านมา", t):
                    kind = "temporal_mention"
                elif has(PROMISE + "|" + PAYMENT + r"|ภายใน|ก่อน|ไม่เกิน|ทัน", t):
                    kind = "deadline"
                else:
                    kind = "schedule"
                emit(m, kind, value, 0.91)
        return signals
