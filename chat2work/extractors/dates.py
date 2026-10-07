"""Preserve relative Thai date/time expressions; resolve only with a reference date.

Without a reference date ``resolved_date`` is always null. With one, only
unambiguous expressions are resolved; anything else stays null with a reason.
"""
import re
from datetime import date, timedelta

WEEKDAYS = {"จันทร์": 0, "อังคาร": 1, "พุธ": 2, "พฤหัสบดี": 3, "พฤหัส": 3, "ศุกร์": 4, "เสาร์": 5, "อาทิตย์": 6}
MONTHS = {
    "มกราคม": 1, "ม.ค.": 1, "กุมภาพันธ์": 2, "ก.พ.": 2, "มีนาคม": 3, "มี.ค.": 3, "เมษายน": 4, "เม.ย.": 4,
    "พฤษภาคม": 5, "พ.ค.": 5, "มิถุนายน": 6, "มิ.ย.": 6, "กรกฎาคม": 7, "ก.ค.": 7, "สิงหาคม": 8, "ส.ค.": 8,
    "กันยายน": 9, "ก.ย.": 9, "ตุลาคม": 10, "ต.ค.": 10, "พฤศจิกายน": 11, "พ.ย.": 11, "ธันวาคม": 12, "ธ.ค.": 12,
}
_WD = "พฤหัสบดี|พฤหัส|จันทร์|อังคาร|พุธ|ศุกร์|เสาร์"  # bare อาทิตย์ is ambiguous (Sunday/week)
_MONTH = "|".join(re.escape(m) for m in sorted(MONTHS, key=len, reverse=True))
_THAI_NUM = "หนึ่ง|สอง|สาม|สี่|ห้า"

DATES = re.compile(
    rf"\d{{1,2}}\s*(?:{_MONTH})(?:\s*(?:\d{{4}}|\d{{2}})(?![\d:.]|\s*(?:โมง|นาฬิกา|ทุ่ม|น\.)))?"
    rf"|\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?"
    r"|วันนี้|พรุ่งนี้|มะรืนนี้|เย็นนี้|คืนนี้|เช้านี้|บ่ายนี้"
    r"|อาทิตย์หน้า|สัปดาห์หน้า|อาทิตย์นี้|สัปดาห์นี้|สิ้นเดือน(?:นี้|หน้า)?|ต้นเดือน(?:นี้|หน้า)?|เดือนหน้า"
    rf"|วัน(?:{_WD}|อาทิตย์)(?:นี้|หน้า)?|(?:{_WD})(?:นี้|หน้า)"
    r"|\d{1,2}[:.]\d{2}\s*น\.|\d{1,2}:\d{2}"
    rf"|บ่าย\s*(?:\d{{1,2}}|{_THAI_NUM})(?:\s*โมง)?|บ่ายโมง|\d{{1,2}}\s*(?:โมง(?:เช้า|เย็น)?|นาฬิกา|ทุ่ม)"
    rf"|(?:{_THAI_NUM})ทุ่ม|ทุ่มนึง|สิบโมง|เก้าโมง|แปดโมง|เที่ยง(?:วัน|คืน)?"
)
TIME = re.compile(r"\d{1,2}[:.]\d{2}|โมง|นาฬิกา|ทุ่ม|บ่าย\s*(?:\d|สอง|สาม|สี่|ห้า)|เที่ยง")


def extract_dates(text: str) -> list[dict]:
    return [{"raw": m.group(), "kind": "time" if TIME.search(m.group()) else "date",
             "resolved_date": None, "resolution": "no_reference_date"} for m in DATES.finditer(text)]


def resolve(raw: str, reference: date) -> tuple[str | None, str]:
    """Return (ISO date or None, resolution status) for one raw expression."""
    if TIME.search(raw) and not re.search(r"นี้", raw):
        return None, "time_only"
    if raw in {"วันนี้", "เย็นนี้", "คืนนี้", "เช้านี้", "บ่ายนี้"}:
        return reference.isoformat(), "resolved"
    if raw == "พรุ่งนี้":
        return (reference + timedelta(days=1)).isoformat(), "resolved"
    if raw == "มะรืนนี้":
        return (reference + timedelta(days=2)).isoformat(), "resolved"
    weekday = re.fullmatch(rf"(?:วัน)?({_WD}|อาทิตย์)(นี้|หน้า)?", raw)
    if weekday and not (weekday[1] == "อาทิตย์" and weekday[2] and not raw.startswith("วัน")):
        target = WEEKDAYS[weekday[1]]
        delta = (target - reference.weekday()) % 7
        # "หน้า" usage varies (this coming vs. the one after); same-day is ambiguous too.
        if weekday[2] == "หน้า" or delta == 0:
            return None, "ambiguous"
        return (reference + timedelta(days=delta)).isoformat(), "resolved"
    numeric = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", raw)
    month_name = re.fullmatch(rf"(\d{{1,2}})\s*({_MONTH})(?:\s*(\d{{2,4}}))?", raw)
    if numeric or month_name:
        day = int((numeric or month_name)[1])
        month = int(numeric[2]) if numeric else MONTHS[month_name[2]]
        year_raw = (numeric or month_name)[3]
        if year_raw is None:
            year = reference.year
        else:
            year = int(year_raw)
            if year < 100:
                return None, "ambiguous"
            if year > 2400:  # Thai Buddhist Era
                year -= 543
        try:
            resolved = date(year, month, day)
        except ValueError:
            return None, "invalid_date"
        if year_raw is None and resolved < reference:
            return None, "ambiguous"  # past date this year, or next year?
        return resolved.isoformat(), "resolved"
    return None, "unsupported_or_range"
