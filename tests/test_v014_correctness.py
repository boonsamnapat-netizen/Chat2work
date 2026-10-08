"""v0.1.4: correctness/safety regressions for the 13 groups in the audit of 563eb8a.

Shared causes covered: clause scope (a closed conditional, a speaker switch after reported speech),
assertion status (hedged acceptance, negated/uncertain rescheduling), event-object binding (which
object a delivery, a completion or a time belongs to), payment purpose/identity matching,
competitor attribution, adapter-value validation and redaction placeholders.
Natural variants and positive controls are included. Review-derived development coverage only.
"""
import math

import pytest

from chat2work import analyze
from chat2work.models import Evidence, Signal


def types(a):
    return {s.type for s in a.signals}


def actions(a):
    return {x.type for x in a.recommended_actions}


def missing(a):
    return {s.value for s in a.missing_information}


def open_commitments(a):
    by_id = {s.id: s for s in a.signals}
    return [by_id[i] for x in a.recommended_actions if x.type == "track_commitment" for i in x.signal_ids]


def open_values(a):
    return sorted(s.value for s in open_commitments(a))


def evidence_backed(a, action):
    """The action exists and every evidence item is an exact source message."""
    found = [x for x in a.recommended_actions if x.type == action]
    texts = {m.text for m in a.messages}
    return bool(found) and all(e.text in texts for x in found for e in x.evidence)


PRICE = "ร้าน: ราคา 18500 บาทครับ\n"
SALE = PRICE + "ลูกค้า: เอาครับ\n"
BOOKED = "ร้าน: ราคา 18500 บาท จะเข้าติดตั้งวันเสาร์ 09:00\n"
QUOTE_REQUEST = "ลูกค้า: ขอใบเสนอราคา PDF ครับ\n"
DEPOSIT_PROMISE = "ลูกค้า: เดี๋ยวเย็นนี้โอนมัดจำ 5000 บาท\n"


# --- P1-01 hedged acceptance -------------------------------------------------------------

@pytest.mark.parametrize("reply", [
    "เอาครับ มั้งนะ", "เอาครับ น่าจะเอานะ", "ตกลงซื้อเลยครับมั้ง",
    "เอาครับมั้ง", "น่าจะเอาครับ", "คงเอาครับ", "อาจจะเอาครับ", "เอาเลยครับ มั้ง",
    "ยืนยันตามราคานี้ครับ มั้ง", "ตกลงตามนี้ครับ น่าจะนะ", "ไม่แน่ใจ แต่เอาครับ", "คิดว่าเอาครับ",
])
def test_hedged_acceptance_is_not_a_sale(reply):
    a = analyze(PRICE + "ลูกค้า: " + reply)
    assert not a.confirmed_sale
    assert a.review_required
    assert a.deal_status == "possible_acceptance"
    assert evidence_backed(a, "confirm_deal_status")
    assert any(s.type == "possible_acceptance" and s.evidence.text == reply for s in a.signals)


@pytest.mark.parametrize("reply", ["ยืนยันตามราคานี้ครับ", "เอาครับ", "ตกลงซื้อเลยครับ", "เอาครับ ขอบคุณครับ", "ยืนยันตามนี้ครับ"])
def test_unhedged_acceptance_still_confirms(reply):
    a = analyze(PRICE + "ลูกค้า: " + reply)
    assert a.confirmed_sale and a.deal_status == "accepted"


# --- P1-02 closed conditional does not govern the next clause ----------------------------

@pytest.mark.parametrize("cancel", [
    "ถ้าใบเสนอราคาส่งไม่ทันไม่เป็นไร ผมยกเลิกงานนี้ครับ",
    "ถ้าส่งใบเสนอราคาไม่ทันก็ไม่เป็นไรครับ ผมยกเลิกงานนี้",
    "หากช่างไม่ว่างไม่เป็นไรครับ ผมยกเลิกงานนี้ครับ",
    "ถ้าไม่ทันไม่เป็นไร ยกเลิกงานครับ",
])
def test_unrelated_closed_conditional_does_not_hide_cancellation(cancel):
    a = analyze(SALE + "ลูกค้า: " + cancel)
    assert not a.confirmed_sale
    assert a.deal_status in {"cancelled", "changed_needs_review"}
    assert any(s.type == "customer_acceptance" for s in a.signals)  # the earlier acceptance stays as evidence
    assert any(s.type in {"cancellation", "reported_cancellation"} and s.evidence.text == cancel for s in a.signals)


