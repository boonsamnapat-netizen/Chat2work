"""v0.1.2: regressions for the expanded independent review of 7dfab32 (findings 1-15).

Grouped by semantic invariant: WHAT is accepted/rejected/rescheduled/completed/priced, and
WHETHER it is asserted, negated, conditional, deferred or reported. Review-derived
development coverage, not a blind benchmark.
"""
from datetime import date

import pytest

from chat2work import analyze
from chat2work.models import Evidence, Signal


def types(a):
    return {s.type for s in a.signals}


def actions(a):
    return {x.type for x in a.recommended_actions}


def missing(a):
    return {s.value for s in a.missing_information}


def roles(text):
    return [(s.value["amount"], s.value["role"]) for s in analyze(text).signals if s.type == "monetary_amount"]


# --- F1: information offers in statement form ---------------------------------

@pytest.mark.parametrize("offer", [
    "ส่งแคตตาล็อกให้ได้นะครับ", "เดี๋ยวส่งรูปแอร์ให้ดูครับ", "จะส่งตัวอย่างสีให้ดูนะครับ",
    "ส่งสเปคแผงโซลาร์ 550 วัตต์ให้ได้ครับ", "เดี๋ยวแนบลิงก์ผลงานให้นะคะ", "ถ้าสนใจ ส่งโบรชัวร์ให้ได้ครับ",
])
@pytest.mark.parametrize("reply", ["เอาครับ", "ได้ครับ ส่งมาเลย", "เอาค่ะ ขอบคุณค่ะ"])
def test_statement_form_information_offer_is_not_a_sale(offer, reply):
    a = analyze(f"ร้าน: {offer}\nลูกค้า: {reply}")
    assert not a.confirmed_sale and "customer_acceptance" not in types(a)
    assert "information_accepted" in types(a)


def test_statement_info_offer_with_price_is_ambiguous():
    a = analyze("ร้าน: ราคา 18,500 บาท เดี๋ยวส่งรูปให้ดูครับ\nลูกค้า: เอาครับ")
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance"


@pytest.mark.parametrize("text", [
    "ร้าน: ราคา 18,500 บาทครับ\nลูกค้า: เอาครับ",
    "ร้าน: ส่งแคตตาล็อกให้แล้วครับ ราคา 18,500 บาท\nลูกค้า: เอาครับ",
    "ร้าน: เดี๋ยวส่งรูปให้ดูครับ\nร้าน: ตัวนี้ 18,500 บาท เอาเลยไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: เดี๋ยวส่งรูปให้ดูครับ\nลูกค้า: ยืนยันตามราคานี้ครับ",
])
def test_purchase_controls_after_information_context(text):
    assert analyze(text).confirmed_sale


# --- F2 / F12: rejection and cancellation -------------------------------------

@pytest.mark.parametrize("prior", ["ร้าน: ราคา 18500 บาทครับ\nลูกค้า: เอาครับ", "ร้าน: ค่าติดตั้ง 18500 บาท\nลูกค้า: ยืนยันตามราคานี้ครับ"])
@pytest.mark.parametrize("offer", ["ร้าน: ส่งแคตตาล็อกให้ดูไหม", "ร้าน: ส่งรูปให้ดูไหม", "ร้าน: รับน้ำเปล่าไหมครับ"])
@pytest.mark.parametrize("reply", ["ไม่ซื้อครับ", "ไม่จ้างครับ", "ไม่ตกลงครับ", "ไม่ซื้อแล้วครับ"])
def test_explicit_commercial_rejection_revokes_sale_after_any_offer(prior, offer, reply):
    a = analyze(f"{prior}\n{offer}\nลูกค้า: {reply}")
    assert not a.confirmed_sale and a.deal_status in {"declined", "cancelled"}
    assert any(s.type == "customer_acceptance" for s in a.signals)  # history kept


