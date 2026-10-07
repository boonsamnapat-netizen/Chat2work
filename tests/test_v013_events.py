"""v0.1.3: event-classification regressions for the nine problem groups found in the review of 3ae8778.

Each family checks WHAT an event targets and WHETHER its clause is asserted (vs negated, conditional,
future, questioned, reported or uncertain) before state changes or obligations close.
Natural variants and positive controls are included. Review-derived development coverage only.
"""
import pytest

from chat2work import analyze
from chat2work.extractors.semantics import classify_clause, clauses


def types(a):
    return {s.type for s in a.signals}


def actions(a):
    return {x.type for x in a.recommended_actions}


def missing(a):
    return {s.value for s in a.missing_information}


def open_commitments(a):
    by_id = {s.id: s for s in a.signals}
    return [by_id[i] for x in a.recommended_actions if x.type == "track_commitment" for i in x.signal_ids]


SALE = "ร้าน: ราคา 18500 บาทครับ\nลูกค้า: เอาครับ\n"
BOOKED = "ร้าน: ราคา 18500 บาท จะเข้าติดตั้งวันเสาร์ 09:00\n"


# --- semantic layer unit tests -------------------------------------------------------------

@pytest.mark.parametrize("text, target, status", [
    ("ส่งใบเสนอราคาแล้วครับ", "ส่งใบเสนอราคา", "asserted"),
    ("ถ้าส่งใบเสนอราคาแล้วจะโทรแจ้งครับ", "ส่งใบเสนอราคา", "conditional"),
    ("พรุ่งนี้จะส่งใบเสนอราคา แล้วโทรแจ้งครับ", "ส่งใบเสนอราคา", "future"),
    ("ส่งใบเสนอราคาแล้วใช่ไหมครับ", "ส่งใบเสนอราคา", "questioned"),
    ("ติดตั้งเสร็จแล้วมั้งครับ", "ติดตั้งเสร็จ", "uncertain"),
    ("ยังไม่ได้ส่งใบเสนอราคาครับ", "ส่งใบเสนอราคา", "negated"),
    ("เพื่อนบอกว่าไม่ซื้อแล้ว", "ไม่ซื้อ", "reported"),
    ("ขอโทษครับ ไม่จ้างครับ", "ไม่จ้าง", "asserted"),
])
def test_clause_status(text, target, status):
    assert classify_clause(text, text.index(target)) == status


def test_clauses_split_on_spaces_and_conjunctions():
    parts = [c.text for c in clauses("โอนแล้ว 1000 บาท ที่เหลืออีก 4000 จะโอนพรุ่งนี้")]
    assert "ที่เหลืออีก 4000 จะโอนพรุ่งนี้" in " ".join(parts) and len(parts) >= 2


# --- 1. information offers in plain statement form ---------------------------------------------

@pytest.mark.parametrize("offer", ["ส่งแคตตาล็อกให้ครับ", "ส่งรูปให้ครับ", "ส่งสเปคให้นะคะ", "แนบลิงก์ผลงานให้ครับ", "ผมส่งแคตตาล็อกให้นะครับ"])
@pytest.mark.parametrize("reply", ["เอาครับ", "ได้ครับ", "โอเคจ้า", "เอาค่ะ ขอบคุณค่ะ"])
def test_plain_information_statement_is_never_a_sale(offer, reply):
    a = analyze(f"ร้าน: {offer}\nลูกค้า: {reply}")
    assert not a.confirmed_sale and "customer_acceptance" not in types(a)


@pytest.mark.parametrize("text", [
    "ร้าน: ส่งรูปให้แล้วครับ ราคา 18,500 บาท\nลูกค้า: เอาครับ",
    "ร้าน: ส่งแคตตาล็อกให้ครับ\nลูกค้า: ยืนยันตามราคานี้ครับ",
    "ร้าน: ส่งแคตตาล็อกให้ครับ\nร้าน: รุ่นนี้ 18,500 บาท เอาเลยไหมครับ\nลูกค้า: เอาครับ",
])
def test_purchase_controls_near_information_statements(text):
    assert analyze(text).confirmed_sale


# --- 2. explicit refusal after an accepted sale ---------------------------------------------------

@pytest.mark.parametrize("refusal", [
    "ผมไม่ซื้อครับ", "ขอโทษครับ ไม่จ้างครับ", "ไม่ซื้อครับ ขอบคุณที่ส่งรูปมาแล้วนะครับ", "หนูไม่เอาแล้วค่ะ",
    "เราไม่จ้างแล้วนะครับ", "ขอบคุณครับ แต่ผมไม่ซื้อครับ", "ไม่ตกลงครับ ราคาสูงไป",
])
def test_explicit_refusal_revokes_accepted_sale(refusal):
    a = analyze(SALE + "ลูกค้า: " + refusal)
    assert not a.confirmed_sale and a.deal_status in {"declined", "cancelled"}
    assert any(s.type == "customer_acceptance" for s in a.signals)