@pytest.mark.parametrize("reply", ["ถ้าลดได้ เอาครับ", "ถ้าลดได้ ตกลงซื้อครับ", "ถ้าส่งพรุ่งนี้ได้ เอาครับ"])
def test_open_conditional_still_governs_acceptance(reply):
    a = analyze(PRICE + "ลูกค้า: " + reply)
    assert not a.confirmed_sale


@pytest.mark.parametrize("reply", ["ถ้าแพงกว่านี้ ผมยกเลิกครับ", "ถ้าช่างไม่ว่าง ยกเลิกงานนี้ครับ"])
def test_open_conditional_still_governs_cancellation(reply):
    a = analyze(SALE + "ลูกค้า: " + reply)
    assert "cancellation" not in types(a)


# --- P1-03 reported speech followed by the customer's own decision ------------------------

@pytest.mark.parametrize("reply", [
    "เพื่อนบอกว่าดี แต่ผมไม่ซื้อครับ", "แฟนบอกว่าคุ้ม แต่ผมไม่ซื้อแล้วครับ", "เพื่อนบอกว่าดี แต่ผมไม่เอาแล้วครับ",
    "เขาบอกว่าดี แต่ผมขอยกเลิกครับ",
])
def test_customer_refusal_after_third_party_speech_revokes_sale(reply):
    a = analyze(SALE + "ลูกค้า: " + reply)
    assert not a.confirmed_sale
    assert a.deal_status in {"declined", "cancelled"}


def test_third_party_cancellation_alone_is_not_a_cancellation():
    a = analyze(SALE + "ลูกค้า: เพื่อนบอกว่าไม่เอาแล้ว")
    assert "cancellation" not in types(a)
    assert not a.confirmed_sale and a.deal_status == "changed_needs_review"


@pytest.mark.parametrize("reply", ["เพื่อนบอกว่าไม่เอาแล้ว แต่ผมยังเอาตามเดิม", "แฟนบอกว่าแพงไป แต่ผมยังเอาครับ"])
def test_reaffirmation_after_third_party_speech_is_respected(reply):
    a = analyze(SALE + "ลูกค้า: " + reply)
    assert a.confirmed_sale
    assert "cancellation" not in types(a) and "customer_rejection" not in types(a)


# --- P2-01 negated or uncertain rescheduling ---------------------------------------------

@pytest.mark.parametrize("reply", ["ไม่เลื่อนนัดครับ ใช้วันเดิม", "ไม่เลื่อนครับ วันเดิมได้", "ไม่ได้เลื่อนนัดครับ", "ไม่ต้องเลื่อนนัดครับ"])
def test_negated_reschedule_keeps_the_slot(reply):
    a = analyze(BOOKED + "ลูกค้า: " + reply)
    assert "reschedule_request" not in types(a)
    assert all(s.metadata.get("slot_status") != "superseded" for s in a.signals)
    assert "appointment_time" not in missing(a)
    assert "reserve_or_attend_appointment" in open_values(a)


@pytest.mark.parametrize("reply", ["อาจจะเลื่อนนัดครับ ยังไม่ได้ยืนยันวันใหม่", "น่าจะต้องเลื่อนนัดครับ", "อาจเลื่อนครับ เดี๋ยวแจ้งอีกที"])
def test_uncertain_reschedule_keeps_the_slot_and_asks(reply):
    a = analyze(BOOKED + "ลูกค้า: " + reply)
    assert "reschedule_request" not in types(a)
    assert all(s.metadata.get("slot_status") != "superseded" for s in a.signals)
    assert "appointment_time" not in missing(a)
    assert "reserve_or_attend_appointment" in open_values(a)
    assert any(s.type == "possible_reschedule" for s in a.signals)
    assert evidence_backed(a, "confirm_appointment")


