"""Derive current deal state and evidence-backed proposals from validated signals."""
import math
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from .models import Action, Analysis, Evidence, Extractor, Message, Opportunity, Signal
from .parsing import parse_conversation
from .extractors import RuleExtractor
from .extractors.dates import resolve
from .extractors.rules import acceptance_contradicted
from .redaction import ADDRESS_PLACEHOLDER
from .validation import validate_references, validate_signal_values

DATE_TYPES = {"deadline", "schedule", "temporal_mention"}
# Customer signals that move the deal state, in conversation order.
CUSTOMER_STATES = {"customer_interest": "interested", "decision_pending": "decision_pending",
                   "customer_acceptance": "accepted", "possible_acceptance": "possible_acceptance",
                   "change_of_mind": "changed_needs_review", "cancellation": "cancelled",
                   "customer_rejection": "declined", "negotiation": "negotiating",
                   "reported_cancellation": "changed_needs_review"}
# Within one message the firmer signal wins ("แพงไป ไม่ซ่อมแล้ว" is a cancellation, not negotiation).
PRIORITY = {"cancellation": 6, "customer_rejection": 5, "change_of_mind": 4, "reported_cancellation": 4, "decision_pending": 3,
            "customer_acceptance": 3, "negotiation": 2, "possible_acceptance": 1, "customer_interest": 0}
ONSITE = r"ติดตั้ง|อยากติด|มาติด|รวมติด|เข้าหน้างาน|ดูหน้างาน|สำรวจ|เข้าวัด|เข้าซ่อม|มาซ่อม|เดินสาย"
# An address explicitly withdrawn later ("ที่อยู่เมื่อกี้ผิด") no longer counts as provided.
ADDRESS_RETRACTED = r"ที่อยู่\S{0,12}(?:ผิด|ไม่ถูก|เปลี่ยน|ใหม่)|(?:เปลี่ยน|แก้)ที่อยู่"
# Wording that makes a later shop price a revision of an earlier explicit total.
PRICE_REVISION = r"ราคาใหม่|ลดเหลือ|เหลือ|ปรับ|แก้ราคา|ลดให้|ราคาพิเศษ|เปลี่ยนเป็น|ต่ำสุด|ทั้งหมด|รวม"
UNKNOWN_CEILING = 0.65
LOCATION = ADDRESS_PLACEHOLDER + r"|ที่อยู่\s*[:：]\s*\S|ที่อยู่(?:คือ|อยู่)\s*\S|หน้างาน(?:อยู่|ที่)\s*\S|สถานที่(?:คือ|อยู่|:)\s*\S|ซอย\s*\S|ถนน\s*\S|บ้านเลขที่\s*\d|พิกัด\s*[:：]\s*\S|https?://(?:maps\.|maps\.app|goo\.gl/maps)"


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
    validate_signal_values(signals, messages)


def _validate_final(signals: list[Signal], actions: list[Action], messages: list[Message]) -> None:
    """Invariants on the finished output, including nodes the core derived itself."""
    _validate(signals, messages)
    validate_references(signals)
    ids = {s.id for s in signals}
    for a in actions:
        if not a.signal_ids or any(i not in ids for i in a.signal_ids) or not a.requires_human_approval:
            raise ValueError("Every action must reference existing signals and require human approval")
    for s in signals:
        if "derived_from" in s.metadata and s.actor == "unknown" and s.confidence > UNKNOWN_CEILING:
            raise ValueError("Derived signals from unknown speakers must keep the confidence ceiling")


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


APPOINTMENT_COMMITMENTS = {"reserve_or_attend_appointment", "attend_appointment"}
PAYMENT_COMMITMENTS = {"make_payment", "pay_deposit"}


def _live(s: Signal) -> bool:
    return s.metadata.get("slot_status") != "superseded"


