"""Aceitação: um teste por critério de avaliação do desafio ("Como a gente vai olhar").

Diferente de test_agent.py, aqui o cliente de cotação é o QuoteClient REAL (retry, deadline,
breaker) falando HTTP com uma /quote simulada no formato da quote-service, e a conversa entra pela
API HTTP (POST /messages), como o canal do WhatsApp faria.
"""

import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from autoseguro.agent import Agent
from autoseguro.api import create_app
from autoseguro.extractor import RegexExtractor
from autoseguro.quote_client import CircuitBreaker, QuoteClient
from autoseguro.store import InMemoryStore
from autoseguro.tracing import Tracer

from .conftest import TODAY

BASE = "http://quote.test"
FULL = "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026, plano completo"
PLANOS = {"moeda": "BRL", "planos": [
    {"id": "essencial", "nome": "Essencial"}, {"id": "completo", "nome": "Completo"},
    {"id": "premium", "nome": "Premium"},
]}  # fmt: skip
QUOTE_OK = {
    "plano_id": "completo", "plano_nome": "Completo", "premio_mensal": 271.37, "franquia": 3000,
    "coberturas": ["colisao", "roubo"], "carencia": {"coberturas": ["roubo"], "dias": 30},
    "primeiro_pagamento_pro_rata": {
        "dias_no_mes": 31, "dias_cobrados": 17, "valor_primeiro_pagamento": 148.82,
    },
}  # fmt: skip
UNAVAILABLE = httpx.Response(503, json={"error": "upstream_unavailable"})

pytestmark = pytest.mark.respx(base_url=BASE, assert_all_called=False)


@pytest.fixture
def trace():
    return io.StringIO()


@pytest.fixture
def chat(respx_mock, trace):
    """Devolve send(conversation_id, text, message_id=None) -> dict e o breaker usado."""
    respx_mock.get("/planos").mock(return_value=httpx.Response(200, json=PLANOS))
    breaker = CircuitBreaker(threshold=3, cooldown=60)
    quotes = QuoteClient(BASE, max_attempts=4, backoff=0.01, sleep=lambda _: None, breaker=breaker)
    agent = Agent(RegexExtractor(), quotes, InMemoryStore(), Tracer(trace), today=lambda: TODAY)
    client = TestClient(create_app(agent))

    def send(conversation_id, text, message_id=None):
        body = {"conversation_id": conversation_id, "text": text, "message_id": message_id}
        resp = client.post("/messages", json=body)
        assert resp.status_code == 200
        return resp.json()

    send.breaker = breaker
    return send


def events(trace, kind=None):
    rows = [json.loads(line) for line in trace.getvalue().splitlines()]
    return [r for r in rows if kind is None or r["event"] == kind]


# Funciona de ponta a ponta? ------------------------------------------------------------------


def test_end_to_end_multi_turn_quotes_with_the_price_from_the_api(chat, respx_mock):
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(200, json=QUOTE_OK))
    assert chat("lead", "Oi, quero cotar o seguro do meu carro")["stage"] == "collecting"
    assert chat("lead", "Tenho 35 anos, o carro é 2022 e meu CEP é 01310-100")["stage"] == (
        "collecting"
    )
    reply = chat("lead", "Quero o plano completo, começando em 15/07/2026")
    assert reply["stage"] == "quoted" and reply["price"] == 271.37
    assert "R$ 271,37 por mês" in reply["text"] and "R$ 148,82" in reply["text"]
    sent = json.loads(route.calls[0].request.content)
    assert sent == {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022,
                    "cep": "01310-100", "data_inicio": "2026-07-15"}  # fmt: skip


# O que ele faz quando a /quote falha? ----------------------------------------------------------


def test_unstable_api_is_retried_until_it_answers(chat, respx_mock):
    route = respx_mock.post("/quote").mock(
        side_effect=[UNAVAILABLE, httpx.ReadTimeout("lenta"), httpx.Response(200, json=QUOTE_OK)]
    )
    reply = chat("lead", FULL)
    assert reply["stage"] == "quoted" and reply["price"] == 271.37
    assert route.call_count == 3


def test_api_down_hands_off_honestly_and_never_invents_price(chat, respx_mock, trace):
    respx_mock.post("/quote").mock(return_value=UNAVAILABLE)
    reply = chat("lead", FULL)
    assert reply["stage"] == "handed_off" and reply["handoff_reason"] == "quote_unavailable"
    assert reply["price"] is None and reply["quote_id"] is None and "R$" not in reply["text"]
    handoff = events(trace, "handoff")[0]
    assert handoff["collected"]["plano_id"] == "completo"  # humano recebe o que já foi coletado