@pytest.mark.parametrize("reply", ["ไม่เลื่อนวันที่โอนมัดจำครับ ใช้วันเดิม", "ไม่เลื่อนวันโอนครับ"])
def test_negated_payment_reschedule_changes_nothing(reply):
    a = analyze(BOOKED + "ลูกค้า: " + reply)
    assert "payment_reschedule_request" not in types(a) and "confirm_payment_schedule" not in actions(a)
    assert "reschedule_request" not in types(a)
    assert "reserve_or_attend_appointment" in open_values(a)


@pytest.mark.parametrize("reply", ["ขอเลื่อนนัดเป็นวันอาทิตย์ 10:00 ครับ", "เลื่อนเป็นวันศุกร์ 13:00 ได้ไหมครับ"])
def test_genuine_reschedule_still_supersedes(reply):
    a = analyze(BOOKED + "ลูกค้า: " + reply)
    assert "reschedule_request" in types(a)
    assert any(s.metadata.get("slot_status") == "superseded" for s in a.signals)


def test_payment_reschedule_does_not_move_installation():
    a = analyze(BOOKED + "ลูกค้า: ขอเลื่อนวันโอนมัดจำเป็นวันศุกร์ครับ")
    assert "payment_reschedule_request" in types(a) and "reschedule_request" not in types(a)
    assert "reserve_or_attend_appointment" in open_values(a)


# --- P2-02 a completed delivery must match its object ------------------------------------

@pytest.mark.parametrize("reply", [
    "ส่งรูปให้แล้วครับ ส่วนใบเสนอราคาจะส่งพรุ่งนี้",
    "ส่งรูปให้แล้วครับ แต่ใบเสนอราคาจะส่งพรุ่งนี้",
    "ส่งราคาให้แล้วครับ ใบเสนอราคาจะส่งพรุ่งนี้",
    "ส่งสเปคให้แล้วครับ ใบเสนอราคาเดี๋ยวส่งตามครับ",
])
def test_delivery_of_another_object_keeps_quotation_open(reply):
    a = analyze(QUOTE_REQUEST + "ร้าน: " + reply)
    assert "quotation_sent" not in types(a)
    assert "send_quotation" in actions(a)
    assert "send_quotation" in open_values(a)


@pytest.mark.parametrize("reply", ["ส่งใบเสนอราคาให้แล้วครับ", "ส่งรูปกับใบเสนอราคาให้แล้วครับ", "แนบไฟล์ใบเสนอราคา PDF ให้แล้วครับ",
                                   "ใบเสนอราคาส่งให้แล้วครับ"])
def test_actual_document_delivery_closes_quotation(reply):
    a = analyze(QUOTE_REQUEST + "ร้าน: " + reply)
    assert "quotation_sent" in types(a)
    assert "send_quotation" not in actions(a)


def test_photo_delivery_is_still_information_sent():
    a = analyze("ลูกค้า: ขอรูปงานติดตั้งหน่อยครับ\nร้าน: ส่งรูปให้แล้วครับ ส่วนใบเสนอราคาจะส่งพรุ่งนี้")
    assert "information_sent" in types(a)


# --- P2-03 payment purpose, identity and partial amounts ---------------------------------

def _payment_open(a):
    return [s for s in open_commitments(a) if s.value in {"pay_deposit", "make_payment"}]


@pytest.mark.parametrize("report", ["โอนค่าอะไหล่ 5000 บาทแล้วครับ มัดจำยังค้างอยู่", "โอนค่าแรง 5000 บาทแล้วครับ ส่วนมัดจำยังไม่ได้โอน",
                                    "โอนค่าสำรวจ 5000 บาทแล้วครับ"])
def test_payment_for_another_purpose_keeps_deposit_open(report):
    a = analyze(DEPOSIT_PROMISE + "ลูกค้า: " + report)
    assert [s.value for s in _payment_open(a)] == ["pay_deposit"]
    assert "check_payment" in actions(a) and a.review_required


