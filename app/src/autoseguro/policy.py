"""Critérios de encaminhamento para humano. Fonte única: mudou aqui, mude docs/DECISIONS.md."""

from __future__ import annotations

from dataclasses import dataclass

from .models import HandoffReason

HANDOFF_RULES: dict[HandoffReason, str] = {
    HandoffReason.USER_REQUEST: "O lead pediu para falar com uma pessoa.",
    HandoffReason.COMPLAINT: "Reclamação, ameaça de Procon/justiça ou insatisfação forte.",
    HandoffReason.OUT_OF_SCOPE: "Sinistro, cancelamento, boleto/apólice ou outro produto.",
    HandoffReason.NO_PROGRESS: "Vários turnos seguidos sem nenhum dado novo utilizável.",
    HandoffReason.QUOTE_UNAVAILABLE: (
        "/quote falhou após retries, circuito aberto ou resposta inválida."
    ),
    HandoffReason.QUOTE_REJECTED: "A API recusou os dados de novo depois de o lead corrigir.",
    HandoffReason.QUOTE_REFUSED: (
        "Recusa por regra de negócio da API (idade > 75, veículo > 20 anos)."
    ),
}


@dataclass(frozen=True)
class Policy:
    max_stalled_turns: int = 3
    max_rejections: int = 2