def test_circuit_breaker_fails_fast_after_repeated_outages(chat, respx_mock):
    route = respx_mock.post("/quote").mock(return_value=UNAVAILABLE)
    for i in range(3):
        chat(f"lead-{i}", FULL)
    calls_before = route.call_count
    reply = chat("lead-next", FULL)
    assert reply["handoff_reason"] == "quote_unavailable" and reply["price"] is None
    assert route.call_count == calls_before  # circuito aberto: nem chamou a API


def test_malformed_200_is_never_shown_as_a_price(chat, respx_mock):
    respx_mock.post("/quote").mock(return_value=httpx.Response(200, json={"plano_id": "completo"}))
    reply = chat("lead", FULL)
    assert reply["handoff_reason"] == "quote_unavailable" and "R$" not in reply["text"]


def test_business_refusal_is_explained_and_goes_to_a_human(chat, respx_mock):
    motivo = "Idade acima do limite de aceitacao (75 anos)."
    route = respx_mock.post("/quote").mock(
        return_value=httpx.Response(422, json={"error": "cotacao_recusada", "motivo": motivo})
    )
    reply = chat("lead", FULL.replace("35", "80"))
    assert reply["handoff_reason"] == "quote_refused" and motivo in reply["text"]
    assert route.call_count == 1  # recusa de negócio não é repetida


def test_validation_error_asks_the_lead_to_fix_the_field(chat, respx_mock):
    invalid = {"detail": [{"loc": ["body", "idade"], "msg": "Input should be >= 0"}]}
    respx_mock.post("/quote").mock(
        side_effect=[httpx.Response(422, json=invalid), httpx.Response(200, json=QUOTE_OK)]
    )
    first = chat("lead", FULL)
    assert first["stage"] == "collecting" and "sua idade" in first["text"]
    assert chat("lead", "40")["stage"] == "quoted"


# O critério de passar pro humano é explícito? -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("quero falar com um atendente", "user_request"),
        ("isso é um absurdo, vou no Procon", "complaint"),
        ("bati o carro, preciso acionar o seguro", "out_of_scope"),
        ("quero a segunda via do boleto", "out_of_scope"),
    ],
)
def test_explicit_handoff_reasons(chat, text, reason):
    reply = chat("lead", text)
    assert (reply["stage"], reply["handoff_reason"]) == ("handed_off", reason)
    assert chat("lead", FULL)["stage"] == "handed_off"  # depois do handoff o bot não cota


# Dá pra rastrear o que aconteceu? --------------------------------------------------------------


def test_every_attempt_is_traced_and_linked_to_the_reply(chat, respx_mock, trace):
    route = respx_mock.post("/quote").mock(
        side_effect=[UNAVAILABLE, httpx.ReadTimeout("lenta"), httpx.Response(200, json=QUOTE_OK)]
    )
    reply = chat("lead", FULL, message_id="wamid-1")
    attempts = events(trace, "quote_attempt")
    assert [a["outcome"] for a in attempts] == ["http_503", "ReadTimeout", "ok"]
    request_ids = {a["request_id"] for a in attempts}
    assert request_ids == {reply["quote_id"]}
    assert {c.request.headers["X-Request-ID"] for c in route.calls} == request_ids
    for row in events(trace):
        assert row["conversation_id"] == "lead" and row["message_id"] == "wamid-1" and row["ts"]


def test_webhook_retry_with_same_message_id_does_not_quote_again(chat, respx_mock):
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(200, json=QUOTE_OK))
    first = chat("lead", FULL, message_id="wamid-1")
    again = chat("lead", FULL, message_id="wamid-1")
    assert first == again and route.call_count == 1


# Cuidado com dados sensíveis -----------------------------------------------------------------


def test_personal_data_never_reaches_the_trace(chat, respx_mock, trace):
    respx_mock.post("/quote").mock(return_value=UNAVAILABLE)
    chat("lead", "Meu CPF é 123.456.789-09, e-mail maria@exemplo.com, tel (11) 98888-7777")
    chat("lead", "placa ABC1D23. " + FULL)
    log = trace.getvalue()
    for secret in ("123.456.789-09", "maria@exemplo.com", "98888-7777", "ABC1D23", "01310-100"):
        assert secret not in log
    assert events(trace, "handoff")[0]["collected"]["cep"] == "01310-***"