@pytest.mark.parametrize("repeat", ["โอน 1000 บาทแล้วครับ ยอดเดียวกับเมื่อกี้", "ที่โอน 1000 บาทเมื่อกี้คือยอดเดิมครับ",
                                    "โอน 1000 บาทแล้วครับ ยอดเดิมนะครับ", "แจ้งอีกรอบครับ โอน 1000 บาทแล้ว"])
def test_repeated_report_of_the_same_transfer_is_not_double_counted(repeat):
    a = analyze("ลูกค้า: จะโอนมัดจำ 2000 บาทพรุ่งนี้\nลูกค้า: โอนแล้ว 1000 บาทครับ\nลูกค้า: " + repeat)
    assert [s.value for s in _payment_open(a)] == ["pay_deposit"]
    assert any("partial_payment" in w for w in a.warnings)


def test_explicit_additional_transfer_is_distinct():
    a = analyze("ลูกค้า: จะโอนมัดจำ 2000 บาทพรุ่งนี้\nลูกค้า: โอนแล้ว 1000 บาทครับ\nลูกค้า: โอนเพิ่มอีก 1000 บาทแล้วครับ ครบแล้ว")
    assert _payment_open(a) == []
    assert "payment_reported_not_verified" in a.warnings and "check_payment" in actions(a)


@pytest.mark.parametrize("report", ["โอนแล้วครับ แต่ยังไม่ครบ", "โอนไปบางส่วนแล้วครับ", "โอนแล้วครับ ยังขาดอยู่นิดหน่อย"])
def test_incomplete_report_without_amount_keeps_tracking(report):
    a = analyze(DEPOSIT_PROMISE + "ลูกค้า: " + report)
    assert [s.value for s in _payment_open(a)] == ["pay_deposit"]
    assert any("partial_payment" in w for w in a.warnings)
    # No remaining amount is invented.
    assert not any(s.type == "customer_commitment" and s.metadata.get("purpose") == "remaining_balance" for s in a.signals)
    assert all(s.value.get("amount") != "0" for s in a.signals if s.type == "monetary_amount")


def test_known_partial_stays_open():
    a = analyze("ลูกค้า: จะโอนมัดจำ 2000 บาทพรุ่งนี้\nลูกค้า: โอนแล้ว 1000 บาทครับ")
    assert [s.value for s in _payment_open(a)] == ["pay_deposit"]


@pytest.mark.parametrize("report", ["โอนมัดจำ 5000 บาทแล้วครับ", "โอนแล้ว 5000 บาทครับ", "โอนแล้วครับ"])
def test_matching_full_report_closes_promise_but_stays_unverified(report):
    a = analyze(DEPOSIT_PROMISE + "ลูกค้า: " + report)
    assert _payment_open(a) == []
    assert "payment_reported_not_verified" in a.warnings and "check_payment" in actions(a)


# --- P2-04 arrival is not completion -----------------------------------------------------

@pytest.mark.parametrize("arrival", ["ช่างมาถึงแล้วครับ ยังไม่ได้เริ่มติดตั้ง", "ช่างมาถึงหน้างานแล้วครับ", "ช่างเข้าหน้างานแล้วครับ กำลังเริ่มงาน",
                                     "มาถึงแล้วครับ"])
def test_arrival_does_not_close_installation(arrival):
    a = analyze(BOOKED + "ร้าน: " + arrival)
    assert "appointment_completed" not in types(a)
    assert any(s.type == "technician_arrived" and s.evidence.text == arrival for s in a.signals)
    # The installation obligation is still tracked: arrival fulfils attendance, not the work.
    assert "reserve_or_attend_appointment" in open_values(a)


@pytest.mark.parametrize("done", ["ติดตั้งเสร็จแล้วครับ", "ติดตั้งเสร็จเรียบร้อยแล้วครับ", "ซ่อมเสร็จแล้วครับ"])
def test_real_completion_closes_installation(done):
    a = analyze(BOOKED + "ร้าน: " + done)
    assert "appointment_completed" in types(a)
    assert "reserve_or_attend_appointment" not in open_values(a)