def test_refusal_split_across_messages():
    a = analyze(SALE + "ลูกค้า: ขอโทษนะครับ\nลูกค้า: ไม่จ้างแล้วครับ")
    assert not a.confirmed_sale


@pytest.mark.parametrize("not_refusal", [
    "ถ้าแพงกว่านี้ผมไม่ซื้อนะครับ", "ไม่ซื้อที่อื่นแน่นอนครับ", "แฟนบอกว่าไม่ซื้อ แต่ผมยังซื้อนะ",
    "ไม่ซื้อเพิ่มแล้วครับ ขอแค่ชุดนี้", "จะไม่ซื้อได้ยังไงครับ", "ไม่ต้องลดครับ",
])
def test_conditional_competitor_reported_or_rhetorical_refusal_keeps_sale(not_refusal):
    assert analyze(SALE + "ลูกค้า: " + not_refusal).confirmed_sale


# --- 3. conditional / future / questioned document events ------------------------------------------

REQUEST = "ลูกค้า: ขอใบเสนอราคา PDF ครับ\n"


@pytest.mark.parametrize("event", [
    "ร้าน: ถ้าส่งใบเสนอราคาแล้วจะโทรแจ้งครับ", "ร้าน: พรุ่งนี้จะส่งใบเสนอราคา แล้วโทรแจ้งครับ",
    "ร้าน: ส่งใบเสนอราคาแล้วใช่ไหมครับ", "ลูกค้า: ถ้าได้รับใบเสนอราคาแล้วจะส่งให้ฝ่ายบัญชีครับ",
    "ร้าน: น่าจะส่งใบเสนอราคาแล้วนะครับ", "ร้าน: ยังไม่ได้ส่งใบเสนอราคาครับ", "ลูกค้า: ได้รับใบเสนอราคาหรือยังนะ",
    "ร้าน: เดี๋ยวส่งใบเสนอราคาแล้วจะแจ้งครับ",
])
def test_non_asserted_document_event_keeps_request_open(event):
    a = analyze(REQUEST + event)
    assert not types(a) & {"quotation_sent", "quotation_received"}
    assert "send_quotation" in actions(a)


@pytest.mark.parametrize("event", ["ร้าน: ส่งใบเสนอราคาแล้วครับ", "ร้าน: ผมส่งใบเสนอราคา PDF ให้แล้วนะครับ", "ลูกค้า: ได้รับใบเสนอราคาแล้วครับ", "ร้าน: แนบใบเสนอราคาไปทางอีเมลแล้ว แล้วโทรแจ้งด้วยครับ"])
def test_asserted_document_delivery_closes_request(event):
    assert "send_quotation" not in actions(analyze(REQUEST + event))


# --- 4. deferral and later go-ahead -------------------------------------------------------------------

def test_deferral_of_promised_quotation_has_no_send_now_action():
    a = analyze("ร้าน: เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้ครับ\nลูกค้า: เอาครับ แต่ยังไม่ต้องส่งครับ")
    assert "send_quotation" not in actions(a) and "schedule_follow_up" not in actions(a)
    hold = next(x for x in a.recommended_actions if x.type == "await_customer_go_ahead")
    by_id = {s.id: s for s in a.signals}
    assert any(by_id[i].type == "business_commitment" for i in hold.signal_ids)  # obligation preserved


@pytest.mark.parametrize("text", ["ลูกค้า: ขอใบเสนอราคา PDF ครับ แต่ยังไม่ต้องส่งตอนนี้", "ลูกค้า: ยังไม่ต้องส่งตอนนี้นะครับ ไว้ค่อยขอใบเสนอราคาทีหลัง"])
def test_deferral_inside_the_request(text):
    a = analyze(text)
    assert "send_quotation" not in actions(a) and "await_customer_go_ahead" in actions(a)


@pytest.mark.parametrize("go", ["ส่งแคตตาล็อกมาได้แล้วครับ", "ตอนนี้ส่งแคตตาล็อกมาได้เลยครับ", "ขอแคตตาล็อกตอนนี้เลยครับ"])
def test_go_ahead_reopens_send_information(go):
    a = analyze("ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: เอาครับ แต่ยังไม่ต้องส่งครับ\nลูกค้า: " + go)
    assert "send_offered_information" in actions(a) and "await_customer_go_ahead" not in actions(a)


def test_go_ahead_reopens_deferred_quotation_promise():
    a = analyze("ร้าน: เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้ครับ\nลูกค้า: เอาครับ แต่ยังไม่ต้องส่งครับ\nลูกค้า: ส่งใบเสนอราคามาได้แล้วครับ")
    assert "send_quotation" in actions(a) and "await_customer_go_ahead" not in actions(a)