@pytest.mark.parametrize("reply", ["ไม่เอาครับ", "ไม่ต้องครับ", "ไม่เป็นไรครับ"])
def test_declining_only_the_offered_object_keeps_sale(reply):
    a = analyze(f"ร้าน: ราคา 18500 บาทครับ\nลูกค้า: เอาครับ\nร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: {reply}")
    assert a.confirmed_sale


@pytest.mark.parametrize("text", [
    "เพื่อนบอกว่าไม่เอาแล้ว แต่ผมยังเอาตามเดิม",
    "แฟนบอกให้ยกเลิก แต่ผมยังยืนยันครับ",
    "แม่บอกว่าไม่ซื้อแล้ว แต่ผมยังซื้อนะครับ",
])
def test_reported_third_party_rejection_with_reaffirmation_keeps_sale(text):
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ\nลูกค้า: " + text)
    assert a.confirmed_sale and a.potential_revenue.amount == "18500"


def test_reported_rejection_without_reaffirmation_needs_review_not_cancel():
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ\nลูกค้า: แฟนบอกว่าไม่เอาแล้ว")
    assert a.deal_status != "cancelled" and a.review_required


def test_own_cancellation_still_cancels():
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ\nลูกค้า: ผมขอยกเลิกครับ")
    assert a.deal_status == "cancelled"


# --- F3 / F11: quotation speech acts ---------------------------------------------

@pytest.mark.parametrize("reply", ["ส่งราคาให้แล้วครับ 18500 บาท", "แจ้งราคาไปแล้วครับ 18,500 บาท", "ราคา 18,500 บาทครับ"])
def test_chat_price_does_not_fulfil_quotation_document(reply):
    a = analyze("ลูกค้า: ขอใบเสนอราคาเป็น PDF หน่อยครับ\nร้าน: " + reply)
    assert "send_quotation" in actions(a) and "quotation_sent" not in types(a)


@pytest.mark.parametrize("delivery", ["ส่งใบเสนอราคาให้แล้วครับ", "แนบไฟล์ใบเสนอราคา PDF ให้แล้วครับ", "ส่ง quotation ทางอีเมลแล้วครับ"])
def test_document_delivery_fulfils_quotation(delivery):
    a = analyze("ลูกค้า: ขอใบเสนอราคาเป็น PDF หน่อยครับ\nร้าน: " + delivery)
    assert "send_quotation" not in actions(a)


def test_price_promise_fulfilled_by_sending_price():
    a = analyze("ร้าน: เดี๋ยวพรุ่งนี้ส่งราคาให้ครับ\nร้าน: ส่งราคาให้แล้วครับ 2,500 บาท")
    assert "send_quotation" not in actions(a) and "track_commitment" not in actions(a)


@pytest.mark.parametrize("text", ["ไม่ต้องส่งใบเสนอราคาให้ครับ", "ไม่เอาใบเสนอราคาครับ", "ยังไม่ต้องทำใบเสนอราคานะครับ"])
def test_declined_quotation_is_not_a_request(text):
    a = analyze("ลูกค้า: " + text)
    assert "quotation_request" not in types(a) and "send_quotation" not in actions(a)


@pytest.mark.parametrize("text", ["ใบเสนอราคามีอายุกี่วันครับ", "ใบเสนอราคารวม VAT หรือยังครับ", "ใบเสนอราคาที่ส่งมาถูกต้องไหมครับ"])
def test_question_about_a_quotation_is_not_a_request(text):
    a = analyze("ลูกค้า: " + text)
    assert "quotation_request" not in types(a) and "send_quotation" not in actions(a)


@pytest.mark.parametrize("text", ["ได้รับใบเสนอราคาแล้วครับ", "ได้รับแล้วครับ ขอบคุณ", "ได้ใบเสนอราคาแล้วค่ะ"])
def test_receipt_report_is_not_purchase_agreement(text):
    a = analyze("ร้าน: ราคา 18,500 บาท ส่งใบเสนอราคาให้แล้วครับ\nลูกค้า: " + text)
    assert "possible_acceptance" not in types(a) and "confirm_deal_status" not in actions(a)
    assert not a.confirmed_sale