@pytest.mark.parametrize("done", ["ยังติดตั้งไม่เสร็จครับ", "ยังไม่เสร็จครับ ติดตั้งอยู่", "ถ้าติดตั้งเสร็จแล้วจะแจ้งครับ", "ติดตั้งเสร็จแล้วมั้งครับ"])
def test_negated_conditional_or_uncertain_completion_keeps_tracking(done):
    a = analyze(BOOKED + "ร้าน: " + done)
    assert "appointment_completed" not in types(a)
    assert "reserve_or_attend_appointment" in open_values(a)


# --- P2-05 times belong to their event ---------------------------------------------------

@pytest.mark.parametrize("other", ["ผมว่างคุยโทรศัพท์วันนี้ 18:00 ครับ", "โทรหาผมได้ 18:00 ครับ", "สะดวกคุยทางไลน์ 20:00 ครับ"])
def test_time_for_a_call_is_not_the_installation_time(other):
    a = analyze("ร้าน: ราคา 18500 บาท นัดติดตั้งวันเสาร์\nลูกค้า: " + other)
    assert "appointment_time" in missing(a)


@pytest.mark.parametrize("time_msg", ["ลูกค้า: สะดวก 10:00 ครับ", "ลูกค้า: เข้ามาได้ 10:00 ครับ", "ร้าน: ช่างเข้า 10:00 นะครับ"])
def test_time_for_the_appointment_still_fills_the_slot(time_msg):
    a = analyze("ร้าน: ราคา 18500 บาท นัดติดตั้งวันเสาร์\n" + time_msg)
    assert "appointment_time" not in missing(a)


# --- P2-06 competitor prices -------------------------------------------------------------

@pytest.mark.parametrize("reply", ["ร้านอื่นราคา 18500 บาทครับ ร้านผมยังไม่ได้คิดราคา", "เจ้าอื่นเสนอ 18500 บาทครับ",
                                   "ที่อื่นขาย 18500 บาทครับ เดี๋ยวผมเช็กราคาให้"])
def test_competitor_price_is_not_our_opportunity(reply):
    a = analyze("ลูกค้า: ขอราคาแอร์ครับ\nร้าน: " + reply)
    money = [s.value for s in a.signals if s.type == "monetary_amount"]
    assert any(v["amount"] == "18500" and v["role"] == "competitor_price" for v in money)
    assert a.potential_revenue.amount is None


def test_customer_reported_competitor_price_is_kept():
    a = analyze("ลูกค้า: ร้านอื่นราคา 17000 บาทครับ")
    assert [s.value["role"] for s in a.signals if s.type == "monetary_amount"] == ["competitor_price"]


def test_later_own_price_supplies_the_amount():
    a = analyze("ลูกค้า: ขอราคาแอร์ครับ\nร้าน: ร้านอื่นราคา 18500 บาทครับ ร้านผมยังไม่ได้คิดราคา\nร้าน: ร้านเราราคา 17900 บาทครับ")
    assert a.potential_revenue.amount == "17900"


def test_own_price_in_the_same_message_as_competitor_price():
    a = analyze("ลูกค้า: ขอราคาแอร์ครับ\nร้าน: ร้านอื่น 18500 บาท ของเรา 17900 บาทครับ")
    roles = {s.value["amount"]: s.value["role"] for s in a.signals if s.type == "monetary_amount"}
    assert roles == {"18500": "competitor_price", "17900": "price"}
    assert a.potential_revenue.amount == "17900"


# --- P2-07 extractor boundary ------------------------------------------------------------

class FakeExtractor:
    name = "fake_adapter"

    def __init__(self, *signals):
        self.specs = signals

    def extract(self, messages):
        out = []
        for n, (index, kind, value, confidence) in enumerate(self.specs, 1):
            m = messages[index]
            out.append(Signal(f"f{n}", kind, m.actor, value, confidence, Evidence(m.id, m.speaker, m.text, m.raw_line)))
        return out