# --- 5. conditional and partial payments --------------------------------------------------------------

PROMISED = "ลูกค้า: เดี๋ยวเย็นนี้โอนมัดจำ 5000 บาท\n"


@pytest.mark.parametrize("text", ["ถ้าโอนแล้วจะส่งสลิปให้ครับ", "พอโอนแล้วจะแจ้งนะครับ", "โอนแล้วหรือยังนะ ไม่แน่ใจ", "จะส่งสลิปให้ครับ"])
def test_non_asserted_payment_report_keeps_commitment(text):
    a = analyze(PROMISED + "ลูกค้า: " + text)
    assert "payment_reported" not in types(a)
    assert any(c.value == "pay_deposit" for c in open_commitments(a))


def test_partial_payment_preserves_remaining_commitment_and_deadline():
    a = analyze(PROMISED + "ลูกค้า: โอนแล้ว 1000 บาท ที่เหลืออีก 4000 จะโอนพรุ่งนี้")
    reported = next(s for s in a.signals if s.type == "payment_reported")
    assert reported.metadata["verified"] is False and reported.metadata.get("reported_amount") == "1000"
    remaining = [c for c in open_commitments(a) if c.metadata.get("amount") == "4000"]
    assert remaining and remaining[0].metadata.get("purpose") == "remaining_balance"
    deadlines = {s.value["raw"] for s in a.signals if s.type == "deadline" and s.evidence.message_id == 1}
    assert "พรุ่งนี้" in deadlines and "schedule_follow_up" in actions(a) and "check_payment" in actions(a)


def test_partial_report_without_remainder_keeps_original_open():
    a = analyze(PROMISED + "ลูกค้า: โอนแล้ว 1000 บาทครับ")
    assert any(c.value == "pay_deposit" for c in open_commitments(a))
    assert any("partial_payment_reported" in w for w in a.warnings)


def test_full_payment_report_closes_commitment():
    a = analyze(PROMISED + "ลูกค้า: โอนแล้วครับ")
    assert not open_commitments(a) and "check_payment" in actions(a)


# --- 6. rescheduling another event -------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "ขอเลื่อนส่งรูปไปพรุ่งนี้ครับ", "ขอเลื่อนวันที่โอนมัดจำไปวันศุกร์ครับ", "ขอเลื่อนวันส่งใบเสนอราคาเป็นวันศุกร์ครับ",
    "ขอเลื่อนส่งแคตตาล็อกเป็นอาทิตย์หน้านะคะ", "เลื่อนการชำระเงินไปสิ้นเดือนได้ไหม",
])
def test_rescheduling_another_event_keeps_installation(text):
    a = analyze(BOOKED + "ลูกค้า: " + text)
    booking = next(s for s in a.signals if s.type == "business_commitment" and s.value == "reserve_or_attend_appointment")
    assert booking.metadata.get("slot_status") != "superseded"
    assert "appointment_time" not in missing(a) and "reschedule_request" not in types(a)


@pytest.mark.parametrize("text", ["ขอเลื่อนนัดติดตั้งเป็นวันศุกร์ครับ", "ขอเลื่อนเป็นวันอาทิตย์ครับ", "ขอเลื่อนวันติดตั้งไปวันจันทร์"])
def test_rescheduling_the_installation_still_supersedes(text):
    a = analyze(BOOKED + "ลูกค้า: " + text)
    assert next(s for s in a.signals if s.type == "business_commitment").metadata.get("slot_status") == "superseded"


# --- 7. money roles ------------------------------------------------------------------------------------

@pytest.mark.parametrize("revision, net", [("ลดให้เหลือ 17000 บาท", "17000"), ("ลดเหลือ 17,000 บาทครับ", "17000"), ("ลดให้ 1,500 เหลือ 17,000 บาท", "17000")])
def test_revised_net_price_replaces_total(revision, net):
    a = analyze("ร้าน: ราคารวม 18500 บาท\nร้าน: " + revision)
    assert a.potential_revenue.amount == net


def test_plain_discount_amount_is_not_the_price():
    a = analyze("ร้าน: ราคารวม 18500 บาท\nร้าน: ลดให้ 1,500 บาทครับ")
    assert a.potential_revenue.amount == "18500"
    assert [s.value["role"] for s in a.signals if s.type == "monetary_amount"][-1] == "discount"


@pytest.mark.parametrize("component", ["รวมค่าแรงไว้แล้ว 1500 บาท", "รวมค่าส่งแล้ว 300 บาท", "ค่าแรง 1500 บาท รวมไว้ในราคาแล้ว"])
def test_included_component_never_replaces_price(component):
    a = analyze("ร้าน: ราคา 18500 บาท\nร้าน: " + component)
    assert a.potential_revenue.amount == "18500"


