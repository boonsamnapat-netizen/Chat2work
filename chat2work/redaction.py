"""Typed redaction placeholders.

Anonymised pilot conversations replace personal data with typed placeholders such as ``[ที่อยู่]``
(see PILOT_EVALUATION_PLAN.md). The engine treats a placeholder as "this kind of information was
given here" so redaction does not change the analysis: a redacted map link still counts as an
address. Placeholders carry no content and are never expanded.
"""
import re

PLACEHOLDERS = {
    "address": ("ที่อยู่", "พิกัด", "แผนที่", "ลิงก์แผนที่", "address", "location", "map"),
    "customer_name": ("ชื่อลูกค้า", "ชื่อ", "name"),
    "shop_name": ("ชื่อร้าน",),
    "phone": ("เบอร์", "เบอร์โทร", "phone"),
    "line_id": ("ไลน์", "line"),
    "email": ("อีเมล", "email"),
    "bank_account": ("บัญชี", "account"),
    "id_number": ("เลขประจำตัว", "id"),
    "licence_plate": ("ทะเบียน",),
}


def placeholder(kind: str) -> str:
    """Regex for a typed placeholder of ``kind``: ``[ที่อยู่]``, ``<ที่อยู่>`` or ``[ADDRESS]``."""
    names = "|".join(re.escape(n) for n in sorted(PLACEHOLDERS[kind], key=len, reverse=True))
    return rf"(?i:\[(?:{names})\]|<(?:{names})>)"


ADDRESS_PLACEHOLDER = placeholder("address")
