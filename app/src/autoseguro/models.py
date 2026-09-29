"""Modelos de domínio: slots da cotação, conversa e resposta."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from pydantic import BaseModel

# Ordem em que os dados são pedidos ao lead.
SLOT_ORDER = ("idade", "veiculo_ano", "cep", "data_inicio", "plano_id")


class Stage(StrEnum):
    COLLECTING = "collecting"
    QUOTED = "quoted"
    HANDED_OFF = "handed_off"


class HandoffReason(StrEnum):
    USER_REQUEST = "user_request"
    COMPLAINT = "complaint"
    OUT_OF_SCOPE = "out_of_scope"
    NO_PROGRESS = "no_progress"
    QUOTE_UNAVAILABLE = "quote_unavailable"
    QUOTE_REJECTED = "quote_rejected"


@dataclass(frozen=True)
class Plan:
    id: str
    nome: str


class Slots(BaseModel):
    """Dados necessários para `POST /quote`. `None` = ainda não informado."""

    plano_id: str | None = None
    idade: int | None = None
    veiculo_ano: int | None = None
    cep: str | None = None
    data_inicio: date | None = None

    def missing(self) -> list[str]:
        return [s for s in SLOT_ORDER if getattr(self, s) is None]

    def merge(self, new: dict) -> int:
        """Aplica valores novos e devolve quantos campos mudaram."""
        changed = 0
        for key, value in new.items():
            if value is not None and getattr(self, key) != value:
                setattr(self, key, value)
                changed += 1
        return changed

    def payload(self) -> dict:
        return self.model_dump(mode="json")


class Reply(BaseModel):
    conversation_id: str
    message_id: str
    text: str
    stage: Stage
    handoff_reason: HandoffReason | None = None
    quote_id: str | None = None
    price: float | None = None


@dataclass
class Conversation:
    id: str
    slots: Slots = field(default_factory=Slots)
    stage: Stage = Stage.COLLECTING
    asked: str | None = None  # último campo pedido (resolve respostas soltas como "35")
    turns: int = 0
    stalled: int = 0  # turnos seguidos sem nenhum dado novo
    rejections: int = 0  # vezes que a API recusou os dados
    last_price: float | None = None
    handoff_reason: HandoffReason | None = None
    replies: dict[str, Reply] = field(default_factory=dict)  # idempotência por message_id