# --- F4: conditional / future completion -------------------------------------------

BOOKED = "ร้าน: ราคา 18500 บาท จะเข้าติดตั้งวันเสาร์ 09:00\n"


@pytest.mark.parametrize("text", [
    "ร้าน: ถ้าติดตั้งเสร็จแล้วจะโทรแจ้งครับ", "ร้าน: พอติดตั้งเสร็จแล้วจะส่งรูปให้ดู", "ร้าน: น่าจะติดตั้งเสร็จเรียบร้อยแล้วช่วงบ่าย",
    "ลูกค้า: ติดตั้งเสร็จแล้วหรือยังครับ", "ร้าน: ยังติดตั้งไม่เสร็จครับ", "ร้าน: หลังจากติดตั้งเสร็จแล้วค่อยโอนนะครับ",
])
def test_non_asserted_completion_keeps_commitment_open(text):
    a = analyze(BOOKED + text)
    assert "appointment_completed" not in types(a) and "track_commitment" in actions(a)


@pytest.mark.parametrize("text", ["ร้าน: ติดตั้งเสร็จแล้วครับ", "ร้าน: ติดตั้งเสร็จเรียบร้อยแล้วครับ เดี๋ยวส่งบิลให้"])
def test_asserted_completion_closes_commitment(text):
    a = analyze(BOOKED + text)
    assert "appointment_completed" in types(a) and "track_commitment" not in actions(a)


# --- F5: what is being rescheduled ----------------------------------------------------

@pytest.mark.parametrize("text", ["ขอเลื่อนโอนมัดจำไปวันศุกร์ครับ", "ขอเลื่อนวันโอนเป็นวันจันทร์นะครับ", "ขอเลื่อนจ่ายเงินไปอาทิตย์หน้า"])
def test_payment_reschedule_does_not_touch_appointment(text):
    a = analyze(BOOKED + "ลูกค้า: " + text)
    booking = next(s for s in a.signals if s.type == "business_commitment")
    assert booking.metadata.get("slot_status") != "superseded"
    assert "reschedule_request" not in types(a) and "payment_reschedule_request" in types(a)
    assert "appointment_time" not in missing(a) and "track_commitment" in actions(a)


def test_appointment_reschedule_still_supersedes():
    a = analyze(BOOKED + "ลูกค้า: ขอเลื่อนนัดติดตั้งเป็นวันศุกร์ครับ")
    assert next(s for s in a.signals if s.type == "business_commitment").metadata.get("slot_status") == "superseded"


# --- F6: deferral of requested information -------------------------------------------

@pytest.mark.parametrize("offer, reply", [
    ("ส่งแคตตาล็อกให้ดูไหม", "เอาครับ แต่ยังไม่ต้องส่งครับ"),
    ("ส่งรูปให้ดูไหมครับ", "ได้ครับ ไว้ค่อยส่งทีหลัง"),
    ("ส่งใบเสนอราคาให้ไหม", "เอาครับ แต่ไม่ต้องส่งตอนนี้"),
])
def test_deferred_information_keeps_interest_without_send_now(offer, reply):
    a = analyze(f"ร้าน: {offer}\nลูกค้า: {reply}")
    accepted = [s for s in a.signals if s.type in {"information_accepted", "quotation_request"}]
    assert accepted and all(s.metadata.get("deferred") for s in accepted)
    assert not actions(a) & {"send_offered_information", "send_quotation"}
    assert "await_customer_go_ahead" in actions(a)


def test_later_go_ahead_after_deferral_reopens_send():
    a = analyze("ร้าน: ส่งใบเสนอราคาให้ไหม\nลูกค้า: เอาครับ แต่ไม่ต้องส่งตอนนี้\nลูกค้า: ส่งใบเสนอราคามาได้แล้วครับ")
    assert "send_quotation" in actions(a)


