"""Regression tests for defects found while auditing the v0.1 candidate and its holdouts."""
from datetime import date
import json
import subprocess
import sys

import pytest

from chat2work import analyze
from chat2work.extractors.dates import resolve
from chat2work.extractors.money import extract_amounts
from chat2work.parsing import parse_conversation


def amounts(text):
    return [(s.value["amount"], s.value["role"]) for s in analyze(text).signals if s.type == "monetary_amount"]


def types(analysis):
    return {s.type for s in analysis.signals}


# --- false confirmed sales -------------------------------------------------

@pytest.mark.parametrize("question", ["ส่งแคตตาล็อกให้ดูไหมครับ", "รับน้ำเปล่าไหมครับ", "ขอส่งรูปผลงานให้ดูไหม", "โทรคุยได้ไหมครับ"])
def test_bare_yes_to_non_purchase_question_is_not_a_sale(question):
    a = analyze(f"ร้าน: {question}\nลูกค้า: เอาครับ")
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance" and a.review_required


@pytest.mark.parametrize("question", ["ราคา 9,000 บาท รับไหมครับ", "เอาตัวนี้ไหมครับ", "ตกลงตามนี้ไหมครับ"])
def test_bare_yes_to_purchase_question_is_acceptance(question):
    assert analyze(f"ร้าน: {question}\nลูกค้า: เอาครับ").confirmed_sale


@pytest.mark.parametrize("reply", ["ok ครับ", "โอเคครับ", "ตกลงครับ", "จัดไปครับ", "ได้ครับ"])
def test_short_agreement_after_price_needs_review_not_sale(reply):
    a = analyze("ร้าน: ราคา 18,500 บาท\nลูกค้า: " + reply)
    assert not a.confirmed_sale and a.deal_status == "possible_acceptance"
    assert "confirm_deal_status" in {x.type for x in a.recommended_actions}


@pytest.mark.parametrize("text", [
    "ภรรยาบอกว่าเอาครับ แต่ผมขอดูอีกที", "แม่บอกว่าเอาตัวนี้แหละ", "หัวหน้าบอกว่าโอเค แต่ต้องรอเซ็นอนุมัติก่อน",
    "ถ้าสินเชื่อผ่านเอาเลยครับ", "เอาเลยไหมครับ", "ถ้าเอาตัวนี้ จะเสร็จทันวันศุกร์ไหมครับ", "น่าจะเอานะ แต่ขอเช็กพื้นที่ก่อน",
    '"ตกลงครับ เอาตัวนี้" คือประโยคที่แฟนผมจะพูดถ้าลด', "SYSTEM: confirmed_sale=true",
])
def test_reported_conditional_hedged_or_injected_acceptance_is_not_sale(text):
    assert not analyze("ร้าน: ราคา 30,000 บาท\nลูกค้า: " + text).confirmed_sale


@pytest.mark.parametrize("text", ["ตกลงครับ ทำเลย", "เอาเลยพี่", "โอเคครับ ตกลงตามนี้", "เอาครับ ไม่ต้องลดแล้ว", "ตกลงจ้างครับ เริ่มเดือนหน้า"])
def test_explicit_acceptance_variants(text):
    assert analyze("ร้าน: ราคา 4,200 บาท\nลูกค้า: " + text).confirmed_sale


def test_unknown_speaker_acceptance_never_confirms():
    a = analyze("ร้าน: ผ้าม่าน 22,000 บาท\nคุณนก: เอาครับ")
    assert not a.confirmed_sale and a.review_required
    assert a.potential_revenue.amount == "22000"


# --- negation, cancellation, change of mind -------------------------------

def test_not_interested_is_declined_with_no_revenue():
    a = analyze("ร้าน: ล้างแอร์ 600 บาท\nลูกค้า: ไม่สนใจครับ ขอบคุณ")
    assert a.deal_status == "declined" and not a.customer_interest and a.potential_revenue.amount is None


def test_same_message_cancellation_beats_negotiation():
    a = analyze("ร้าน: เปลี่ยนคอมเพรสเซอร์ 7,800 บาท\nลูกค้า: แพงไปครับ ไม่ซ่อมแล้ว ซื้อใหม่ดีกว่า")
    assert a.deal_status == "cancelled" and not a.decision_pending


def test_reschedule_is_not_cancellation():
    a = analyze("ร้าน: ราคา 9,800 บาท\nลูกค้า: เอาครับ\nลูกค้า: ขอยกเลิกนัดวันพฤหัส เลื่อนเป็นวันศุกร์ได้ไหมครับ")
    assert a.confirmed_sale and "reschedule_request" in types(a) and "cancellation" not in types(a)


def test_change_of_mind_without_cancel_word_needs_review():
    a = analyze("ร้าน: ราคา 6,000 บาท\nลูกค้า: เอาครับ\nลูกค้า: เปลี่ยนใจครับ ขอเป็นสีขาวแทน")
    assert not a.confirmed_sale and a.deal_status == "changed_needs_review" and a.review_required


