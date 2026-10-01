"""Núcleo do agente: máquina de estados coletando -> cotando -> cotado | encaminhado."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from typing import Protocol

from . import messages
from .extractor import Extractor
from .models import Conversation, HandoffReason, Plan, Reply, Slots, Stage
from .policy import Policy
from .quote_client import Quote, QuoteRefused, QuoteRejected, QuoteUnavailable
from .store import Store
from .tracing import Tracer


class Quotes(Protocol):
    def list_plans(self, refresh: bool = False) -> list[Plan]: ...
    def quote(
        self, slots: Slots, request_id: str, on_attempt: Callable[[dict], None] | None = None
    ) -> Quote: ...


class Agent:
    def __init__(
        self,
        extractor: Extractor,
        quotes: Quotes,
        store: Store,
        tracer: Tracer,
        policy: Policy | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.extractor, self.quotes, self.store, self.tracer = extractor, quotes, store, tracer
        self.policy = policy or Policy()
        self.today = today

    def handle(self, conversation_id: str, text: str, message_id: str | None = None) -> Reply:
        """Processa uma mensagem do lead; o mesmo message_id devolve a mesma resposta."""
        message_id = message_id or uuid.uuid4().hex
        with self.store.lock(conversation_id):
            conv = self.store.get(conversation_id)
            if message_id in conv.replies:
                return conv.replies[message_id]
            self.tracer.emit("message_in", conversation_id, message_id, text=text)
            reply = self._step(conv, text, message_id)
            conv.replies[message_id] = reply
            self.store.save(conv)
            self.tracer.emit(
                "message_out",
                conversation_id,
                message_id,
                stage=reply.stage,
                handoff_reason=reply.handoff_reason,
                quote_id=reply.quote_id,
                text=reply.text,
            )
            return reply

    def _step(self, conv: Conversation, text: str, message_id: str) -> Reply:
        if conv.stage is Stage.HANDED_OFF:
            return self._reply(conv, message_id, messages.ALREADY_HANDED_OFF)

        conv.turns += 1
        plans = self.quotes.list_plans()
        found = self.extractor.extract(text, plans, self.today(), conv.asked)

        if found.topic:
            return self._handoff(conv, message_id, found.topic)
        if found.wants_human:
            return self._handoff(conv, message_id, HandoffReason.USER_REQUEST)

        invalid = self._drop_invalid(found.slots)
        changed = conv.slots.merge(found.slots)
        conv.stalled = 0 if changed else conv.stalled + (1 if conv.turns > 1 else 0)
        self.tracer.emit("slots", conv.id, message_id, slots=conv.slots.payload(), changed=changed,
                         invalid=invalid)  # fmt: skip

        if conv.stage is Stage.QUOTED and not changed and not invalid:
            return self._reply(conv, message_id, messages.recap(conv.last_price))
        if conv.stalled >= self.policy.max_stalled_turns:
            return self._handoff(conv, message_id, HandoffReason.NO_PROGRESS)
        if invalid:
            conv.asked = invalid[0]
            return self._reply(conv, message_id, " ".join(messages.INVALID[f] for f in invalid))

        gone = self._drop_retired_plan(conv, plans)
        missing = conv.slots.missing()
        if missing:
            if "plano_id" in missing and not plans:  # sem lista de planos não dá para perguntar
                return self._handoff(conv, message_id, HandoffReason.QUOTE_UNAVAILABLE)
            conv.asked = missing[0]
            text = messages.ask(missing, plans, conv.turns == 1)
            return self._reply(conv, message_id, messages.plan_gone(gone) + text if gone else text)
        return self._quote(conv, message_id, plans)

    @staticmethod
    def _drop_retired_plan(conv: Conversation, plans: list[Plan]) -> str | None:
        """Plano escolhido saiu do catálogo (`/planos` mudou): esquece e pergunta de novo."""
        chosen = conv.slots.plano_id
        if chosen and plans and chosen not in {p.id for p in plans}:
            conv.slots.plano_id = None
            return chosen
        return None

    def _drop_invalid(self, slots: dict) -> list[str]:
        """Descarta o que a API cotaria mas não faz sentido: vigência passada, carro do futuro."""
        today = self.today()
        invalid = []
        if slots.get("veiculo_ano") and slots["veiculo_ano"] > today.year + 1:
            invalid.append("veiculo_ano")
        if slots.get("data_inicio") and slots["data_inicio"] < today:
            invalid.append("data_inicio")
        for name in invalid:
            del slots[name]
        return invalid

    def _quote(self, conv: Conversation, message_id: str, plans: list[Plan]) -> Reply:
        request_id = uuid.uuid4().hex

        def on_attempt(info: dict) -> None:
            self.tracer.emit("quote_attempt", conv.id, message_id, request_id=request_id, **info)

        try:
            quote = self.quotes.quote(conv.slots, request_id, on_attempt)
        except QuoteRejected as exc:
            conv.rejections += 1
            self.tracer.emit("quote_rejected", conv.id, message_id, request_id=request_id,
                             detail=exc.detail, fields=exc.fields)  # fmt: skip
            if conv.rejections >= self.policy.max_rejections or not exc.fields:
                return self._handoff(conv, message_id, HandoffReason.QUOTE_REJECTED)
            for name in exc.fields:
                setattr(conv.slots, name, None)
            conv.asked = exc.fields[0]
            label = messages.LABELS.get(conv.asked, "o plano")
            return self._reply(conv, message_id, messages.rejected(exc.detail, label))
        except QuoteRefused as exc:
            self.tracer.emit("quote_refused", conv.id, message_id, request_id=request_id,
                             motivo=exc.motivo)  # fmt: skip
            fresh = self.quotes.list_plans(refresh=True)  # a recusa pode ser catálogo desatualizado
            gone = self._drop_retired_plan(conv, fresh)
            if gone:
                conv.asked = "plano_id"
                ask = messages.ask(["plano_id"], fresh, first_turn=False)
                return self._reply(conv, message_id, messages.plan_gone(gone) + ask)
            return self._handoff(conv, message_id, HandoffReason.QUOTE_REFUSED,
                                 messages.refused(exc.motivo))  # fmt: skip
        except QuoteUnavailable as exc:
            self.tracer.emit("quote_failed", conv.id, message_id, request_id=request_id,
                             reason=exc.reason, attempts=exc.attempts)  # fmt: skip
            return self._handoff(conv, message_id, HandoffReason.QUOTE_UNAVAILABLE)

        conv.stage, conv.rejections, conv.last_price = Stage.QUOTED, 0, quote.price
        self.tracer.emit("quote_ok", conv.id, message_id, request_id=request_id, price=quote.price)
        plan = next((p.nome for p in plans if p.id == conv.slots.plano_id), conv.slots.plano_id)
        return self._reply(
            conv, message_id, messages.quoted(str(plan), quote),
            quote_id=quote.request_id, price=quote.price,
        )  # fmt: skip

    def _handoff(
        self, conv: Conversation, message_id: str, reason: HandoffReason, text: str | None = None
    ) -> Reply:
        conv.stage, conv.handoff_reason = Stage.HANDED_OFF, reason
        self.tracer.emit(
            "handoff", conv.id, message_id, reason=reason, collected=conv.slots.payload()
        )
        return self._reply(
            conv, message_id, text or messages.HANDOFF[reason], handoff_reason=reason
        )

    @staticmethod
    def _reply(conv: Conversation, message_id: str, text: str, **extra) -> Reply:
        return Reply(
            conversation_id=conv.id, message_id=message_id, text=text, stage=conv.stage, **extra
        )
