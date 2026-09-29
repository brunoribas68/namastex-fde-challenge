"""Textos enviados ao lead. Respostas são templates: preço só vem da API, nunca de um LLM."""

from __future__ import annotations

from .models import HandoffReason, Plan

LABELS = {
    "idade": "sua idade",
    "veiculo_ano": "o ano do veículo",
    "cep": "seu CEP",
    "data_inicio": "a data de início da vigência (ex.: 15/07/2026)",
}

HANDOFF = {
    HandoffReason.USER_REQUEST: "Claro! Vou te passar para um de nossos consultores agora.",
    HandoffReason.COMPLAINT: "Sinto muito pelo transtorno. Vou chamar um consultor para "
    "cuidar disso pessoalmente.",
    HandoffReason.OUT_OF_SCOPE: "Esse assunto é com nossa equipe de atendimento. "
    "Já estou te encaminhando para um consultor.",
    HandoffReason.NO_PROGRESS: "Não consegui entender bem os dados. Vou chamar um consultor "
    "para te ajudar.",
    HandoffReason.QUOTE_UNAVAILABLE: "Nosso sistema de cotação está instável agora e não quero "
    "te passar um valor errado. Um consultor vai te retornar com a cotação em breve.",
    HandoffReason.QUOTE_REJECTED: "Não consegui validar esses dados na cotação. Um consultor "
    "vai te ajudar a acertar isso.",
}

ALREADY_HANDED_OFF = (
    "Seu atendimento já foi encaminhado a um consultor, que falará com você em breve."
)
GREETING = "Olá! Sou o assistente da AutoSeguro e vou cotar o seguro do seu veículo. "


def ask(missing: list[str], plans: list[Plan], first_turn: bool) -> str:
    items = []
    for slot in missing:
        if slot == "plano_id":
            items.append("o plano desejado (" + ", ".join(p.nome for p in plans) + ")")
        else:
            items.append(LABELS[slot])
    intro = GREETING if first_turn else ""
    if len(items) == 1:
        return f"{intro}Falta só {items[0]}."
    bullets = "\n".join(f"- {i}" for i in items)
    return f"{intro}Para cotar, me informe:\n{bullets}"


def money(value: float) -> str:
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def quoted(plan: str, price: float, quote_id: str) -> str:
    return (
        f"Cotação do plano {plan}: {money(price)}.\n"
        f"Código da cotação: {quote_id[:8]}.\n"
        "Quer simular outra opção? É só me dizer o que muda (ex.: outro plano)."
    )


def recap(price: float | None) -> str:
    valor = f" ({money(price)})" if price else ""
    return (
        f"Sua cotação{valor} continua valendo. Para simular outra opção, me diga o dado que muda "
        "ou peça um atendente."
    )


def rejected(detail: str, field_label: str) -> str:
    return f"A cotação não aceitou os dados: {detail}. Pode me confirmar {field_label}?"