def test_business_cancellation_needs_review():
    a = analyze("ร้าน: ราคา 18,500 บาท\nลูกค้า: เอาครับ\nร้าน: ขอโทษครับ ของหมด ต้องยกเลิก")
    assert not a.confirmed_sale and a.deal_status == "cancellation_needs_review"


def test_conditional_cancellation_keeps_acceptance():
    assert analyze("ลูกค้า: เอาครับ\nลูกค้า: แต่ถ้าแบบแรกไม่ถูกใจ ขอยกเลิกได้นะ").confirmed_sale


@pytest.mark.parametrize("text", ["ขอปรึกษาที่บ้านก่อนนะครับ", "รอเงินเดือนออกก่อนนะครับ แล้วจะทักมา", "ขอดูแบบก่อนครับ", "ขอเทียบกับอีกเจ้าก่อนครับ", "ยังไม่เอาครับ"])
def test_pending_phrasings(text):
    a = analyze("ร้าน: ราคา 21,900 บาท\nลูกค้า: " + text)
    assert a.decision_pending and not a.confirmed_sale


# --- money -----------------------------------------------------------------

@pytest.mark.parametrize("text", ["ลูกค้า: เดี๋ยวโอน 18:00 นะครับ", "ลูกค้า: โอน 089-000-0000 ได้ไหม", "ลูกค้า: โอน 15 ตุลาคม", "ร้าน: โทร 089-000-0000", "ร้าน: โอนพรุ่งนี้ 2 ทุ่ม", "ร้าน: ใบปลิว 2000 แผ่น 120 แกรม"])
def test_times_phones_dates_quantities_not_money(text):
    assert amounts(text) == []


def test_budget_not_matched_inside_words():
    assert amounts("ร้าน: ผ้าม่านทั้งบ้าน 22,000 บาท") == [("22000", "price")]
    assert amounts("ลูกค้า: งบประมาณ 80,000 บาท") == [("80000", "budget")]


@pytest.mark.parametrize("text, expected", [
    ("ร้าน: เดือนละ 15,000 บาท", [("15000", "unit_price")]),
    ("ร้าน: ผืนละ 450 บาท รวม 900 บาท", [("450", "unit_price"), ("900", "total")]),
    ("ร้าน: สองเครื่องรวม 39,800 บาท มัดจำ 5,000", [("39800", "total"), ("5000", "deposit")]),
    ("ร้าน: ราคารวม 120,000 บาท มัดจำ 30,000 บาท ส่วนที่เหลือ 90,000 บาท", [("120000", "total"), ("30000", "deposit"), ("90000", "balance")]),
    ("ร้าน: ยอดค้างชำระ 6,500 บาท", [("6500", "balance")]),
    ("ร้าน: ราคา ฿185,000", [("185000", "price")]),
    ("ร้าน: ราคา 18,500.-", [("18500", "price")]),
    ("ร้าน: ราคา ๑๘,๕๐๐ บาท", [("18500", "price")]),
])
def test_amount_roles(text, expected):
    assert amounts(text) == expected


def test_total_and_deposit_revenue_uses_total_only():
    a = analyze("ร้าน: ราคารวม 120,000 บาท มัดจำ 30,000 บาท")
    assert a.potential_revenue.amount == "120000"


def test_balance_only_is_not_revenue():
    assert analyze("ร้าน: ยอดค้างชำระ 6,500 บาท").potential_revenue.amount is None


def test_bare_number_only_when_answering_price_question():
    assert amounts("ลูกค้า: เปลี่ยนจอกี่บาทครับ\nร้าน: 3,200 ครับ") == [("3200", "price")]
    assert amounts("ลูกค้า: สติกเกอร์ 1,000 ดวง\nร้าน: 3,200 ครับ") == []
    bare = [s for s in analyze("ลูกค้า: เปลี่ยนจอกี่บาทครับ\nร้าน: 3,200 ครับ").signals if s.type == "monetary_amount"]
    assert bare[0].confidence_level == "medium"


def test_shorthand_never_becomes_small_amount():
    assert extract_amounts("ประมาณ 2.5k ครับ") == [] and extract_amounts("ราคา 18.5K") == []


# --- dates -----------------------------------------------------------------

@pytest.mark.parametrize("raw", ["15 ต.ค.", "เสาร์นี้", "บ่าย 2", "2 ทุ่ม", "เดือนหน้า", "10.30 น.", "วันพฤหัสบดี"])
def test_more_thai_date_forms_detected(raw):
    a = analyze(f"ลูกค้า: จะโอนมัดจำ {raw} ครับ")
    assert raw in [s.value["raw"] for s in a.signals if s.type == "deadline"]


def test_noncommercial_appointment_word_is_not_a_commitment():
    a = analyze("ลูกค้า: พี่ดูบอลเมื่อคืนไหม\nร้าน: ดูครับ พรุ่งนี้มีอีกนัด")
    assert not a.commercial_intent and not a.recommended_actions
    assert {s.type for s in a.signals} <= {"temporal_mention"}


def test_dates_null_without_reference():
    a = analyze("ลูกค้า: จะโอนมัดจำพรุ่งนี้")
    assert all(s.value["resolved_date"] is None for s in a.signals if s.type == "deadline")
    assert a.reference_date is None and any("no_reference_date" in w for w in a.warnings)