@pytest.mark.parametrize("value", [
    {"amount": "-1000", "currency": "USD", "role": "price", "raw": "-1000"},
    {"amount": "-1000", "currency": "THB", "role": "price", "raw": "-1000"},
    {"amount": "0", "currency": "THB", "role": "price", "raw": "0"},
    {"amount": "NaN", "currency": "THB", "role": "price", "raw": "NaN"},
    {"amount": "Infinity", "currency": "THB", "role": "price", "raw": "inf"},
    {"amount": "sNaN", "currency": "THB", "role": "price", "raw": "x"},
    {"amount": float("nan"), "currency": "THB", "role": "price", "raw": "x"},
    {"amount": "1,000", "currency": "THB", "role": "price", "raw": "1,000"},
    {"amount": "1000", "currency": "THB", "role": "invented_role", "raw": "1000"},
    {"amount": "1000", "currency": "", "role": "price", "raw": "1000"},
    {"amount": "1000", "role": "price", "raw": "1000"},
    {},
    "1000",
    None,
    [1000],
])
def test_invalid_monetary_values_are_rejected_clearly(value):
    with pytest.raises(ValueError, match="monetary_amount"):
        analyze("ร้าน: ราคา 1000 USD", extractor=FakeExtractor((0, "monetary_amount", value, 0.95)))


def test_usd_amount_is_never_relabelled_thb():
    value = {"amount": "1000", "currency": "USD", "role": "price", "raw": "1000"}
    a = analyze("ร้าน: ราคา 1000 USD", extractor=FakeExtractor((0, "commercial_intent", "commercial_discussion", 0.9),
                                                               (0, "monetary_amount", value, 0.95)))
    assert a.potential_revenue.amount is None or a.potential_revenue.currency == "USD"
    assert a.potential_revenue.currency != "THB" or a.potential_revenue.amount is None


@pytest.mark.parametrize("kind, value", [
    ("schedule", {}), ("schedule", {"raw": "พรุ่งนี้", "kind": "weekday", "resolved_date": None, "resolution": "x"}),
    ("deadline", {"raw": "พรุ่งนี้", "kind": "date", "resolved_date": "2026-13-40", "resolution": "resolved"}),
    ("deadline", "พรุ่งนี้"),
    ("customer_commitment", {"amount": 5}), ("customer_commitment", ""), ("customer_acceptance", 3),
])
def test_invalid_values_of_other_types_are_rejected(kind, value):
    with pytest.raises(ValueError, match=kind):
        analyze("ลูกค้า: พรุ่งนี้โอนครับ", extractor=FakeExtractor((0, kind, value, 0.92)))


@pytest.mark.parametrize("meta_case", ["amount", "offer"])
def test_invalid_metadata_references_are_rejected(meta_case):
    class BadMeta(FakeExtractor):
        def extract(self, messages):
            m = messages[0]
            meta = {"amount": "-5"} if meta_case == "amount" else {"offer_message_id": 99}
            kind = "customer_commitment" if meta_case == "amount" else "possible_acceptance"
            value = "pay_deposit" if meta_case == "amount" else "ambiguous_agreement"
            return [Signal("f1", kind, m.actor, value, 0.7, Evidence(m.id, m.speaker, m.text, m.raw_line), meta)]
    with pytest.raises(ValueError):
        analyze("ลูกค้า: พรุ่งนี้โอนครับ", extractor=BadMeta())


def test_contradicted_high_confidence_acceptance_goes_to_review():
    a = analyze("ลูกค้า: ขอคิดดูก่อนครับ",
                extractor=FakeExtractor((0, "customer_acceptance", "explicit_acceptance", 0.99)))
    assert not a.confirmed_sale
    assert a.review_required and a.deal_status == "acceptance_needs_review"
    assert evidence_backed(a, "confirm_deal_status")
    assert any("acceptance_contradicted_by_evidence" in w for w in a.warnings)


@pytest.mark.parametrize("text", ["ลูกค้า: ไม่เอาครับ", "ลูกค้า: ถ้าลดได้เอาครับ", "ลูกค้า: เอาไหมนะ", "ลูกค้า: เอาครับมั้ง",
                                  "ลูกค้า: เพื่อนบอกว่าเอา"])
