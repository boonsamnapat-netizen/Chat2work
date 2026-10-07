"""Derive current deal state and evidence-backed proposals from validated signals."""
import math
import re
from dataclasses import replace
from datetime import date
from .models import Action, Analysis, Evidence, Extractor, Message, Opportunity, Signal
from .parsing import parse_conversation
from .extractors import RuleExtractor
from .extractors.dates import resolve

DATE_TYPES = {"deadline", "schedule", "temporal_mention"}
# Customer signals that move the deal state, in conversation order.
CUSTOMER_STATES = {"customer_interest": "interested", "decision_pending": "decision_pending",
                   "customer_acceptance": "accepted", "possible_acceptance": "possible_acceptance",
                   "change_of_mind": "changed_needs_review", "cancellation": "cancelled",
                   "customer_rejection": "declined", "negotiation": "negotiating"}
# Within one message the firmer signal wins ("แพงไป ไม่ซ่อมแล้ว" is a cancellation, not negotiation).
PRIORITY = {"cancellation": 6, "customer_rejection": 5, "change_of_mind": 4, "decision_pending": 3,
            "customer_acceptance": 3, "negotiation": 2, "possible_acceptance": 1, "customer_interest": 0}
ONSITE = r"ติดตั้ง|อยากติด|มาติด|รวมติด|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าวัด|เข้าซ่อม|มาซ่อม|เดินสาย"
LOCATION = r"ที่อยู่\s*[:：]\s*\S|ที่อยู่(?:คือ|อยู่)\s*\S|หน้างาน(?:อยู่|ที่)\s*\S|สถานที่(?:คือ|อยู่|:)\s*\S|ซอย\s*\S|ถนน\s*\S|บ้านเลขที่\s*\d|พิกัด\s*[:：]\s*\S|https?://(?:maps\.|maps\.app|goo\.gl/maps)"


def _validate(signals: list[Signal], messages: list[Message]) -> None:
    indexed = {m.id: m for m in messages}
    ids = set()
    for s in signals:
        if s.id in ids or not s.id:
            raise ValueError("Signal IDs must be nonempty and unique")
        ids.add(s.id)
        m = indexed.get(s.evidence.message_id)
        if not m or s.evidence != Evidence(m.id, m.speaker, m.text, m.raw_line) or s.actor != m.actor:
            raise ValueError("Signal evidence and actor must match the source message exactly")
        if not math.isfinite(s.confidence) or not 0 <= s.confidence <= 1:
            raise ValueError("Confidence must be finite and between zero and one")
        if s.actor == "unknown" and s.confidence >= 0.80:
            raise ValueError("Unknown speakers require human review")
        if s.type == "customer_acceptance" and (s.actor != "customer" or s.confidence < 0.90):
            raise ValueError("Acceptance requires an explicit customer and high confidence")


def _resolve_dates(signals: list[Signal], reference: date | None) -> list[Signal]:
    if reference is None:
        return signals
    out = []
    for s in signals:
        # Temporal mentions may refer to the past ("ตั้งแต่วันจันทร์"); only forward-looking dates resolve.
        if s.type == "temporal_mention" and isinstance(s.value, dict):
            s = replace(s, value={**s.value, "resolution": "not_resolved_context_may_be_past"})
        elif s.type in DATE_TYPES and isinstance(s.value, dict) and s.value.get("resolved_date") is None:
            resolved, status = resolve(s.value["raw"], reference)
            s = replace(s, value={**s.value, "resolved_date": resolved, "resolution": status})
        out.append(s)
    return out