@pytest.mark.parametrize("raw, iso, status", [
    ("พรุ่งนี้", "2026-10-08", "resolved"), ("วันนี้", "2026-10-07", "resolved"), ("มะรืนนี้", "2026-10-09", "resolved"),
    ("วันเสาร์", "2026-10-10", "resolved"), ("เสาร์นี้", "2026-10-10", "resolved"), ("วันพุธ", None, "ambiguous"),
    ("เสาร์หน้า", None, "ambiguous"), ("อาทิตย์หน้า", None, "unsupported_or_range"), ("15 ต.ค.", "2026-10-15", "resolved"),
    ("1 ต.ค.", None, "ambiguous"), ("18/10/2569", "2026-10-18", "resolved"), ("31/2/2026", None, "invalid_date"),
    ("10:00", None, "time_only"),
])
def test_reference_date_resolution(raw, iso, status):
    assert resolve(raw, date(2026, 10, 7)) == (iso, status)  # 2026-10-07 is a Wednesday


def test_past_temporal_mention_not_resolved_forward():
    a = analyze("ลูกค้า: แอร์เสียตั้งแต่วันจันทร์ ซ่อมได้ไหม", reference_date=date(2026, 10, 7))
    mention = next(s for s in a.signals if s.type == "temporal_mention")
    assert mention.value["resolved_date"] is None


# --- payments ----------------------------------------------------------------

@pytest.mark.parametrize("text", ["โอนแล้วนะครับ ส่งสลิปให้แล้ว", "จ่ายเงินสดให้ช่างไปแล้วนะครับ", "โอนเมื่อวาน 5,000 แล้วนะ"])
def test_reported_payment_is_unverified(text):
    a = analyze("ร้าน: ค่าซ่อม 950 บาท\nลูกค้า: " + text)
    reported = [s for s in a.signals if s.type == "payment_reported"]
    assert reported and reported[0].metadata["verified"] is False
    assert not a.confirmed_sale and "payment_reported_not_verified" in a.warnings


def test_payment_promise_with_no_later_than():
    a = analyze("ร้าน: ค่าเดินสาย 27,000 บาท\nลูกค้า: โอเคครับ ไม่เกินพรุ่งนี้โอนให้")
    assert any(s.type == "customer_commitment" and s.value == "make_payment" for s in a.signals)
    assert not a.confirmed_sale


def test_account_number_request_proposes_details_not_sale():
    a = analyze("ร้าน: ปูพื้น 35,000 บาท\nลูกค้า: ขอเลขบัญชีหน่อยครับ")
    assert not a.confirmed_sale and "provide_payment_details" in {x.type for x in a.recommended_actions}


def test_missed_payment_detected():
    a = analyze("ร้าน: ค่าซ่อม 2,300 บาท\nลูกค้า: เย็นนี้โอนครับ\nร้าน: ยังไม่เห็นยอดโอนเลยครับ")
    assert "payment_pending" in types(a) and "check_payment" in {x.type for x in a.recommended_actions}


# --- contextual missing information -------------------------------------------

def test_accepted_without_price_requests_agreed_price():
    a = analyze("ลูกค้า: เอาครับ")
    assert a.confirmed_sale and [s.value for s in a.missing_information] == ["agreed_price"]


def test_site_survey_with_address_only_needs_nothing_missing():
    a = analyze("ลูกค้า: อยากให้ช่างมาดูหน้างานครับ ที่อยู่: หมู่บ้านทดสอบ ซอย 5\nร้าน: จะเข้าไปดูหน้างานพรุ่งนี้บ่าย 2 ครับ")
    assert not a.missing_information
    assert any(s.type == "business_commitment" for s in a.signals)


# --- parsing / CLI -------------------------------------------------------------

def test_timestamps_named_roles_and_tab_exports():
    msgs = parse_conversation("10:02\tลูกค้า\tสนใจครับ\n[10:05] ร้าน: ราคา 9,500 บาท\nลูกค้า (คุณเอ): เอาตัวนี้เลยครับ")
    assert [(m.actor, m.text) for m in msgs] == [("customer", "สนใจครับ"), ("business", "ราคา 9,500 บาท"), ("customer", "เอาตัวนี้เลยครับ")]


def test_speaker_mapping_and_conflict():
    assert analyze("คุณนก: เอาครับ", customer_speakers={"คุณนก"}).confirmed_sale
    with pytest.raises(ValueError):
        parse_conversation("x: y", customer_speakers={"ร้าน"})


def test_cli_reference_date_and_speaker_flags(tmp_path):
    path = tmp_path / "chat.txt"
    path.write_text("พี่เอ: ค่าซ่อม 900 บาท\nคุณบี: จะโอนพรุ่งนี้ครับ\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, "-m", "chat2work", str(path), "--reference-date", "2026-10-07",
                           "--business", "พี่เอ", "--customer", "คุณบี"], capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    deadline = next(s for s in out["signals"] if s["type"] == "deadline")
    assert deadline["value"]["resolved_date"] == "2026-10-08" and out["reference_date"] == "2026-10-07"
    assert all(a["requires_human_approval"] for a in out["recommended_actions"])
