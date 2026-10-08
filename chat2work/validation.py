"""Per-type value validation at the extractor boundary.

Any extractor (the rule baseline or a future model adapter) must return values the core can derive
from safely. Exact evidence and a high confidence show where a signal came from; they do not prove
that its value is well formed or that its meaning is right. Invalid values raise ``ValueError``
naming the signal type, before any state or opportunity is derived.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

MONEY_ROLES = {"price", "total", "deposit", "budget", "unit_price", "previous_price", "discount", "balance", "payment",
               "gift_value", "included_component", "expense", "competitor_price"}
DATE_KINDS = {"date", "time"}
DATE_TYPES = {"deadline", "schedule", "temporal_mention"}
SLOT_STATUSES = {"superseded", "replacement"}
_CANONICAL_AMOUNT = re.compile(r"\d+(?:\.\d+)?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class SignalValueError(ValueError):
    pass


def _fail(signal, problem: str) -> None:
    raise SignalValueError(f"Invalid {signal.type} value in signal {signal.id}: {problem}")


def positive_amount(value: object) -> bool:
    """A canonical, finite, positive decimal string such as "18500" or "1250.50"."""
    if not isinstance(value, str) or not _CANONICAL_AMOUNT.fullmatch(value):
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite() and number > 0


def _iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def validate_signal_values(signals, messages) -> None:
    message_ids = {m.id for m in messages}
    for s in signals:
        v = s.value
        if s.type == "monetary_amount":
            if not isinstance(v, dict):
                _fail(s, "expected an object with amount, currency, role and raw")
            missing = {"amount", "currency", "role", "raw"} - set(v)
            if missing:
                _fail(s, "missing " + ", ".join(sorted(missing)))
            if not positive_amount(v["amount"]):
                _fail(s, f"amount must be a canonical finite positive decimal string, got {v['amount']!r}")
            if not isinstance(v["currency"], str) or not _CURRENCY.fullmatch(v["currency"]):
                _fail(s, f"currency must be an ISO 4217 code such as THB, got {v['currency']!r}")
            if v["role"] not in MONEY_ROLES:
                _fail(s, f"unknown money role {v['role']!r}")
            if not isinstance(v["raw"], str) or not v["raw"]:
                _fail(s, "raw must be the non-empty source text")
        elif s.type in DATE_TYPES:
            if not isinstance(v, dict):
                _fail(s, "expected an object with raw, kind, resolved_date and resolution")
            missing = {"raw", "kind", "resolved_date", "resolution"} - set(v)
            if missing:
                _fail(s, "missing " + ", ".join(sorted(missing)))
            if not isinstance(v["raw"], str) or not v["raw"] or v["raw"] not in s.evidence.text:
                _fail(s, "raw must be text found in the evidence message")
            if v["kind"] not in DATE_KINDS:
                _fail(s, f"kind must be one of {sorted(DATE_KINDS)}, got {v['kind']!r}")
            if v["resolved_date"] is not None and not _iso_date(v["resolved_date"]):
                _fail(s, f"resolved_date must be null or an ISO date, got {v['resolved_date']!r}")
            if not isinstance(v["resolution"], str):
                _fail(s, "resolution must be a string")
        elif not isinstance(v, str) or not v:
            _fail(s, "expected a non-empty string")
        meta = s.metadata
        if not isinstance(meta, dict):
            _fail(s, "metadata must be an object")
        for key in ("amount", "reported_amount"):
            if key in meta and not positive_amount(meta[key]):
                _fail(s, f"metadata {key} must be a canonical finite positive decimal string, got {meta[key]!r}")
        if "offer_message_id" in meta and meta["offer_message_id"] not in message_ids:
            _fail(s, f"metadata offer_message_id {meta['offer_message_id']!r} is not a supplied message")
        if "slot_status" in meta and meta["slot_status"] not in SLOT_STATUSES:
            _fail(s, f"metadata slot_status must be one of {sorted(SLOT_STATUSES)}")


def validate_references(signals) -> None:
    """Derived-node references must point at signals that exist."""
    ids = {s.id for s in signals}
    for s in signals:
        refs = list(s.metadata.get("derived_from", [])) + ([s.metadata["superseded_by"]] if "superseded_by" in s.metadata else [])
        if any(r not in ids for r in refs):
            _fail(s, "metadata references a signal that does not exist")