def _mark_superseded_slots(signals: list[Signal]) -> list[Signal]:
    """After a reschedule, earlier appointment slots, their times and attendance promises
    remain as history but are marked superseded; only the latest arrangement is active."""
    reschedules = [s for s in signals if s.type == "reschedule_request"]
    if not reschedules:
        return signals
    latest = reschedules[-1]
    cutoff = latest.evidence.message_id
    appointment_messages = {s.evidence.message_id for s in signals
                            if s.type == "appointment" or (s.type.endswith("_commitment") and s.value in APPOINTMENT_COMMITMENTS)}
    out = []
    for s in signals:
        earlier = s.evidence.message_id < cutoff
        stale = (s.metadata.get("slot_status") == "superseded"
                 or (earlier and (s.type in {"appointment", "reschedule_request"}
                                  or (s.type.endswith("_commitment") and s.value in APPOINTMENT_COMMITMENTS)
                                  or (s.type in {"schedule", "deadline"} and s.evidence.message_id in appointment_messages))))
        if stale:
            s = replace(s, metadata={**s.metadata, "slot_status": "superseded", "superseded_by": latest.id})
        out.append(s)
    return out


def _after(signal: Signal, events: list[Signal]) -> bool:
    return any(e.evidence.message_id > signal.evidence.message_id for e in events)