# --- F7 / F8 / F9: money eligibility --------------------------------------------------

@pytest.mark.parametrize("reply", ["เบอร์โทร +66890000000 ครับ", "โทร +66 89 000 0000 ครับ", "ติดต่อ +6689-000-0000", "ไลน์ไอดี 66890000000 ครับ"])
def test_phone_identifiers_are_never_money(reply):
    a = analyze("ลูกค้า: ขอราคาหน่อยครับ\nร้าน: " + reply)
    assert not [s for s in a.signals if s.type == "monetary_amount"] and a.potential_revenue.amount is None


@pytest.mark.parametrize("reply, amount", [("3,200 ครับ", "3200"), ("ประมาณ 3,200 ครับ", "3200"), ("อยู่ที่ 3200 ค่ะ", "3200")])
def test_bare_price_answer_still_extracted(reply, amount):
    assert roles("ลูกค้า: ราคาเท่าไหร่ครับ\nร้าน: " + reply) == [(amount, "price")]


@pytest.mark.parametrize("text, role", [
    ("ร้าน: แถมขาแขวนมูลค่า 500 บาท", "gift_value"), ("ร้าน: ของแถมมูลค่า 1,200 บาทครับ", "gift_value"),
    ("ร้าน: ค่าแรง 1500 บาทรวมอยู่ในราคาแล้ว", "included_component"), ("ร้าน: ค่าส่ง 300 บาท รวมในราคาแล้วครับ", "included_component"),
    ("ร้าน: จ่ายค่าอะไหล่ 1500 บาทครับ", "expense"), ("ร้าน: ซื้ออะไหล่มา 800 บาท", "expense"),
    ("ลูกค้า: จ่ายค่าซ่อม 950 บาทแล้วครับ", "payment"),
])
def test_non_selling_amount_roles(text, role):
    assert [r for _, r in roles(text)] == [role]


@pytest.mark.parametrize("extra", ["ร้าน: แถมขาแขวนมูลค่า 500 บาท", "ร้าน: ค่าแรง 1500 บาทรวมอยู่ในราคาแล้ว", "ร้าน: จ่ายค่าอะไหล่ 1500 บาทครับ"])
def test_supporting_amount_does_not_replace_deal_price(extra):
    for first in ("ร้าน: ราคา 18500 บาทรวมติดตั้ง", "ร้าน: ราคารวม 18500 บาทครับ"):
        a = analyze(f"{first}\n{extra}\nลูกค้า: ยืนยันตามราคานี้ครับ")
        assert a.potential_revenue.amount == "18500", (first, extra)
        assert a.confirmed_sale


def test_split_bubbles_match_single_message_total():
    one = analyze("ร้าน: ราคารวม 18500 บาท ค่าแรง 1500 บาท\nลูกค้า: ยืนยันตามราคานี้ครับ").potential_revenue.amount
    two = analyze("ร้าน: ราคารวม 18500 บาท\nร้าน: ค่าแรง 1500 บาท\nลูกค้า: ยืนยันตามราคานี้ครับ")
    assert one == "18500" and two.potential_revenue.amount == "18500"
    assert two.review_required and any("later_price_relation_unclear" in w for w in two.warnings)


@pytest.mark.parametrize("revision", ["ราคาใหม่ 17,000 บาทครับ", "ลดเหลือ 17,000 บาทครับ", "ปรับราคาเป็น 17,000 บาท"])
def test_explicit_revision_replaces_total(revision):
    assert analyze(f"ร้าน: ราคารวม 18,500 บาท\nร้าน: {revision}").potential_revenue.amount == "17000"


def test_expense_alone_is_not_opportunity():
    assert analyze("ร้าน: จ่ายค่าอะไหล่ 1500 บาทครับ").potential_revenue.amount is None


