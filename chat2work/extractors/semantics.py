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
UNCERTAIN = r"มั้ง|มั๊ง|ม้าง|น่าจะ|คง(?!ที่|เหลือ)|ไม่แน่ใจ|คิดว่า|(?<!เ)อาจ(?:จะ)?|ประมาณว่า|เหมือนจะ"  # not "เอาจ้า"
FUTURE = r"(?<!น่า)จะ|เดี๋ยว|พรุ่งนี้|ค่อย|ทีหลัง|เย็นนี้|คืนนี้|บ่ายนี้|อาทิตย์หน้า|สัปดาห์หน้า"
NEGATION = r"ไม่|ยังไม่|มิได้|ไม่ได้"
REPORTED = (r"(?:เพื่อน|แฟน|แม่|พ่อ|หัวหน้า|ภรรยา|สามี|เขา|เค้า|ที่บ้าน|เจ้านาย|ลูกค้า)\S{0,6}บอก"
            r"|(?<!ผม)(?<!ฉัน)(?<!เรา)(?<!หนู)(?<!ผมก็)(?:บอกว่า|พูดว่า)")  # "ผมบอกว่า…" is the speaker's own word
# After reported words, a contrastive first-person clause gives the floor back to the speaker:
# "เพื่อนบอกว่าดี | แต่ผมไม่ซื้อครับ" is the customer's own refusal.
SPEAKER_RETURN = r"(?:แต่|ส่วน)\s*(?:ผม|หนู|เรา|ฉัน|ดิฉัน|กระผม|ตัวเอง)"
# A condition that already has its own consequent ("ถ้าส่งไม่ทันไม่เป็นไร") is closed: it does not
# govern the next clause ("ถ้าใบเสนอราคาส่งไม่ทันไม่เป็นไร | ผมยกเลิกงานนี้ครับ").
CLOSED_CONDITION = r"ไม่เป็นไร|ไม่เป็นปัญหา|ไม่ว่ากัน|ก็ได้|ก็โอเค"


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
    if re.search(CONDITIONAL, before) or opens_condition(previous):
        return "conditional"
    if reported_at(text, position):
        return "reported"
    if re.search(r"(?:" + NEGATION + r")\S{0,4}$", before):
        return "negated"
    if re.search(UNCERTAIN, whole) or re.search(r"ไม่แน่ใจ|คิดว่า", text[:position]):
        return "uncertain"
    future_scope = before if completed else whole
    if re.search(FUTURE, future_scope):
        return "future"
    return "asserted"


def opens_condition(clause_text: str) -> bool:
    """A clause introducing a condition for what follows: it starts with ถ้า/หาก and is not closed."""
    return bool(re.match(r"^(?:แต่|และ|ก็)?(?:ถ้า|หาก)", clause_text)) and not re.search(CLOSED_CONDITION, clause_text)


def closed_conditions(text: str) -> list[Clause]:
    """Conditional clauses that carry their own consequent; their markers belong to them alone."""
    return [c for c in clauses(text) if re.match(r"^(?:แต่|และ|ก็)?(?:ถ้า|หาก)", c.text) and re.search(CLOSED_CONDITION, c.text)]


def without_closed_conditions(text: str) -> str:
    """The message with closed conditional clauses blanked out (same length, positions preserved)."""
    for c in closed_conditions(text):
        text = text[:c.start] + " " * (c.end - c.start) + text[c.end:]
    return text


def reported_at(text: str, position: int) -> bool:
    """True when the words at ``position`` are someone else's reported speech: an attribution comes
    before them and the speaker has not taken the floor back ("แต่ผม…") in between."""
    last = None
    for m in re.finditer(REPORTED, text[:position]):
        last = m
    return last is not None and not re.search(SPEAKER_RETURN, text[last.end():position])


def hedged(text: str, clause_pattern: str) -> bool:
    """A hedge (มั้ง, น่าจะ, คง, อาจ, คิดว่า…) that qualifies the event matched by ``clause_pattern``:
    in the event's own clause, or in a neighbouring clause that holds nothing but the hedge, particles
    and a repeated decision verb ("เอาครับ | มั้งนะ", "เอาครับ | น่าจะเอานะ", "ไม่แน่ใจ | แต่เอาครับ").
    A hedge about something else ("เอาครับ | น่าจะสะดวกวันเสาร์") does not qualify it."""
    parts = clauses(text)
    events = [i for i, c in enumerate(parts) if re.search(clause_pattern, c.text)]
    for i in events:
        if re.search(UNCERTAIN, parts[i].text):
            return True
        for j in (i - 1, i + 1):
            if 0 <= j < len(parts) and re.search(UNCERTAIN, parts[j].text) and re.fullmatch(_HEDGE_ONLY, parts[j].text):
                return True
    return False


_HEDGE_ONLY = (r"(?:แต่|ก็|ผม|หนู|เรา|ฉัน|" + UNCERTAIN + r"|เอา|ซื้อ|ตกลง|จ้าง|สั่ง|ยืนยัน|ตามนี้|เลย|นะ|ครับ|ค่ะ|คะ|จ้า|ค่า|แหละ|ละ|"
               r"น้า|คับ|[\s,.!])+")


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
