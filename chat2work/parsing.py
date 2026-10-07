"""Explicit speaker parsing; unknown labels are never guessed to be customers."""
import re
from .models import Message

CUSTOMERS = {"ลูกค้า", "ผู้ซื้อ", "customer", "client"}
BUSINESSES = {"ร้าน", "ช่าง", "บริษัท", "ผู้ขาย", "แอดมิน", "business", "seller", "shop", "admin"}
# Optional leading chat timestamp: "10:30 ", "[10:30] ", "10.30 น. "
TIMESTAMP = re.compile(r"^\s*\[?\d{1,2}[:.]\d{2}(?:\s*น\.)?\]?\s+")
# "ลูกค้า (คุณเอ)" keeps the role keyword; the bracketed name is ignored for role.
ROLE_WITH_NAME = re.compile(r"^(.+?)\s*[(\[].*[)\]]$")


def _actor(speaker: str, customers: set[str], businesses: set[str]) -> str:
    label = speaker.casefold()
    base = ROLE_WITH_NAME.match(label)
    for candidate in (label, base[1].strip() if base else None):
        if candidate in customers:
            return "customer"
        if candidate in businesses:
            return "business"
    return "unknown"


def parse_conversation(text: str, *, customer_speakers=frozenset(), business_speakers=frozenset()) -> list[Message]:
    """One message per non-empty line in ``Speaker: text`` form (tab-separated
    ``time<TAB>speaker<TAB>text`` exports are also accepted). Extra speaker names
    can be mapped explicitly; anything else is ``unknown`` and needs review."""
    customers = CUSTOMERS | {s.casefold() for s in customer_speakers}
    businesses = BUSINESSES | {s.casefold() for s in business_speakers}
    if customers & businesses:
        raise ValueError("A speaker label cannot be both customer and business")
    messages = []
    for line in text.splitlines():
        if not line.strip():
            continue
        tabbed = line.split("\t")
        if len(tabbed) >= 3 and TIMESTAMP.match(tabbed[0] + " "):
            speaker, content = tabbed[1].strip(), "\t".join(tabbed[2:]).strip()
        else:
            body = TIMESTAMP.sub("", line, count=1)
            match = re.match(r"^\s*([^:：]{1,40})[:：](.*)$", body)
            speaker, content = (match[1].strip(), match[2].strip()) if match else ("unknown", body.strip())
        messages.append(Message(len(messages), speaker, _actor(speaker, customers, businesses), content, line))
    return messages