@pytest.mark.parametrize("text", ["ร้าน: ช่างบอกราคา 18500 บาทครับ", "ร้าน: พี่ช่างบอกว่า 18,500 บาท", "ร้าน: ทางร้านขอบอกราคา 18500 บาท", "ร้าน: ทั้งบ้าน 22,000 บาท"])
def test_budget_needs_a_real_budget_word(text):
    assert [r for _, r in roles(text)] == ["price"]


@pytest.mark.parametrize("text", ["ลูกค้า: งบ 45000 บาท", "ลูกค้า: มีงบไม่เกิน 45,000 บาท", "ลูกค้า: งบประมาณ 80,000 บาท", "ลูกค้า: ตั้งงบไว้ 30,000 บาท"])
def test_real_budget_still_detected(text):
    assert [r for _, r in roles(text)] == ["budget"]


# --- F10: short year --------------------------------------------------------------------

@pytest.mark.parametrize("text, raw", [("ร้าน: นัดติดตั้ง 15 ต.ค. 70 เวลา 09:00", "15 ต.ค. 70"), ("ร้าน: นัดติดตั้ง 15 ตุลาคม 70", "15 ตุลาคม 70")])
def test_short_year_preserved_and_unresolved(text, raw):
    a = analyze(text, reference_date=date(2026, 10, 7))
    d = next(s for s in a.signals if s.type in {"schedule", "deadline"} and s.value["kind"] == "date")
    assert d.value["raw"] == raw and d.value["resolved_date"] is None and d.value["resolution"] == "ambiguous"


def test_full_year_and_time_after_month_still_work():
    a = analyze("ร้าน: นัดติดตั้ง 15 ต.ค. 2569 09:00", reference_date=date(2026, 10, 7))
    raws = {s.value["raw"]: s.value["resolved_date"] for s in a.signals if s.type in {"schedule", "deadline"}}
    assert raws == {"15 ต.ค. 2569": "2026-10-15", "09:00": None}


# --- F13 / F14: final-graph invariants ----------------------------------------------------

def test_derived_signals_respect_unknown_speaker_ceiling():
    a = analyze("นัดติดตั้งวันเสาร์ครับ")
    assert a.missing_information and all(s.confidence <= 0.65 for s in a.signals if s.actor == "unknown")
    assert all(x.confidence <= 0.65 for x in a.recommended_actions)


class OneSignalAdapter:
    name = "audit_adapter"

    def __init__(self, signal_id):
        self.signal_id = signal_id

    def extract(self, messages):
        m = messages[0]
        return [Signal(self.signal_id, "appointment", m.actor, "schedule_discussion", .93,
                       Evidence(m.id, m.speaker, m.text, m.raw_line))]


@pytest.mark.parametrize("signal_id", ["s1", "s2", "s3", "custom-7"])
def test_adapter_ids_stay_unique_after_derivation(signal_id):
    a = analyze("ร้าน: นัดติดตั้งวันเสาร์ครับ", extractor=OneSignalAdapter(signal_id))
    ids = [s.id for s in a.signals]
    assert len(ids) == len(set(ids)) and a.missing_information
    assert all(i in ids for x in a.recommended_actions for i in x.signal_ids)


# --- F15: retracted address -------------------------------------------------------------

@pytest.mark.parametrize("retraction", ["ที่อยู่เมื่อกี้ผิดครับ เดี๋ยวส่งใหม่", "ขอเปลี่ยนที่อยู่นะครับ", "ที่อยู่ไม่ถูกครับ"])
def test_retracted_address_is_requested_again(retraction):
    a = analyze("ลูกค้า: นัดติดตั้งวันเสาร์ 09:00 ที่อยู่: บ้านเลขที่ 123 ถนนทดสอบ\nลูกค้า: " + retraction)
    assert "installation_address" in missing(a)


