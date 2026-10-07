"""Provider-independent v0.1 output schema. Confidence is heuristic, not probability."""
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

Actor = Literal["customer", "business", "unknown"]


def confidence_level(confidence: float) -> str:
    if confidence >= 0.90:
        return "high"
    if confidence >= 0.80:
        return "medium"
    return "needs_review"


@dataclass(frozen=True)
class Message:
    id: int
    speaker: str
    actor: Actor
    text: str
    raw_line: str


@dataclass(frozen=True)
class Evidence:
    message_id: int
    speaker: str
    text: str
    raw_line: str


@dataclass(frozen=True)
class Signal:
    id: str
    type: str
    actor: Actor
    value: object
    confidence: float
    evidence: Evidence
    metadata: dict = field(default_factory=dict)

    @property
    def confidence_level(self) -> str:
        return confidence_level(self.confidence)


@dataclass(frozen=True)
class Action:
    type: str
    description: str
    signal_ids: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    confidence: float
    approval_status: str = "proposed"
    requires_human_approval: bool = True


@dataclass(frozen=True)
class Opportunity:
    amount: str | None
    currency: str
    signal_ids: tuple[str, ...]
    confidence: float | None
    reason: str


@dataclass
class Analysis:
    schema_version: str
    provider: str
    reference_date: str | None
    messages: list[Message]
    signals: list[Signal]
    commercial_intent: bool
    customer_interest: bool
    decision_pending: bool
    confirmed_sale: bool
    deal_status: str
    status_signal_ids: list[str]
    potential_revenue: Opportunity
    missing_information: list[Signal]
    recommended_actions: list[Action]
    review_required: bool
    warnings: list[str]

    def to_dict(self) -> dict:
        result = asdict(self)
        for signal in result["signals"] + result["missing_information"]:
            signal["confidence_level"] = confidence_level(signal["confidence"])
        for action in result["recommended_actions"]:
            action["confidence_level"] = confidence_level(action["confidence"])
        return result


class Extractor(Protocol):
    """Future OpenAI/Gemini/Claude/Ollama adapters return the same Signal objects.

    Core validates evidence, IDs, actors and confidence before deriving actions.
    Providers must not perform execution or inject ungrounded suggestions.
    """
    name: str

    def extract(self, messages: list[Message]) -> list[Signal]: ...