def test_total_that_includes_labor_is_still_the_total():
    a = analyze("ร้าน: ราคานี้รวมค่าแรงแล้ว 18,500 บาท")
    assert a.potential_revenue.amount == "18500"


# --- 8. uncertain completion --------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["ติดตั้งเสร็จแล้วมั้งครับ", "ติดตั้งเสร็จแล้วน่าจะนะครับ", "คิดว่าติดตั้งเสร็จแล้วครับ", "ไม่แน่ใจว่าติดตั้งเสร็จแล้วหรือยัง", "ติดตั้งเสร็จแล้วมั๊ง"])
def test_uncertain_completion_keeps_tracking_and_asks_to_verify(text):
    a = analyze(BOOKED + "ร้าน: " + text)
    assert "appointment_completed" not in types(a)
    assert "track_commitment" in actions(a) and "verify_completion" in actions(a)


@pytest.mark.parametrize("text", ["ติดตั้งเสร็จแล้วครับ", "ติดตั้งเสร็จเรียบร้อยแล้วครับ ขอบคุณครับ"])
def test_asserted_completion_still_closes(text):
    a = analyze(BOOKED + "ร้าน: " + text)
    assert "appointment_completed" in types(a) and "track_commitment" not in actions(a)


# --- 9. cancelling a document is not cancelling the purchase ---------------------------------------------

@pytest.mark.parametrize("text", ["ยกเลิกใบเสนอราคาครับ แต่ยังซื้อสินค้าเหมือนเดิม", "ยกเลิกใบเสนอราคานะครับ", "ไม่เอาใบเสนอราคาแล้วครับ"])
def test_cancelling_a_document_withdraws_only_the_document(text):
    a = analyze(SALE + "ลูกค้า: ขอส่งใบเสนอราคาให้หน่อย\nลูกค้า: " + text)
    assert a.confirmed_sale and a.deal_status == "accepted" and "send_quotation" not in actions(a)
    assert any(s.type == "quotation_declined" for s in a.signals)


def test_cancelling_other_information_keeps_sale_and_quotation_request():
    a = analyze(SALE + "ลูกค้า: ขอส่งใบเสนอราคาให้หน่อย\nลูกค้า: ยกเลิกการส่งแคตตาล็อกครับ")
    assert a.confirmed_sale and "send_quotation" in actions(a)


@pytest.mark.parametrize("text", ["ยกเลิกออเดอร์ครับ", "ขอยกเลิกครับ", "ยกเลิกทั้งหมดครับ ไม่ต้องส่งใบเสนอราคาแล้ว"])
def test_cancelling_the_order_still_cancels(text):
    a = analyze(SALE + "ลูกค้า: " + text)
    assert a.deal_status == "cancelled"


def test_remaining_balance_inherits_deposit_purpose():
    a = analyze("ลูกค้า: จะโอนมัดจำ 8,000 บาทพรุ่งนี้\nลูกค้า: โอนไปแล้ว 3,000 บาท ที่เหลือ 5,000 จะโอนวันเสาร์")
    remaining = [c for c in open_commitments(a) if c.metadata.get("purpose") == "remaining_balance"]
    assert [c.value for c in remaining] == ["pay_deposit"] and remaining[0].metadata["amount"] == "5000"


# --- natural-variant probes (found after the first fixes) --------------------------------------

@pytest.mark.parametrize("reply", ["เอาจ้า", "เอาคับ", "เอาค่า"])
def test_informal_acceptance_after_price(reply):
    assert analyze("ร้าน: ราคา 2,500 บาทครับ\nลูกค้า: " + reply).confirmed_sale


def test_informal_acceptance_of_information_is_not_a_sale():
    assert not analyze("ร้าน: เดี๋ยวส่งรูปให้น้า\nลูกค้า: เอาจ้า").confirmed_sale


@pytest.mark.parametrize("text, kind", [("ลูกค้า: โอนละนะคะ", "payment_reported"), ("ร้าน: ติดตั้งเสร็จละครับ", "appointment_completed")])
def test_colloquial_la_marks_completion(text, kind):
    a = analyze("ลูกค้า: เดี๋ยวโอนมัดจำ 3000 นะ\n" + BOOKED + text)
    assert kind in types(a)


def test_payment_notice_is_not_decision_pending():
    a = analyze("ลูกค้า: เดี๋ยวโอนมัดจำ 3000 นะ\nลูกค้า: หากโอนเรียบร้อยแล้วจะแจ้งอีกทีค่ะ")
    assert not a.decision_pending and "payment_reported" not in types(a)


def test_thanks_answers_an_information_offer():
    a = analyze("ร้าน: ส่งแคตตาล็อกให้ครับ\nลูกค้า: ขอบคุณครับ\nร้าน: รุ่นนี้ 9,900 บาท\nลูกค้า: เอาครับ")
    assert a.confirmed_sale
