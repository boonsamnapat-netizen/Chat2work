"""Small explicit semantic layer: split a Thai message into clauses and classify an event in one.

Before the rules change a deal state or close an obligation they ask two questions:

* WHAT does the event target? (``event_target``: purchase, document, information, payment, appointment)
* WHETHER the clause asserts it (``classify_clause``): one of ``asserted``, ``negated``, ``conditional``,
  ``future``, ``questioned``, ``reported`` or ``uncertain``.

This is a heuristic for Thai chat, not a parser. It is deliberately small and fully deterministic.
"""
import re
from dataclasses import dataclass

STATUSES = ("asserted", "negated", "conditional", "future", "questioned", "reported", "uncertain")

# Clause boundaries: whitespace, and conjunctions that start a new clause even without a space.
_BOUNDARY = re.compile(r"\s+|(?=แต่|และ(?!ก็)|ที่เหลือ|ส่วนที่เหลือ)")

CONDITIONAL = r"ถ้า|หาก|สมมติ|ถ้าเกิด|พอ(?!ดี|แล้ว|ใจ)|เมื่อ(?!วาน|ไร|ไหร่|กี้|คืน)|หลังจาก|หลัง(?=\S{0,6}เสร็จ)|ในกรณี|กรณีที่"
QUESTION = r"ไหม|มั้ย|ไม๊|หรือยัง|รึยัง|หรือเปล่า|รึเปล่า|หรือป่าว|ใช่ไหม|ใช่มั้ย|\?|เมื่อไร|เมื่อไหร่|ยังไง|อย่างไร|ได้ยังไง"
UNCERTAIN = r"มั้ง|มั๊ง|ม้าง|น่าจะ|คง(?!ที่|เหลือ)|ไม่แน่ใจ|คิดว่า|อาจจะ|อาจ|ประมาณว่า|เหมือนจะ"
FUTURE = r"(?<!น่า)จะ|เดี๋ยว|พรุ่งนี้|ค่อย|ทีหลัง|เย็นนี้|คืนนี้|บ่ายนี้|อาทิตย์หน้า|สัปดาห์หน้า"
NEGATION = r"ไม่|ยังไม่|มิได้|ไม่ได้"
REPORTED = (r"(?:เพื่อน|แฟน|แม่|พ่อ|หัวหน้า|ภรรยา|สามี|เขา|เค้า|ที่บ้าน|เจ้านาย|ลูกค้า)\S{0,6}บอก"
            r"|(?<!ผม)(?<!ฉัน)(?<!เรา)(?<!หนู)(?:บอกว่า|พูดว่า)")


@dataclass(frozen=True)
class Clause:
    text: str
    start: int
    end: int


# A chunk that only continues the previous clause: Latin words, numbers, amounts and particles
# ("แนบไฟล์ใบเสนอราคา PDF ให้แล้วครับ", "โอนแล้ว 1000 บาท", "ส่ง quotation ทางอีเมลแล้ว").
_CONTINUATION = re.compile(r"^(?:[A-Za-z0-9.,/#@:+\-]+$|(?:ให้|ไป|มา|ทาง|ด้วย|นะ|ครับ|ค่ะ|คะ|จ้า|บาท)(?!ถ้า|หาก))")


def clauses(text: str) -> list[Clause]:
    """Split a message into clauses at spaces and clause-starting conjunctions."""
    out, pos = [], 0
    bounds = [(m.start(), m.end()) for m in _BOUNDARY.finditer(text)] + [(len(text), len(text))]
    for start, end in bounds:
        if start > pos:
            chunk = Clause(text[pos:start], pos, start)
            if out and _CONTINUATION.match(chunk.text) and not re.match(r"^(?:แต่|และ|ที่เหลือ|ส่วนที่เหลือ)", chunk.text):
                prev = out.pop()
                chunk = Clause(text[prev.start:start], prev.start, start)
            out.append(chunk)
        pos = max(pos, end)
    return out or [Clause(text, 0, len(text))]


def clause_at(text: str, position: int) -> tuple[int, list[Clause]]:
    parts = clauses(text)
    index = next((i for i, c in enumerate(parts) if c.start <= position < c.end), len(parts) - 1)
    return index, parts


def classify_clause(text: str, position: int, *, completed: bool = False) -> str:
    """Status of the event whose wording starts at ``position``.

    Markers are read within the event's clause; a condition introduced by ``ถ้า``/``หาก`` in the
    previous clause also governs this one ("ถ้าลดได้ เอาครับ"). Reported speech is checked in the
    message text before the event. With ``completed=True`` a future marker after a completed
    ``แล้ว`` belongs to a following action ("ส่งแล้ว จะโทรแจ้ง") and does not make the event future.
    """
    i, parts = clause_at(text, position)
    clause = parts[i]
    local = position - clause.start
    before, whole = clause.text[:local], clause.text
    previous = parts[i - 1].text if i else ""
    if re.search(QUESTION, whole):
        return "questioned"
    if re.search(CONDITIONAL, before) or re.match(r"^(?:แต่|และ|ก็)?(?:ถ้า|หาก)", previous):
        return "conditional"
    if re.search(REPORTED, text[:position]):
        return "reported"
    if re.search(r"(?:" + NEGATION + r")\S{0,4}$", before):
        return "negated"
    if re.search(UNCERTAIN, whole) or re.search(r"ไม่แน่ใจ|คิดว่า", text[:position]):
        return "uncertain"
    future_scope = before if completed else whole
    if re.search(FUTURE, future_scope):
        return "future"
    return "asserted"


# --- targets ------------------------------------------------------------------------------

TARGETS = (
    ("payment", r"โอน|จ่าย|ชำระ|มัดจำ|เงิน"),
    ("document", r"ใบเสนอราคา|ใบเสนอ|quotation|ใบแจ้งหนี้|ใบกำกับ|invoice"),
    ("information", r"แคต(?:ต)?าล็อ[กค]|catalog|โบรชัวร์|รูป|ภาพ|วิดีโอ|คลิป|ตัวอย่าง|สเปค|สเปก|ลิงก์|ข้อมูล"),
    ("appointment", r"นัด|ติดตั้ง|ซ่อม|เข้าหน้างาน|หน้างาน|สำรวจ|คิว|ช่าง|เข้าทำ|เข้าไป"),
    ("purchase", r"ออเดอร์|คำสั่งซื้อ|สินค้า|งาน(?!ส่ง)|ทั้งหมด|ซื้อ|จ้าง"),
)


def event_target(text: str, position: int, *, window: int = 24) -> str | None:
    """The first recognised object right after an event word, e.g. ``เลื่อน|โอนมัดจำ`` -> payment.

    Returns None when the event word has no explicit object ("ขอเลื่อนเป็นวันศุกร์")."""
    after = text[position:position + window]
    best = None
    for kind, pattern in TARGETS:
        m = re.search(pattern, after)
        if m and (best is None or m.start() < best[1]):
            best = (kind, m.start())
    return best[0] if best else None