def test_new_address_after_retraction_satisfies():
    a = analyze("ลูกค้า: นัดติดตั้งวันเสาร์ 09:00 ที่อยู่: บ้านเลขที่ 123 ถนนทดสอบ\nลูกค้า: ที่อยู่เมื่อกี้ผิดครับ\nลูกค้า: ที่อยู่: บ้านเลขที่ 45 ถนนทดสอบสอง")
    assert "installation_address" not in missing(a)


# --- adjacent cases found by probing the v0.1.2 fixes ----------------------------------

@pytest.mark.parametrize("text", ["ร้าน: รุ่นนี้ 18,500 บาท", "ร้าน: รุ่นใหม่ราคา 18,500 บาท", "ร้าน: ค่าบริการ paid 500 บาท"])
def test_identifier_words_do_not_swallow_prices(text):
    assert [a for a, _ in roles(text)] == [text.split()[-2].replace(",", "")]


@pytest.mark.parametrize("text", ["ไม่ซื้อที่อื่นแน่นอนครับ", "ไม่จ้างเจ้าอื่นแล้วครับ"])
def test_refusing_competitors_is_not_rejecting_the_deal(text):
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ\nลูกค้า: " + text)
    assert a.confirmed_sale


def test_first_person_reported_cancellation_is_own_cancellation():
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ\nลูกค้า: ผมบอกว่าไม่เอาแล้วครับ")
    assert a.deal_status == "cancelled"


@pytest.mark.parametrize("offer", ["เดี๋ยวส่งรูปให้ดูครับ ถ้าโอเคก็สั่งได้เลย", "รุ่นนี้ 18,500 บาท มีรูปให้ดูในเพจครับ"])
def test_statement_offer_mixed_with_purchase_needs_review(offer):
    a = analyze(f"ร้าน: {offer}\nลูกค้า: เอาครับ")
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance"


def test_appointment_and_payment_rescheduled_in_one_message():
    a = analyze(BOOKED + "ลูกค้า: ขอเลื่อนนัดเป็นวันอาทิตย์ และขอเลื่อนโอนไปวันจันทร์")
    assert {"reschedule_request", "payment_reschedule_request"} <= types(a)
    assert next(s for s in a.signals if s.type == "business_commitment").metadata.get("slot_status") == "superseded"
    slots = {s.value["raw"]: s.metadata.get("slot_status") for s in a.signals if s.type in {"schedule", "deadline"} and s.evidence.message_id == 1}
    assert slots["วันอาทิตย์"] == "replacement" and slots["วันจันทร์"] is None
    assert "appointment_time" in missing(a)


# --- holdout4 first-run weaknesses (fixed after that run; holdout4 is now development coverage) ---

@pytest.mark.parametrize("text", ["ร้าน: จะเข้าทำวันพฤหัส 14:00 ครับ", "ร้าน: เดี๋ยวเข้าทำงานให้วันเสาร์ครับ"])
def test_coming_to_do_the_work_is_a_visit_commitment(text):
    a = analyze("ร้าน: ค่าแรง 3,000 บาท\n" + text)
    assert any(s.type == "business_commitment" and s.value == "reserve_or_attend_appointment" for s in a.signals)


@pytest.mark.parametrize("reply", ["ไม่ต้องส่งใบเสนอราคาครับ ยืนยันตามราคานี้", "ไม่เอาแคตตาล็อกครับ ตกลงซื้อเลย"])
def test_declined_document_does_not_make_explicit_purchase_ambiguous(reply):
    assert analyze("ร้าน: ราคา 7,500 บาท\nลูกค้า: " + reply).confirmed_sale


@pytest.mark.parametrize("reply", ["เอาครับ ไม่ไปซื้อที่อื่นแล้ว", "เอาค่ะ ไม่จ้างเจ้าอื่นแน่นอน"])
def test_loyalty_phrase_does_not_block_acceptance(reply):
    assert analyze("ร้าน: ราคา 7,500 บาท\nลูกค้า: " + reply).confirmed_sale
