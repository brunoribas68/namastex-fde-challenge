from autoseguro.models import HandoffReason, Stage
from autoseguro.quote_client import Quote, QuoteRefused, QuoteRejected, QuoteUnavailable

from .conftest import FakeQuotes

FULL = "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026, plano completo"


def test_happy_path_multi_turn(make_agent):
    agent, quotes = make_agent()
    r1 = agent.handle("c1", "Oi, quero cotar")
    assert r1.stage is Stage.COLLECTING and "Olá" in r1.text and "idade" in r1.text
    r2 = agent.handle("c1", "35")
    assert "Falta" in r2.text or "informe" in r2.text
    r3 = agent.handle("c1", "carro 2022, cep 01310-100, começo em 15/07/2026, plano completo")
    assert r3.stage is Stage.QUOTED
    assert r3.price == 1234.5 and r3.quote_id and "1.234,50" in r3.text
    assert len(quotes.calls) == 1


def test_quotes_in_one_message(make_agent):
    agent, _ = make_agent()
    assert agent.handle("c1", FULL).stage is Stage.QUOTED


def test_asks_only_for_missing(make_agent):
    agent, _ = make_agent()
    reply = agent.handle("c1", "Tenho 35 anos, carro 2022, CEP 01310-100, plano completo")
    assert reply.stage is Stage.COLLECTING and "data" in reply.text


def test_user_asks_for_human(make_agent):
    agent, quotes = make_agent()
    reply = agent.handle("c1", "prefiro falar com um atendente")
    assert reply.handoff_reason is HandoffReason.USER_REQUEST
    assert quotes.calls == []


def test_out_of_scope_and_complaint(make_agent):
    agent, _ = make_agent()
    assert agent.handle("a", "tive um sinistro").handoff_reason is HandoffReason.OUT_OF_SCOPE
    assert agent.handle("b", "vou ao Procon").handoff_reason is HandoffReason.COMPLAINT


def test_quote_unavailable_hands_off_without_inventing_price(make_agent):
    agent, _ = make_agent(FakeQuotes([QuoteUnavailable("http_503", 4)]))
    reply = agent.handle("c1", FULL)
    assert reply.handoff_reason is HandoffReason.QUOTE_UNAVAILABLE
    assert reply.price is None and reply.quote_id is None and "R$" not in reply.text


def test_rejection_asks_to_fix_then_recovers(make_agent):
    rejection = QuoteRejected("ano inválido", ["veiculo_ano"])
    agent, quotes = make_agent(FakeQuotes([rejection]))
    r1 = agent.handle("c1", FULL)
    assert r1.stage is Stage.COLLECTING and "ano inválido" in r1.text
    r2 = agent.handle("c1", "2021")
    assert r2.stage is Stage.QUOTED
    assert quotes.calls[-1].veiculo_ano == 2021


def test_repeated_rejection_hands_off(make_agent):
    rejection = QuoteRejected("ano inválido", ["veiculo_ano"])
    agent, _ = make_agent(FakeQuotes([rejection, rejection]))
    agent.handle("c1", FULL)
    reply = agent.handle("c1", "2020")
    assert reply.handoff_reason is HandoffReason.QUOTE_REJECTED


def test_rejection_without_known_field_hands_off(make_agent):
    agent, _ = make_agent(FakeQuotes([QuoteRejected("erro genérico", [])]))
    assert agent.handle("c1", FULL).handoff_reason is HandoffReason.QUOTE_REJECTED


def test_no_progress_hands_off_but_greeting_does_not_count(make_agent):
    agent, _ = make_agent()
    assert agent.handle("c1", "oi").stage is Stage.COLLECTING
    assert agent.handle("c1", "hmm").stage is Stage.COLLECTING
    assert agent.handle("c1", "não sei").stage is Stage.COLLECTING
    assert agent.handle("c1", "talvez").handoff_reason is HandoffReason.NO_PROGRESS


def test_no_plans_available_hands_off(make_agent):
    agent, _ = make_agent(FakeQuotes(plans=[]))
    reply = agent.handle("c1", "Tenho 35 anos, carro 2022, CEP 01310-100, dia 15/07/2026")
    assert reply.handoff_reason is HandoffReason.QUOTE_UNAVAILABLE


def test_bot_stays_quiet_after_handoff(make_agent):
    agent, quotes = make_agent()
    agent.handle("c1", "quero um atendente")
    reply = agent.handle("c1", FULL)
    assert reply.stage is Stage.HANDED_OFF and "encaminhado" in reply.text
    assert quotes.calls == []


