"""v0.1.1 safety patch: regressions for the five defects in the independent review of 7c6a8fd.

These are review-derived regression cases, not a blind benchmark.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from chat2work import analyze

ROOT = Path(__file__).resolve().parents[1]


def types(a):
    return {s.type for s in a.signals}


def actions(a):
    return {x.type for x in a.recommended_actions}


def missing(a):
    return {s.value for s in a.missing_information}


# --- 1. informational acceptance must not become a confirmed sale -----------

INFORMATIONAL = [
    # the four review reproductions
    "ร้าน: รับแคตตาล็อกพร้อมราคาไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: ให้ส่งรูปแอร์ 18000 BTU ให้ดูไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: ราคา 18500 บาทครับ ให้ส่งใบเสนอราคาให้ไหม\nลูกค้า: เอาครับ",
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: เอาครับ ส่งมาเลย",
    # prices, quantities and specifications inside the informational offer
    "ร้าน: แคตตาล็อกรุ่น 12000 BTU ราคา 15,900 บาท ส่งให้ดูไหมครับ\nลูกค้า: เอาครับ ขอบคุณครับ",
    "ร้าน: ขอส่งตัวอย่างงานพิมพ์ 500 ใบให้ดูไหมครับ\nลูกค้า: เอาค่ะ",
    "ร้าน: ส่งสเปคแผง 550 วัตต์ 10 แผง ให้ดูก่อนไหมครับ\nลูกค้า: ได้ครับ ส่งมาเลย",
    "ร้าน: แพ็กเกจ 25,000 บาท มีรายละเอียดเป็น PDF ส่งให้ไหมครับ\nลูกค้า: ตกลงครับ",
    # expanded replies
    "ร้าน: ส่งรูปผลงานให้ดูไหมครับ\nลูกค้า: เอาครับ ส่งมาทางไลน์เลย",
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: ส่งมาเลยครับ",
    "ร้าน: ให้ส่งใบเสนอราคาให้ไหมครับ\nลูกค้า: เอาเลยครับ จะได้เอาไปเสนอหัวหน้า",
    # intervening messages
    "ร้าน: ราคา 18,500 บาทครับ\nร้าน: ส่งสเปคให้ดูไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: ส่งใบเสนอราคาให้ไหมครับ\nลูกค้า: แป๊บนะครับ\nลูกค้า: เอาครับ",
]


@pytest.mark.parametrize("text", INFORMATIONAL)
def test_accepting_information_is_not_a_sale(text):
    a = analyze(text)
    assert not a.confirmed_sale
    assert "customer_acceptance" not in types(a)
    accepted = [s for s in a.signals if s.type == "information_accepted"]
    assert accepted and accepted[-1].actor == "customer"
    assert accepted[-1].evidence.raw_line == text.splitlines()[-1]
    offer = accepted[-1].metadata["offer_message_id"]
    assert a.messages[offer].actor == "business"


@pytest.mark.parametrize("text", [
    "ร้าน: ราคา 18500 บาทครับ ให้ส่งใบเสนอราคาให้ไหม\nลูกค้า: เอาครับ",
    "ร้าน: ให้ส่งใบเสนอราคาให้ไหมครับ\nลูกค้า: เอาเลยครับ จะได้เอาไปเสนอหัวหน้า",
])
def test_accepted_quotation_offer_becomes_quotation_request(text):
    a = analyze(text)
    assert "quotation_request" in types(a) and "send_quotation" in actions(a)
    assert not any(s.type == "business_commitment" for s in a.signals)


def test_accepted_catalog_proposes_sending_it():
    a = analyze("ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: เอาครับ ส่งมาเลย")
    action = next(x for x in a.recommended_actions if x.type == "send_offered_information")
    assert {e.message_id for e in action.evidence} == {0, 1}


@pytest.mark.parametrize("text", [
    "ร้าน: จะเอาตัวนี้เลยไหม หรือให้ส่งรูปให้ดูก่อน\nลูกค้า: เอาครับ",
    "ร้าน: ราคา 18,500 บาท ตกลงสั่งไหมครับ หรือขอแคตตาล็อกก่อน\nลูกค้า: ได้ครับ",
])
def test_mixed_purchase_and_information_question_needs_review(text):
    a = analyze(text)
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance" and a.review_required
    s = next(s for s in a.signals if s.type == "possible_acceptance")
    assert s.confidence < 0.80 and s.metadata["offer_message_id"] == 0


def test_declining_information_is_not_declining_the_deal():
    a = analyze("ร้าน: ราคา 18,500 บาท\nร้าน: ส่งแคตตาล็อกให้ดูไหมครับ\nลูกค้า: ไม่เอาครับ")
    assert a.deal_status != "declined" and a.potential_revenue.amount == "18500"


@pytest.mark.parametrize("text", [
    "ร้าน: ราคา 18500 บาทครับ\nลูกค้า: ยืนยันตามราคานี้ครับ",
    "ร้าน: เอาตัวนี้ราคา 18500 บาทไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: ราคา 18500 บาทครับ\nลูกค้า: เอาครับ",
    "ร้าน: ตกลงสั่งรุ่นนี้ไหมครับ\nลูกค้า: เอาครับ ส่งมาเลย",
    "ร้าน: ราคา 9,000 บาท รับไหมครับ\nลูกค้า: เอาครับ",
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: ไม่ต้องครับ ยืนยันสั่งซื้อรุ่นเดิมเลย",
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: เอาครับ\nร้าน: ราคา 18,500 บาท\nลูกค้า: ยืนยันตามราคานี้ครับ",
])
def test_explicit_purchase_acceptance_still_confirms(text):
    a = analyze(text)
    assert a.confirmed_sale and a.deal_status == "accepted"


@pytest.mark.parametrize("text", [
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: แฟนบอกว่าเอาครับ",
    "ร้าน: ราคา 18,500 บาท\nลูกค้า: ถ้าลดได้ เอาครับ",
    "ร้าน: ส่งรูปให้ดูไหม\nคุณนก: เอาครับ",
])
def test_reported_conditional_and_unknown_still_not_sale(text):
    assert not analyze(text).confirmed_sale


# --- 2. quotation request after a numeric price --------------------------------

def test_quotation_document_request_after_price_proposes_quotation():
    a = analyze("ร้าน: ราคา 18500 บาทครับ\nลูกค้า: ขอใบเสนอราคาเป็น PDF หน่อยครับ")
    action = next(x for x in a.recommended_actions if x.type == "send_quotation")
    request = next(s for s in a.signals if s.type == "quotation_request")
    assert action.signal_ids == (request.id,) and action.evidence[0].message_id == 1
    assert "รับปาก" not in action.description  # no invented business promise
    assert not any(s.type == "business_commitment" for s in a.signals)


def test_price_enquiry_is_not_a_quotation_document_request():
    a = analyze("ลูกค้า: ราคาเท่าไหร่ครับ\nร้าน: 18,500 บาทครับ")
    assert "quotation_request" not in types(a) and "price_enquiry" in types(a)
    assert "send_quotation" not in actions(a) and "answer_price_enquiry" not in actions(a)


def test_unanswered_price_enquiry_proposes_answer_not_quotation():
    a = analyze("ลูกค้า: ราคาเท่าไหร่ครับ")
    assert "answer_price_enquiry" in actions(a) and "send_quotation" not in actions(a)


@pytest.mark.parametrize("delivery", ["ร้าน: ส่งใบเสนอราคาให้แล้วครับ", "ลูกค้า: ได้รับใบเสนอราคาแล้วครับ"])
def test_delivered_quotation_closes_request_and_promise(delivery):
    a = analyze("ลูกค้า: ขอใบเสนอราคาหน่อยครับ\nร้าน: เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้\n" + delivery)
    assert "send_quotation" not in actions(a)
    assert "track_commitment" not in actions(a)


def test_new_quotation_request_after_delivery_reopens():
    a = analyze("ลูกค้า: ขอใบเสนอราคาหน่อยครับ\nร้าน: ส่งใบเสนอราคาให้แล้วครับ\nลูกค้า: ขอใบเสนอราคาฉบับแก้ไขด้วยครับ")
    action = next(x for x in a.recommended_actions if x.type == "send_quotation")
    assert [e.message_id for e in action.evidence] == [2]


def test_request_and_promise_merge_into_one_proposal():
    a = analyze("ลูกค้า: ขอใบเสนอราคาหน่อยครับ\nร้าน: เดี๋ยวพรุ่งนี้ส่งใบเสนอราคาให้")
    sends = [x for x in a.recommended_actions if x.type == "send_quotation"]
    assert len(sends) == 1 and {e.message_id for e in sends[0].evidence} == {0, 1}


# --- 3. payment report must not close attendance commitments ------------------

def _open_commitment_values(a):
    by_id = {s.id: s for s in a.signals}
    track = [x for x in a.recommended_actions if x.type == "track_commitment"]
    return {by_id[i].value for x in track for i in x.signal_ids}


def test_payment_report_does_not_close_attendance():
    a = analyze("ลูกค้า: จะเข้าหน้างานวันเสาร์ครับ\nลูกค้า: โอนแล้วครับ")
    assert "attend_appointment" in _open_commitment_values(a)
    assert "check_payment" in actions(a)


def test_payment_report_closes_only_payment_commitment():
    a = analyze("ร้าน: ค่าติดตั้ง 3,500 บาท\nลูกค้า: จะโอนมัดจำพรุ่งนี้ครับ\nลูกค้า: จะเข้าหน้างานวันเสาร์ครับ\nลูกค้า: โอนแล้วครับ")
    assert _open_commitment_values(a) == {"attend_appointment"}
    reported = next(s for s in a.signals if s.type == "payment_reported")
    assert reported.metadata["verified"] is False and not a.confirmed_sale


def test_completion_closes_attendance_but_not_payment():
    a = analyze("ร้าน: ค่าติดตั้ง 3,500 บาท จะเข้าติดตั้งวันเสาร์\nลูกค้า: จะโอนให้พรุ่งนี้\nร้าน: ติดตั้งเสร็จแล้วครับ")
    assert _open_commitment_values(a) == {"make_payment"}


# --- 4. evaluate.py must fail on missing datasets ------------------------------

def run_evaluate(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(ROOT / "evaluate.py"), *args], capture_output=True, text=True, cwd=cwd)


def test_missing_explicit_dataset_fails(tmp_path):
    missing_path = tmp_path / "does-not-exist.jsonl"
    proc = run_evaluate("--dataset", str(missing_path), "--check")
    assert proc.returncode != 0 and "does-not-exist.jsonl" in proc.stderr and "not found" in proc.stderr


def test_missing_one_of_several_explicit_datasets_fails(tmp_path):
    proc = run_evaluate("--dataset", str(ROOT / "data/conversations.jsonl"), "--dataset", str(tmp_path / "gone.jsonl"))
    assert proc.returncode != 0 and "gone.jsonl" in proc.stderr


def test_missing_required_default_dataset_fails(tmp_path):
    proc = run_evaluate("--data-dir", str(tmp_path), "--check")
    assert proc.returncode != 0 and "conversations.jsonl" in proc.stderr


def test_duplicate_dataset_rejected():
    path = str(ROOT / "data/holdout.jsonl")
    proc = run_evaluate("--dataset", path, "--dataset", path)
    assert proc.returncode != 0 and "duplicate" in proc.stderr.lower()


def test_empty_dataset_file_fails(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    proc = run_evaluate("--dataset", str(empty), "--check")
    assert proc.returncode != 0 and "empty" in proc.stderr.lower()


def test_failing_metric_still_fails_check(tmp_path):
    case = json.loads((ROOT / "data/conversations.jsonl").read_text(encoding="utf-8").splitlines()[0])
    case["expected"]["amounts"] = [["99999", "price"]]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    proc = run_evaluate("--dataset", str(bad), "--check")
    assert proc.returncode == 1 and json.loads(proc.stdout)[0]["failed_gates"]


def test_existing_datasets_pass_check(tmp_path):
    proc = run_evaluate("--check")
    assert proc.returncode == 0, proc.stderr
    assert len(json.loads(proc.stdout)) == 6


# --- 5. rescheduled appointment must not reuse the old time ------------------

RESCHEDULE = "ร้าน: ราคา 18500 บาท จะเข้าติดตั้งวันเสาร์ 09:00\nลูกค้า: ยกเลิกนัดวันเสาร์ เลื่อนเป็นวันศุกร์แทน แต่ยังไม่ทราบเวลา"


def test_reschedule_requests_new_time_and_keeps_history():
    a = analyze(RESCHEDULE)
    assert {"installation_address", "appointment_time"} <= missing(a)
    old = next(s for s in a.signals if s.type in {"schedule", "deadline"} and s.value["raw"] == "09:00")
    assert old.metadata["slot_status"] == "superseded"
    old_commitment = next(s for s in a.signals if s.type == "business_commitment")
    assert old_commitment.metadata["slot_status"] == "superseded"
    assert "reserve_or_attend_appointment" not in _open_commitment_values(a)
    confirm = next(x for x in a.recommended_actions if x.type == "confirm_appointment")
    assert [e.message_id for e in confirm.evidence] == [1]
    assert a.commercial_intent and a.deal_status != "cancelled" and a.potential_revenue.amount == "18500"


def test_new_time_in_reschedule_message_satisfies_time():
    a = analyze("ร้าน: จะเข้าติดตั้งวันเสาร์ 09:00\nลูกค้า: ขอเลื่อนเป็นวันศุกร์ 13:00 ครับ ที่อยู่: บ้านทดสอบ ซอย 1")
    assert "appointment_time" not in missing(a)


def test_old_time_inside_reschedule_message_is_superseded():
    a = analyze("ร้าน: ค่าติดตั้ง 3,500 บาท\nลูกค้า: ขอยกเลิกนัดเสาร์นี้ 09:00 เลื่อนเป็นวันอาทิตย์ครับ")
    assert "appointment_time" in missing(a)


def test_later_time_after_reschedule_satisfies_time():
    a = analyze(RESCHEDULE + "\nร้าน: วันศุกร์ 14:00 สะดวกไหมครับ\nลูกค้า: ได้ครับ")
    assert "appointment_time" not in missing(a)


def test_business_reschedule_supersedes_old_slot():
    a = analyze("ร้าน: ค่าซ่อม 900 บาท จะเข้าซ่อมวันจันทร์ 10:00\nร้าน: ขอเลื่อนเป็นวันพุธนะครับ ยังไม่ทราบเวลา")
    assert "appointment_time" in missing(a)
    assert "reschedule_request" in types(a)


def test_reschedule_is_still_not_a_deal_cancellation_and_keeps_sale():
    a = analyze("ร้าน: ราคา 9,800 บาท\nลูกค้า: เอาครับ\n" + RESCHEDULE.splitlines()[1])
    assert a.confirmed_sale and "cancellation" not in types(a)


# --- holdout3 first-run weaknesses (fixed after that run; holdout3 is now development coverage) ---

@pytest.mark.parametrize("last", ["ขอเลื่อนเป็นวันพุธนะครับ เวลาเดี๋ยวแจ้งอีกที", "เลื่อนนัดเป็นเสาร์หน้าครับ เดี๋ยวบอกเวลาอีกที"])
def test_pending_about_appointment_time_is_not_deal_pending(last):
    a = analyze("ร้าน: ค่าติดตั้ง 2,000 บาท\nลูกค้า: เอาครับ\nร้าน: จะเข้าไปติดตั้งวันจันทร์ 10:00\nลูกค้า: " + last)
    assert a.confirmed_sale and not a.decision_pending and "appointment_time" in missing(a)


def test_pending_about_the_purchase_still_counts():
    a = analyze("ร้าน: ค่าติดตั้ง 2,000 บาท\nลูกค้า: เอาครับ\nลูกค้า: เดี๋ยวแจ้งอีกทีว่าจะเอาไหม")
    assert a.decision_pending and not a.confirmed_sale


@pytest.mark.parametrize("reply", ["ยืนยันติดตั้งตามราคานี้ครับ", "ตกลงทำตามราคานี้ครับ", "ยืนยันซ่อมครับ"])
def test_named_purchase_with_verb_in_between(reply):
    assert analyze("ร้าน: ค่าซ่อม 3,300 บาท\nลูกค้า: " + reply).confirmed_sale


@pytest.mark.parametrize("question, reply", [("ราคา 4,200 บาท จ้างเลยไหมครับ", "จ้างเลยครับ"), ("ชุดนี้ 990 บาท ซื้อเลยไหม", "ซื้อเลยค่ะ"), ("ราคา 2,800 บาท", "สั่งเลยครับ")])
def test_echoed_purchase_verb_is_acceptance(question, reply):
    assert analyze(f"ร้าน: {question}\nลูกค้า: {reply}").confirmed_sale


@pytest.mark.parametrize("text", ["สั่งเลยไหมครับ", "ถ้าลดได้ สั่งเลยครับ", "สั่งเลยได้ที่ไหนครับ"])
def test_echoed_verb_guards_still_apply(text):
    assert not analyze("ร้าน: ราคา 2,800 บาท\nลูกค้า: " + text).confirmed_sale


@pytest.mark.parametrize("text", ["จะโอนค่าสำรวจพรุ่งนี้ครับ", "เดี๋ยวจ่ายค่าติดตั้งเย็นนี้"])
def test_paying_an_appointment_fee_is_not_attendance(text):
    a = analyze("ร้าน: ค่าสำรวจ 1,500 บาท\nลูกค้า: " + text)
    values = {s.value for s in a.signals if s.type == "customer_commitment"}
    assert "attend_appointment" not in values and values & {"make_payment", "pay_deposit"}


@pytest.mark.parametrize("text", ["จะรอช่างที่บ้านวันอาทิตย์ครับ", "จะอยู่บ้านรอช่างพรุ่งนี้บ่าย 2"])
def test_waiting_for_technician_is_attendance(text):
    a = analyze("ร้าน: ค่าซ่อม 900 บาท\nลูกค้า: " + text)
    assert any(s.type == "customer_commitment" and s.value == "attend_appointment" for s in a.signals)


@pytest.mark.parametrize("reply", ["เอาครับ เอาตัวนี้เลย", "ไม่ต้องครับ เอาตัวนี้เลย", "ได้ครับ แต่จะเอารุ่นนี้นะ"])
def test_product_pick_after_information_offer_needs_review(reply):
    a = analyze("ร้าน: ส่งรูปให้ดูไหมครับ\nลูกค้า: " + reply)
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance"


@pytest.mark.parametrize("text", [
    "ร้าน: ส่งแคตตาล็อกให้ดูไหม\nร้าน: มีหลายรุ่นครับ ราคา 9,000 บาท\nลูกค้า: เอาครับ",
    "ร้าน: ให้ส่งรูปงานให้ดูไหมครับ\nร้าน: งานนี้ 25,000 บาทครับ\nลูกค้า: ได้ครับ",
])
def test_unanswered_information_question_behind_a_price_statement_needs_review(text):
    a = analyze(text)
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance"


def test_answered_information_question_does_not_block_later_purchase():
    a = analyze("ร้าน: ส่งแคตตาล็อกให้ดูไหม\nลูกค้า: ไม่ต้องครับ\nร้าน: ราคา 9,000 บาท\nลูกค้า: เอาครับ")
    assert a.confirmed_sale