def analyze(conversation: str, *, extractor: Extractor | None = None, reference_date: date | None = None,
            customer_speakers: set[str] | frozenset[str] = frozenset(),
            business_speakers: set[str] | frozenset[str] = frozenset()) -> Analysis:
    """Analyze a conversation. ``reference_date`` (when the chat happened) enables
    resolution of unambiguous relative dates; without it every resolved_date is null."""
    messages = parse_conversation(conversation, customer_speakers=customer_speakers, business_speakers=business_speakers)
    provider = extractor or RuleExtractor()
    signals = list(provider.extract(messages))
    _validate(signals, messages)
    signals = _mark_superseded_slots(_resolve_dates(signals, reference_date))
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
    contradicted = []
    for _, s in sorted(per_message.items()):
        if s.type == "business_cancellation":
            state, status_sources = "cancellation_needs_review", [s.id]
            continue
        # Confidence and exact evidence do not prove meaning: an acceptance whose own message is
        # hedged, conditional, negated, questioned, pending or reported goes to a person.
        if s.type == "customer_acceptance" and acceptance_contradicted(s.evidence.text):
            contradicted.append(s)
            state, status_sources = "acceptance_needs_review", [s.id]
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
    # Only this shop's THB prices form the opportunity; another currency is never relabelled as THB.
    candidates = [s for s in amounts if s.actor == "business" and s.value["role"] in {"price", "total"} and s.value["currency"] == "THB"]
    foreign = [s for s in amounts if s.value["currency"] != "THB"]
    # Most recent business price message; prefer explicit total over component prices.
    latest_id = max((c.evidence.message_id for c in candidates), default=-1)
    latest = [s for s in candidates if s.evidence.message_id == latest_id]
    latest = [s for s in latest if s.value["role"] == "total"] or latest
    # A later plain price in a separate bubble ("ค่าแรง 1500 บาท") does not silently replace an earlier
    # explicit total; only revision wording does. Otherwise keep the total and ask for review.
    earlier_totals = [s for s in candidates if s.value["role"] == "total" and s.evidence.message_id < latest_id]
    price_relation_unclear = False
    if earlier_totals and all(s.value["role"] != "total" for s in latest) and not re.search(PRICE_REVISION, latest[0].evidence.text):
        newest_total_id = max(s.evidence.message_id for s in earlier_totals)
        latest = [s for s in earlier_totals if s.evidence.message_id == newest_total_id]
        price_relation_unclear = True
    unambiguous = len({s.value["amount"] for s in latest}) == 1
    if unambiguous and not inactive and commercial:
        source = latest[-1]
        opportunity = Opportunity(source.value["amount"], "THB", (source.id,), source.confidence,
                                  "explicit_business_price; potential_only_not_booked_revenue")
    else:
        opportunity = Opportunity(None, "THB", (), None, state if inactive else "no_unambiguous_business_total_or_price")

    missing: list[Signal] = []

    used_ids = {s.id for s in signals}

    def next_id() -> str:
        n = len(used_ids) + 1
        while f"s{n}" in used_ids:
            n += 1
        used_ids.add(f"s{n}")
        return f"s{n}"

    def need(field: str, origin: Signal, reason: str) -> None:
        # A derived node is never more certain than its source, and unknown speakers stay capped.
        confidence = min(0.84, origin.confidence, UNKNOWN_CEILING if origin.actor == "unknown" else 1.0)
        derived = Signal(next_id(), "missing_information", origin.actor, field, confidence,
                         origin.evidence, {"derived_from": [origin.id], "reason": reason})
        signals.append(derived)
        missing.append(derived)

    slots = by_type.get("appointment", []) + by_type.get("reschedule_request", [])
    completed = by_type.get("appointment_completed", [])
    active_appointments = [] if inactive else sorted(
        (s for s in slots if _live(s) and not _after(s, completed)), key=lambda s: s.evidence.message_id)
    reschedules = by_type.get("reschedule_request", [])
    active_from = reschedules[-1].evidence.message_id if reschedules else -1
    # The on-site nature comes from the whole deal: a bare "เลื่อนเป็นวันศุกร์" still concerns that job.
    onsite = any(re.search(ONSITE, s.evidence.text) for s in slots)
    rearranged = active_from >= 0 and _live(reschedules[-1])
    if active_appointments and (onsite or rearranged):
        origin = active_appointments[-1]
        address_ids = [m.id for m in messages if re.search(LOCATION, m.text)
                       and not re.search(r"(?:ขอ|ส่ง|แจ้ง|ยืนยัน).*ที่อยู่|ยังไม่|ไม่มี|ไม่ทราบ|สมมติว่า|ตัวอย่าง", m.text)]
        retracted_ids = [m.id for m in messages if re.search(ADDRESS_RETRACTED, m.text) and m.id not in address_ids]
        located = bool(address_ids) and max(address_ids) > max(retracted_ids, default=-1)
        if onsite and not located:
            need("installation_address", origin, "needed_for_onsite_schedule; not_found_in_supplied_messages")
        # Only times from the active arrangement count; a superseded slot's time is history.
        appointment_dates = [s for s in signals if _live(s) and s.evidence.message_id >= active_from and s.metadata.get("event") != "call"
                             and (s.type == "schedule" or (s.type == "deadline" and any(a.evidence.message_id == s.evidence.message_id for a in active_appointments)))]
        if not any(s.value["kind"] == "time" for s in appointment_dates):
            need("appointment_time", origin, ("needed_for_rescheduled_slot" if rearranged else "needed_for_onsite_schedule")
                 + "; not_found_in_supplied_messages")
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
        # Closed/reported events are history, not unfulfilled commitments. Each kind of commitment
        # is closed only by evidence about that kind: a payment report cannot prove attendance.
        # Fulfilment must match the deliverable: only a document closes a quotation request or a
        # document promise; a price typed or "sent" in chat closes only a price promise or enquiry.
        documents = by_type.get("quotation_sent", []) + by_type.get("quotation_received", [])
        prices_given = by_type.get("price_sent", []) + documents
        declined = by_type.get("quotation_declined", [])

        def quote_open(s: Signal) -> bool:
            closers = prices_given if s.metadata.get("deliverable") == "price" else documents
            return not _after(s, closers + declined)

        promises = [s for s in by_type.get("business_commitment", []) if s.value == "send_quotation" and quote_open(s)]
        requests = [s for s in by_type.get("quotation_request", []) if quote_open(s)]
        # A deferral ("เอาครับ แต่ยังไม่ต้องส่ง") puts the quotation on hold until a later go-ahead
        # (a new, non-deferred request). The promise and request stay as evidence of the obligation.
        quote_holds = [s for s in requests if s.metadata.get("deferred")]
        go_aheads = [s for s in requests if not s.metadata.get("deferred")]
        last_hold = max((s.evidence.message_id for s in quote_holds), default=-1)
        on_hold = last_hold >= 0 and max((s.evidence.message_id for s in go_aheads), default=-1) < last_hold
        held = sorted(promises + quote_holds, key=lambda s: s.evidence.message_id) if on_hold else []
        open_quotes = [] if on_hold else promises
        open_requests = [] if on_hold else [s for s in go_aheads if s.evidence.message_id >= last_hold]
        if open_quotes:
            propose("send_quotation", "จัดเตรียมและส่งใบเสนอราคาที่รับปากไว้",
                    sorted(open_quotes + open_requests, key=lambda s: s.evidence.message_id))
        else:
            propose("send_quotation", "ลูกค้าขอใบเสนอราคาเป็นเอกสาร: จัดเตรียมและส่งให้ลูกค้า (ราคาในแชตยังไม่ใช่ใบเสนอราคา)", open_requests)
        priced = [s for s in amounts if s.actor == "business" and s.value["role"] != "competitor_price"] + prices_given
        propose("answer_price_enquiry", "ตอบราคาที่ลูกค้าสอบถาม โดยตรวจสอบราคาก่อนส่ง",
                [s for s in by_type.get("price_enquiry", []) if not _after(s, priced)])
        offers = {s.evidence.message_id: s for s in by_type.get("information_offer", [])}
        info_closed = by_type.get("information_sent", []) + by_type.get("information_declined", [])
        info_requests = [s for s in by_type.get("information_requested", []) if not _after(s, info_closed)]
        released: set[str] = set()
        for accepted_info in by_type.get("information_accepted", []):
            if accepted_info.value == "quotation" or _after(accepted_info, info_closed):
                continue
            offer_signal = offers.get(accepted_info.metadata.get("offer_message_id"))
            go = [r for r in info_requests if r.value == accepted_info.value and r.evidence.message_id > accepted_info.evidence.message_id]
            sources = [x for x in (offer_signal, accepted_info) if x is not None] + go
            released.update(r.id for r in go)
            if accepted_info.metadata.get("deferred") and not go:
                held.append(accepted_info)
            else:
                propose("send_offered_information", f"ส่งข้อมูลที่ลูกค้าตอบรับ ({accepted_info.value}); ไม่ใช่การยืนยันการซื้อ", sources)
        for request in info_requests:
            if request.id not in released:
                propose("send_offered_information", f"ลูกค้าขอข้อมูล ({request.value}); ไม่ใช่การยืนยันการซื้อ", [request])
        # Keep the interest and the obligation, honour the timing constraint: no send-now proposal.
        propose("await_customer_go_ahead", "ลูกค้าสนใจแต่ขอให้ยังไม่ส่ง: รอให้ลูกค้าแจ้งก่อนจึงส่ง",
                sorted(held, key=lambda s: s.evidence.message_id))
        propose("confirm_payment_schedule", "ยืนยันกำหนดชำระเงินใหม่กับลูกค้า (ไม่เปลี่ยนนัดหมายงาน)",
                by_type.get("payment_reschedule_request", []))
        propose("verify_completion", "ยังไม่ชัดว่างานเสร็จแล้ว: ตรวจสอบกับช่าง/ลูกค้าก่อนปิดงาน",
                [s for s in by_type.get("completion_uncertain", []) if not _after(s, completed)])
        payments_reported = by_type.get("payment_reported", [])
        remainders = [s for s in by_type.get("customer_commitment", []) if s.metadata.get("purpose") == "remaining_balance"]
        partial_payment = []

        def pays_for(r: Signal, c: Signal) -> bool:
            """A report pays a commitment only if its purpose fits: a named fee ("ค่าอะไหล่") is not the deposit."""
            purpose = r.metadata.get("purpose")
            return purpose in {None, "deposit"} or c.value != "pay_deposit"

        def payment_open(c: Signal) -> bool:
            later = [r for r in payments_reported if r.evidence.message_id > c.evidence.message_id and pays_for(r, c)]
            if not later:
                return True
            if any(r.evidence.message_id > c.evidence.message_id for r in remainders):
                return False  # superseded by the evidenced remaining-balance commitment
            # A repeated report of the same transfer is not new money.
            distinct = [r for r in later if not r.metadata.get("repeat_of_previous")]
            if not distinct:
                return True
            reported = [r.metadata.get("reported_amount") for r in distinct]
            known = c.metadata.get("amount") and all(reported)
            covered = known and sum(Decimal(x) for x in reported) >= Decimal(c.metadata["amount"])
            # "โอนแล้วครับ แต่ยังไม่ครบ": short by an unknown amount; never invent the remainder.
            if (any(r.metadata.get("partial") for r in later) and not covered) or (known and not covered):
                partial_payment.append(c)
                return True
            return False

        def is_open(c: Signal) -> bool:
            if c.value == "send_quotation":
                return c in open_quotes
            if c.value in PAYMENT_COMMITMENTS:
                return payment_open(c)
            if c.value in APPOINTMENT_COMMITMENTS:
                return _live(c) and not _after(c, completed)
            return True

        commitments = by_type.get("business_commitment", []) + by_type.get("customer_commitment", [])
        open_commitments = sorted((c for c in commitments if is_open(c)), key=lambda c: c.evidence.message_id)
        propose("track_commitment", "ตรวจติดตามสิ่งที่รับปากไว้ โดยยืนยันกับผู้รับผิดชอบก่อนดำเนินการ", open_commitments)
        payment_commitments = [s for s in by_type.get("customer_commitment", []) if s.value in {"make_payment", "pay_deposit"}]
        propose("check_payment", "ตรวจสอบยอดเงินจริงก่อนสรุปว่าได้รับชำระแล้ว", payment_commitments + by_type.get("payment_pending", []) + payments_reported)
        propose("provide_payment_details", "ตรวจสอบและส่งรายละเอียดการชำระเงินที่ถูกต้องให้ลูกค้า (ยังไม่ใช่การยืนยันการขาย)",
                [s for s in by_type.get("payment_signal", []) if s.value == "account_number_request"])
        possible_moves = by_type.get("possible_reschedule", [])
        propose("confirm_appointment", "ยืนยันวัน เวลา และสถานที่นัดกับลูกค้า" + (" (ลูกค้าอาจเลื่อนนัด: ถามให้ชัดก่อนเปลี่ยนคิว)" if possible_moves else ""),
                sorted(active_appointments + possible_moves, key=lambda s: s.evidence.message_id))
        propose("request_missing_information", "ขอข้อมูลที่ยังไม่พบในบทสนทนา: " + ", ".join(s.value for s in missing), missing)
        follow_sources = by_type.get("decision_pending", []) + by_type.get("negotiation", []) + by_type.get("quotation_sent", []) + by_type.get("price_sent", [])
        if not accepted and state not in {"possible_acceptance", "changed_needs_review", "cancellation_needs_review"}:
            propose("follow_up_customer", "สอบถามการตัดสินใจของลูกค้า โดยเคารพคำขอคิดก่อน", follow_sources or by_type.get("customer_interest", []))
        open_deadlines = [s for s in by_type.get("deadline", []) if any(c.evidence.message_id == s.evidence.message_id for c in open_commitments)]
        propose("schedule_follow_up", "กำหนดเวลาติดตามโดยยืนยันวันที่สัมพัทธ์ก่อน", open_deadlines)
        propose("add_to_revenue_radar", "ติดตามโอกาสรายได้และสถานะถัดไป; ยังไม่ใช่รายได้ที่รับรู้", ([s for s in amounts if s.id in opportunity.signal_ids] or by_type.get("customer_interest", []) or by_type.get("quotation_request", []) or by_type.get("price_enquiry", []) or open_quotes))
    warnings = []
    if any(m.actor == "unknown" for m in messages):
        warnings.append("unknown_speakers_require_review; use ลูกค้า: / ร้าน:")
    date_signals = [s for s in signals if s.type in DATE_TYPES]
    if date_signals and (reference_date is None or any(s.value["resolved_date"] is None for s in date_signals)):
        warnings.append("some_dates_unresolved; no_overdue_inference" if reference_date else "dates_are_unresolved; no_reference_date_supplied")
    if len(latest) > 1 and not unambiguous:
        warnings.append("multiple_price_options; opportunity_amount_requires_review")
    if any(not _live(s) for s in signals):
        warnings.append("appointment_rescheduled; earlier_slot_superseded")
    if contradicted:
        warnings.append("acceptance_contradicted_by_evidence; confirm_with_customer")
    if foreign:
        warnings.append("non_thb_amount; not_used_for_thb_opportunity")
    if by_type.get("possible_reschedule"):
        warnings.append("reschedule_not_confirmed; existing_slot_kept")
    if price_relation_unclear:
        warnings.append("later_price_relation_unclear; kept_earlier_explicit_total_for_review")
    if by_type.get("payment_reported"):
        warnings.append("payment_reported_not_verified")
    if not inactive and partial_payment:
        warnings.append("partial_payment_reported; remaining_amount_unconfirmed")
    if state in {"possible_acceptance", "changed_needs_review", "cancellation_needs_review", "acceptance_needs_review"}:
        warnings.append(f"deal_status_{state}")
    review = bool(warnings) or any(s.confidence < 0.80 for s in signals)
    _validate_final(signals, actions, messages)
    return Analysis("0.1", provider.name, reference_date.isoformat() if reference_date else None, messages, signals, commercial,
                    bool(by_type.get("customer_interest")), pending, accepted, state, status_sources,
                    opportunity, missing, actions, review, warnings)
