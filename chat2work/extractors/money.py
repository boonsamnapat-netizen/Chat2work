"""Extract only explicit amounts; never multiply prices by quantities."""
import re
from decimal import Decimal

# Reject digits glued to times (18:00), dates (18/5), phone/ID segments (089-000) and decimals.
NUMBERS = re.compile(r"(?<![\d,./:\-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?![\d,]|[:/\-]\d|\.\d)")
UNITS = re.compile(r"\s*(?:BTU\b|บีทียู|เครื่อง|ตัว|ชุด|ชิ้น|ใบ|แผ่น|ผืน|เล่ม|ม้วน|แผง|แกรม|ลูก|ดวง|กล่อง|ห้อง|เมตร|ตร\.?ม|ตารางเมตร|วัตต์|kW\b|กิโลวัตต์|วัน|เดือน|ปี|ครั้ง|คน|%|เปอร์เซ็นต์|โมง|ทุ่ม|นาฬิกา|น\.|จุด|ต\.ค|พ\.ย|ธ\.ค|ม\.ค|ก\.พ|มี\.ค|เม\.ย|พ\.ค|มิ\.ย|ก\.ค|ส\.ค|ก\.ย|มกรา|กุมภา|มีนา|เมษา|พฤษภา|มิถุนา|กรกฎา|สิงหา|กันยา|ตุลา|พฤศจิกา|ธันวา)", re.I)
# "งบ" (budget) without matching inside words such as "ทั้งบ้าน".
BUDGET = r"(?<!ทั้)งบ(?![\u0E31\u0E34-\u0E3A\u0E47-\u0E4E])"
PER_UNIT = r"(?:เครื่อง|ชุด|ตัว|ชิ้น|ใบ|แผ่น|ผืน|ดวง|กล่อง|ห้อง|จุด|เดือน|ปี|ครั้ง|วัน|คน|ชั่วโมง|เล่ม|ม้วน|แผง|ลูก|ต้น|งาน|โพสต์|คลิป|ตารางเมตร|ตร\.?ม\.?|เมตร)ละ"
PRICE_PREFIX = re.compile(r"(?:ราคา(?:เดิม|ใหม่|รวม)?|" + BUDGET + r"(?:ประมาณ)?(?:ไม่เกิน)?|มัดจำ|ยอด(?:รวม|ทั้งหมด|คงเหลือ)?|ค่า\S{0,12}|โอน|ชำระ|เหลือ|ลด(?:ราคา)?|ส่วนลด|รวม(?:ทั้งหมด)?|ทั้งหมด|" + PER_UNIT + r")\s*(?:อยู่ที่|คือ|ประมาณ|แค่|ที่|อีก|ไว้|ให้|ก่อน|บาท|ไม่เกิน|ไม่เกินงบ)?\s*฿?\s*$")
CURRENCY_AFTER = re.compile(r"\s*(?:บาท|฿|THB\b|\.-)", re.I)
IDENTIFIER_BEFORE = re.compile(r"(?:เบอร์|โทร|บัญชี|เลขที่|ออเดอร์|รุ่น|order|no\.?|#)\s*$", re.I)


def extract_amounts(text: str, *, allow_bare: bool = False) -> list[dict]:
    """Return explicit THB amounts with a role.

    ``allow_bare`` accepts a number without a price keyword or currency, used only
    when the caller knows the message answers a direct price question.
    """
    amounts = []
    for match in NUMBERS.finditer(text):
        raw = match.group()
        before, after = text[max(0, match.start()-30):match.start()], text[match.end():]
        currency = bool(CURRENCY_AFTER.match(after)) or before.rstrip().endswith("฿")
        # Reject unsupported scales rather than silently underpricing (18.5k is not 18.5).
        if re.match(r"\s*(?:[kKmMbB]\b|พัน|หมื่น|แสน|ล้าน)", after):
            continue
        if not currency and re.match(r"\s*[A-Za-z]", after):
            continue
        if IDENTIFIER_BEFORE.search(before):
            continue
        # Leading zeros are phone numbers, account numbers or codes, not prices.
        if raw.startswith("0") and len(raw.split(".")[0]) > 1:
            continue
        if not currency and UNITS.match(after):
            continue
        bare_ok = allow_bare and ("," in raw or len(raw.split(".")[0]) >= 3)
        if not currency and not PRICE_PREFIX.search(before) and not bare_ok:
            continue
        number = Decimal(raw.replace(",", ""))
        if number <= 0:
            continue
        amounts.append({"amount": format(number, "f"), "currency": "THB", "role": _role(before[-25:], after), "raw": raw})
    return amounts


def _role(prefix: str, after: str) -> str:
    def near(pattern: str) -> bool:
        return re.search(f"(?:{pattern})[^\\d]*$", prefix) is not None

    if near(r"มัดจำ|เงินดาวน์"):
        return "deposit"
    if near(BUDGET + r"|ไม่เกิน"):
        return "budget"
    if near(r"ราคาเดิม"):
        return "previous_price"
    if near(r"ส่วนลด|ลดให้|ลด\s*$"):
        return "discount"
    if near(r"คงเหลือ|เหลือจ่าย|ที่เหลือ|ยอดค้าง"):
        return "balance"
    if near(r"โอน|ชำระ"):
        return "payment"
    if near(PER_UNIT) or re.match(r"\s*(?:บาท)?\s*(?:ต่อ|/)\s*\S", after):
        return "unit_price"
    if near(r"รวม|ทั้งหมด"):
        return "total"
    return "price"