def test_requote_when_lead_changes_data(make_agent):
    agent, quotes = make_agent()
    agent.handle("c1", FULL)
    reply = agent.handle("c1", "e no plano essencial?")
    assert reply.stage is Stage.QUOTED and len(quotes.calls) == 2
    assert quotes.calls[-1].plano_id == "essencial"


def test_message_without_new_data_after_quote_only_recaps(make_agent):
    agent, quotes = make_agent()
    agent.handle("c1", FULL)
    reply = agent.handle("c1", "obrigado")
    assert "continua valendo" in reply.text and len(quotes.calls) == 1


def test_duplicate_message_id_is_idempotent(make_agent):
    agent, quotes = make_agent()
    first = agent.handle("c1", FULL, message_id="m1")
    again = agent.handle("c1", FULL, message_id="m1")
    assert first == again and len(quotes.calls) == 1


def test_trace_links_messages_and_quotes_without_pii(make_agent, trace_buffer):
    import json

    agent, _ = make_agent()
    agent.handle("c1", "meu cpf 123.456.789-09, " + FULL, message_id="m1")
    events = [json.loads(line) for line in trace_buffer.getvalue().splitlines()]
    kinds = [e["event"] for e in events]
    assert kinds == ["message_in", "slots", "quote_ok", "message_out"]
    assert all(e["conversation_id"] == "c1" and e["message_id"] == "m1" for e in events)
    assert events[2]["request_id"] == events[3]["quote_id"]
    assert "123.456.789-09" not in trace_buffer.getvalue()
    assert "01310-100" not in trace_buffer.getvalue()


def test_business_refusal_explains_reason_and_hands_off(make_agent):
    agent, _ = make_agent(FakeQuotes([QuoteRefused("Veiculo com mais de 20 anos nao e aceito.")]))
    reply = agent.handle("c1", FULL)
    assert reply.handoff_reason is HandoffReason.QUOTE_REFUSED
    assert "mais de 20 anos" in reply.text and reply.price is None


def test_quote_message_shows_carencia_and_pro_rata_from_api(make_agent):
    raw = {
        "franquia": 3000, "coberturas": ["colisao", "carro_reserva"],
        "carencia": {"coberturas": ["roubo", "furto"], "dias": 30},
        "primeiro_pagamento_pro_rata": {
            "dias_no_mes": 31, "dias_cobrados": 17, "valor_primeiro_pagamento": 115.11,
        },
    }  # fmt: skip
    agent, _ = make_agent(FakeQuotes([Quote("r", 209.9, raw)]))
    text = agent.handle("c1", FULL).text
    assert "R$ 209,90 por mês" in text and "carro reserva" in text
    assert "roubo e furto só valem após 30 dias" in text
    assert "R$ 115,11" in text and "17 de 31" in text


def test_quote_message_survives_unexpected_detail_shape(make_agent):
    agent, _ = make_agent(FakeQuotes([Quote("r", 100.0, {"carencia": {"coberturas": ["x"]}})]))
    assert "R$ 100,00" in agent.handle("c1", FULL).text


def test_past_start_date_is_not_quoted_and_lead_is_asked_again(make_agent):
    agent, quotes = make_agent()
    reply = agent.handle("c1", FULL.replace("15/07/2026", "15/06/2026"))
    assert reply.stage is Stage.COLLECTING and "passado" in reply.text
    assert quotes.calls == []
    assert agent.handle("c1", "20/07/2026").stage is Stage.QUOTED
    assert str(quotes.calls[-1].data_inicio) == "2026-07-20"


def test_future_vehicle_year_asks_to_confirm_instead_of_quoting(make_agent):
    agent, quotes = make_agent()
    reply = agent.handle("c1", FULL.replace("2022", "2031"))
    assert reply.stage is Stage.COLLECTING and "futuro" in reply.text and quotes.calls == []
    assert agent.handle("c1", "2021").stage is Stage.QUOTED
    assert quotes.calls[-1].veiculo_ano == 2021


def test_invalid_value_after_quote_keeps_previous_quote(make_agent):
    agent, quotes = make_agent()
    agent.handle("c1", FULL)
    reply = agent.handle("c1", "e se começar em 01/01/2020?")
    assert "passado" in reply.text and len(quotes.calls) == 1
    assert str(quotes.calls[-1].data_inicio) == "2026-07-15"


def test_next_year_model_is_sent_to_the_api(make_agent):
    agent, quotes = make_agent()
    assert agent.handle("c1", FULL.replace("2022", "2027")).stage is Stage.QUOTED
    assert quotes.calls[-1].veiculo_ano == 2027


def test_many_thanks_after_quote_never_hand_off(make_agent):
    agent, _ = make_agent()
    agent.handle("c1", FULL)
    for _ in range(5):
        assert agent.handle("c1", "obrigado").stage is Stage.QUOTED