def analyze(conversation: str, *, extractor: Extractor | None = None, reference_date: date | None = None,
            customer_speakers: set[str] | frozenset[str] = frozenset(),
            business_speakers: set[str] | frozenset[str] = frozenset()) -> Analysis:
    """Analyze a conversation. ``reference_date`` (when the chat happened) enables
    resolution of unambiguous relative dates; without it every resolved_date is null."""
    messages = parse_conversation(conversation, customer_speakers=customer_speakers, business_speakers=business_speakers)
    provider = extractor or RuleExtractor()
    signals = list(provider.extract(messages))
    _validate(signals, messages)
    signals = _resolve_dates(signals, reference_date)
    by_type: dict[str, list[Signal]] = {}
    for s in signals:
        by_type.setdefault(s.type, []).append(s)
    commercial = bool(by_type.get("commercial_intent"))
    state = "inquiry" if commercial else "non_commercial"
    status_sources: list[str] = []
    per_message: dict[int, Signal] = {}
    for s in signals:
        if s.type == "business_cancellation" or (s.type in CUSTOMER_STATES and s.actor == "customer"):
            best = per_message.get(s.evidence.message_id)
            if best is None or PRIORITY.get(s.type, 7) >= PRIORITY.get(best.type, 7):
                per_message[s.evidence.message_id] = s
    for _, s in sorted(per_message.items()):
        if s.type == "business_cancellation":
            state, status_sources = "cancellation_needs_review", [s.id]
            continue
        # Routine later interest or a vague "ok" cannot undo a firmer state.
        if s.type in {"customer_interest", "possible_acceptance"} and state in {"accepted", "cancelled", "declined", "cancellation_needs_review"}:
            continue
        state, status_sources = CUSTOMER_STATES[s.type], [s.id]
    last_status_message = max((s.evidence.message_id for s in signals if s.id in status_sources), default=-1)
    if state == "accepted" and any(m.actor == "unknown" and m.id > last_status_message for m in messages):
        state = "acceptance_needs_review"
    accepted = state == "accepted"
    pending = state in {"decision_pending", "negotiating"}
    inactive = state in {"cancelled", "declined"}
    amounts = by_type.get("monetary_amount", [])
    candidates = [s for s in amounts if s.actor == "business" and s.value["role"] in {"price", "total"}]
    # Most recent business price message; prefer explicit total over component prices.
    latest_id = max((c.evidence.message_id for c in candidates), default=-1)
    latest = [s for s in candidates if s.evidence.message_id == latest_id]
    latest = [s for s in latest if s.value["role"] == "total"] or latest
    unambiguous = len({s.value["amount"] for s in latest}) == 1
    if unambiguous and not inactive and commercial:
        source = latest[-1]
        opportunity = Opportunity(source.value["amount"], "THB", (source.id,), source.confidence,
                                  "explicit_business_price; potential_only_not_booked_revenue")
    else:
        opportunity = Opportunity(None, "THB", (), None, state if inactive else "no_unambiguous_business_total_or_price")

    missing: list[Signal] = []

    def need(field: str, origin: Signal, reason: str) -> None:
        derived = Signal(f"s{len(signals)+1}", "missing_information", origin.actor, field, 0.84,
                         origin.evidence, {"derived_from": [origin.id], "reason": reason})
        signals.append(derived)
        missing.append(derived)

    active_appointments = [] if inactive else by_type.get("appointment", []) + by_type.get("reschedule_request", [])
    onsite = [s for s in active_appointments if re.search(ONSITE, s.evidence.text)]
    if onsite:
        origin = onsite[-1]
        located = any(re.search(LOCATION, m.text) and not re.search(r"(?:ขอ|ส่ง|แจ้ง|ยืนยัน).*ที่อยู่|ยังไม่|ไม่มี|ไม่ทราบ|สมมติว่า|ตัวอย่าง", m.text) for m in messages)
        if not located:
            need("installation_address", origin, "needed_for_onsite_schedule; not_found_in_supplied_messages")
        appointment_dates = [s for s in signals if s.type == "schedule" or (s.type == "deadline" and any(a.evidence.message_id == s.evidence.message_id for a in active_appointments))]
        if not any(s.value["kind"] == "time" for s in appointment_dates):
            need("appointment_time", origin, "needed_for_onsite_schedule; not_found_in_supplied_messages")
    if accepted and opportunity.amount is None:
        need("agreed_price", by_type["customer_acceptance"][-1], "customer_accepted_but_no_single_business_price_found")

    actions: list[Action] = []

    def propose(kind: str, description: str, sources: list[Signal]) -> None:
        if sources:
            actions.append(Action(kind, description, tuple(s.id for s in sources),
                                  tuple(dict.fromkeys(s.evidence for s in sources)), min(s.confidence for s in sources)))

    if state == "cancelled":
        propose("confirm_cancellation", "ยืนยันการยกเลิกกับลูกค้า และตรวจสอบคิว/มัดจำที่เกี่ยวข้องโดยเจ้าหน้าที่",
                [s for s in signals if s.id in status_sources])
    if state in {"possible_acceptance", "changed_needs_review", "acceptance_needs_review", "cancellation_needs_review"}:
        propose("confirm_deal_status", "ยืนยันกับลูกค้าให้ชัดเจนก่อนบันทึกว่าตกลงซื้อหรือยกเลิก",
                [s for s in signals if s.id in status_sources])
    if not inactive:
        # Closed/reported events are history, not unfulfilled commitments.
        quotes = [s for s in by_type.get("business_commitment", []) if s.value == "send_quotation"]
        sent = by_type.get("quotation_sent", [])
        open_quotes = [s for s in quotes if not any(done.evidence.message_id > s.evidence.message_id for done in sent)]
        propose("send_quotation", "จัดเตรียมและส่งใบเสนอราคาที่รับปากไว้", open_quotes or (by_type.get("quotation_request", []) if not sent and opportunity.amount is None else []))
        commitments = by_type.get("business_commitment", []) + by_type.get("customer_commitment", [])
        completed_payments = by_type.get("payment_reported", [])
        open_commitments = [s for s in commitments if s in open_quotes or s.value == "reserve_or_attend_appointment" or (s.type == "customer_commitment" and not any(p.evidence.message_id > s.evidence.message_id for p in completed_payments))]
        propose("track_commitment", "ตรวจติดตามสิ่งที่รับปากไว้ โดยยืนยันกับผู้รับผิดชอบก่อนดำเนินการ", open_commitments)
        payment_commitments = [s for s in by_type.get("customer_commitment", []) if s.value in {"make_payment", "pay_deposit"}]
        propose("check_payment", "ตรวจสอบยอดเงินจริงก่อนสรุปว่าได้รับชำระแล้ว", payment_commitments + by_type.get("payment_pending", []) + completed_payments)
        propose("provide_payment_details", "ตรวจสอบและส่งรายละเอียดการชำระเงินที่ถูกต้องให้ลูกค้า (ยังไม่ใช่การยืนยันการขาย)",
                [s for s in by_type.get("payment_signal", []) if s.value == "account_number_request"])
        propose("confirm_appointment", "ยืนยันวัน เวลา และสถานที่นัดกับลูกค้า", active_appointments)
        propose("request_missing_information", "ขอข้อมูลที่ยังไม่พบในบทสนทนา: " + ", ".join(s.value for s in missing), missing)
        follow_sources = by_type.get("decision_pending", []) + by_type.get("negotiation", []) + by_type.get("quotation_sent", [])
        if not accepted and state not in {"possible_acceptance", "changed_needs_review", "cancellation_needs_review"}:
            propose("follow_up_customer", "สอบถามการตัดสินใจของลูกค้า โดยเคารพคำขอคิดก่อน", follow_sources or by_type.get("customer_interest", []))
        open_deadlines = [s for s in by_type.get("deadline", []) if any(c.evidence.message_id == s.evidence.message_id for c in open_commitments)]
        propose("schedule_follow_up", "กำหนดเวลาติดตามโดยยืนยันวันที่สัมพัทธ์ก่อน", open_deadlines)
        propose("add_to_revenue_radar", "ติดตามโอกาสรายได้และสถานะถัดไป; ยังไม่ใช่รายได้ที่รับรู้", ([s for s in amounts if s.id in opportunity.signal_ids] or by_type.get("customer_interest", []) or by_type.get("quotation_request", []) or open_quotes))
    warnings = []
    if any(m.actor == "unknown" for m in messages):
        warnings.append("unknown_speakers_require_review; use ลูกค้า: / ร้าน:")
    date_signals = [s for s in signals if s.type in DATE_TYPES]
    if date_signals and (reference_date is None or any(s.value["resolved_date"] is None for s in date_signals)):
        warnings.append("some_dates_unresolved; no_overdue_inference" if reference_date else "dates_are_unresolved; no_reference_date_supplied")
    if len(latest) > 1 and not unambiguous:
        warnings.append("multiple_price_options; opportunity_amount_requires_review")
    if by_type.get("payment_reported"):
        warnings.append("payment_reported_not_verified")
    if state in {"possible_acceptance", "changed_needs_review", "cancellation_needs_review"}:
        warnings.append(f"deal_status_{state}")
    review = bool(warnings) or any(s.confidence < 0.80 for s in signals)
    return Analysis("0.1", provider.name, reference_date.isoformat() if reference_date else None, messages, signals, commercial,
                    bool(by_type.get("customer_interest")), pending, accepted, state, status_sources,
                    opportunity, missing, actions, review, warnings)