def test_adapter_acceptance_must_survive_the_rule_cross_check(text):
    a = analyze(text, extractor=FakeExtractor((0, "customer_acceptance", "explicit_acceptance", 0.99)))
    assert not a.confirmed_sale and a.review_required


def test_valid_adapter_still_works():
    price = {"amount": "18500", "currency": "THB", "role": "price", "raw": "18500"}
    a = analyze("ร้าน: ราคา 18500 บาท\nลูกค้า: ยืนยันตามราคานี้ครับ",
                extractor=FakeExtractor((0, "commercial_intent", "commercial_discussion", 0.9), (0, "monetary_amount", price, 0.96),
                                        (1, "customer_acceptance", "explicit_acceptance", 0.96)))
    assert a.confirmed_sale and a.potential_revenue.amount == "18500"


def test_rule_extractor_output_passes_value_validation_on_every_dataset():
    import json
    from pathlib import Path
    for path in sorted((Path(__file__).parent.parent / "data").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            analyze(json.loads(line)["conversation"])  # raises on any invalid value


def test_readme_no_longer_claims_evidence_proves_semantics():
    from pathlib import Path
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    assert "do not prove" in readme or "does not prove" in readme


# --- P2-08 redaction placeholders --------------------------------------------------------

BOOKING = "ร้าน: นัดติดตั้งวันเสาร์ 09:00\nลูกค้า: "


@pytest.mark.parametrize("placeholder", ["[ที่อยู่]", "ที่อยู่: [ที่อยู่]", "[ADDRESS]", "[address]", "<ที่อยู่>", "[พิกัด]", "[ลิงก์แผนที่]"])
def test_address_placeholder_counts_as_present(placeholder):
    assert "installation_address" not in missing(analyze(BOOKING + placeholder))


def test_redaction_invariance_for_address():
    raw = analyze(BOOKING + "https://maps.app.goo.gl/synthetic-audit")
    redacted = analyze(BOOKING + "[ที่อยู่]")
    assert missing(raw) == missing(redacted)
    assert actions(raw) == actions(redacted)
    assert raw.confirmed_sale == redacted.confirmed_sale and raw.deal_status == redacted.deal_status


@pytest.mark.parametrize("raw, redacted", [
    ("ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ โทร 0890000000", "ร้าน: ราคา 18500 บาท\nลูกค้า: เอาครับ โทร [เบอร์]"),
    ("ลูกค้า: ผมชื่อสมชาย ขอราคาแอร์ครับ", "ลูกค้า: ผมชื่อ[ชื่อลูกค้า] ขอราคาแอร์ครับ"),
    ("ร้าน: โอนมาที่บัญชี 1234567890 ได้เลยครับ\nลูกค้า: เดี๋ยวเย็นนี้โอนมัดจำ 5000 บาท",
     "ร้าน: โอนมาที่บัญชี [บัญชี] ได้เลยครับ\nลูกค้า: เดี๋ยวเย็นนี้โอนมัดจำ 5000 บาท"),
])
def test_redaction_invariance_for_other_placeholders(raw, redacted):
    a, b = analyze(raw), analyze(redacted)
    assert actions(a) == actions(b) and missing(a) == missing(b)
    assert a.confirmed_sale == b.confirmed_sale and a.potential_revenue.amount == b.potential_revenue.amount


def test_placeholder_in_a_request_is_not_an_address():
    a = analyze(BOOKING + "ขอ[ที่อยู่]ร้านหน่อยครับ")
    assert "installation_address" in missing(a)


def test_no_address_at_all_is_still_missing():
    assert "installation_address" in missing(analyze(BOOKING + "ได้ครับ"))


# --- whole-conversation invariants -------------------------------------------------------

def test_confidences_finite_everywhere():
    a = analyze(SALE + "ลูกค้า: เพื่อนบอกว่าดี แต่ผมไม่ซื้อครับ")
    assert all(math.isfinite(s.confidence) for s in a.signals)


@pytest.mark.parametrize("reply", ["ถ้าวันเสาร์ไม่ได้ก็ไม่เป็นไรครับ เอาครับ", "ตกลงจ้างครับ ถ้าวันเสาร์ไม่ว่างก็ไม่เป็นไร"])
def test_closed_conditional_does_not_hide_a_genuine_acceptance(reply):
    assert analyze(PRICE + "ลูกค้า: " + reply).confirmed_sale


# --- P2-10 evaluation ---------------------------------------------------------------------

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from chat2work.evaluation.harness import evaluate, evaluate_actions

ROOT = Path(__file__).resolve().parents[1]


def _scenario(tmp_path, conversation, **expected):
    base = {"confirmed_sale": False, "required_actions": [], "forbidden_actions": [], "open_obligations": []}
    case = {"id": "t", "industry": "repair", "synthetic": True, "tags": expected.pop("tags", []),
            "conversation": conversation, "expected": {**base, **expected}}
    path = tmp_path / "t_scenarios.jsonl"
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_structured_obligation_checks_amount_and_purpose(tmp_path):
    conv = "ลูกค้า: จะโอนมัดจำ 2000 บาทพรุ่งนี้"
    ok = {"value": "pay_deposit", "actor": "customer", "amount": "2000", "purpose": "deposit", "deadline": ["พรุ่งนี้"]}
    assert evaluate_actions(_scenario(tmp_path, conv, open_obligations=[ok]))["action_case_accuracy"] == 1
    for wrong in ({**ok, "amount": "1000"}, {**ok, "actor": "business"}, {**ok, "purpose": "ค่าอะไหล่"}, {**ok, "deadline": []}):
        assert evaluate_actions(_scenario(tmp_path, conv, open_obligations=[wrong]))["action_case_accuracy"] == 0
    # Legacy value-only labels still work.
    assert evaluate_actions(_scenario(tmp_path, conv, open_obligations=["pay_deposit"]))["action_case_accuracy"] == 1


def test_safety_failure_and_silent_sale_drop_fail_the_gate(tmp_path):
    path = _scenario(tmp_path, "ร้าน: ราคา 18500 บาทครับ\nลูกค้า: ขอบคุณครับ", confirmed_sale=True, tags=["genuine_sale"])
    report = evaluate_actions(path)
    assert report["genuine_sales_dropped_without_review"] == 1 and report["safety_case_failures"] == 1
    proc = subprocess.run([sys.executable, str(ROOT / "evaluate.py"), "--dataset", str(path), "--check"], capture_output=True, text=True)
    gates = json.loads(proc.stdout)[0]["failed_gates"]
    assert proc.returncode == 1 and "genuine sale dropped without review" in gates and "safety scenario failed" in gates


def test_optional_money_and_opportunity_labels_are_scored(tmp_path):
    conv = "ลูกค้า: ขอราคาแอร์ครับ\nร้าน: ร้านอื่นราคา 18500 บาทครับ"
    good = _scenario(tmp_path, conv, potential_revenue=None, amount_roles=[["18500", "competitor_price"]])
    assert evaluate_actions(good)["action_case_accuracy"] == 1
    bad = _scenario(tmp_path, conv, potential_revenue="18500")
    assert evaluate_actions(bad)["action_case_accuracy"] == 0


def test_label_reports_count_silent_sale_drops():
    for path in sorted((ROOT / "data").glob("*.jsonl")):
        if not path.name.endswith("scenarios.jsonl"):
            assert evaluate(path)["genuine_sales_dropped_without_review"] == 0


def test_safety_scenarios_are_frozen_and_pass():
    path = ROOT / "data/safety_scenarios.jsonl"
    first = json.loads((ROOT / "data/blind_first_runs.json").read_text(encoding="utf-8"))["safety_scenarios.jsonl"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first["labels_frozen_sha256"]
    report = evaluate_actions(path)
    assert report["safety_case_failures"] == 0 and report["false_confirmed_sales"] == 0
    assert report["genuine_sales_dropped_without_review"] == 0
