from autoseguro.models import HandoffReason, Stage
from autoseguro.quote_client import QuoteRejected, QuoteUnavailable

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
    reply = agent.handle("c1", "e no plano básico?")
    assert reply.stage is Stage.QUOTED and len(quotes.calls) == 2
    assert quotes.calls[-1].plano_id == "basico"


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
