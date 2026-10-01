"""E se o negócio mudar? Um teste por mudança provável na quote-service, sem mexer no agente.

Os planos, preços e regras são da API (`GET /planos` e `POST /quote`). Estes testes simulam a API
mudando e conferem o que o agente faz: o que se adapta sozinho, o que degrada com segurança
(handoff sem preço) e o que exige código. Ver docs/EVOLUCAO.md.
"""

import io

import httpx
import pytest

from autoseguro.agent import Agent
from autoseguro.extractor import RegexExtractor
from autoseguro.quote_client import QuoteClient
from autoseguro.store import InMemoryStore
from autoseguro.tracing import Tracer

from .conftest import TODAY

BASE = "http://quote.test"
DATA = "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026"

pytestmark = pytest.mark.respx(base_url=BASE, assert_all_called=False)


def catalog(*plans):
    """Resposta do GET /planos com (id, nome)."""
    return httpx.Response(200, json={"planos": [{"id": i, "nome": n} for i, n in plans]})


def priced(plano_id, price=150.0, **extra):
    return httpx.Response(200, json={"plano_id": plano_id, "premio_mensal": price, **extra})


ATUAL = catalog(("essencial", "Essencial"), ("completo", "Completo"), ("premium", "Premium"))


@pytest.fixture
def clock():
    return [0.0]


@pytest.fixture
def agent(clock):
    quotes = QuoteClient(
        BASE, max_attempts=2, sleep=lambda _: None, clock=lambda: clock[0], plans_ttl=300
    )
    return Agent(RegexExtractor(), quotes, InMemoryStore(), Tracer(io.StringIO()),
                 today=lambda: TODAY)  # fmt: skip


# Muda sozinho, sem deploy -----------------------------------------------------------------------


def test_new_plan_is_offered_and_quoted_after_cache_expires(agent, respx_mock, clock):
    planos = respx_mock.get("/planos").mock(return_value=ATUAL)
    assert "Ouro" not in agent.handle("a", "oi").text
    planos.mock(return_value=catalog(("essencial", "Essencial"), ("ouro", "Ouro")))
    clock[0] = 301  # passou o PLANS_CACHE_TTL_S
    assert "Ouro" in agent.handle("b", "oi").text
    respx_mock.post("/quote").mock(return_value=priced("ouro", 512.3))
    assert agent.handle("b", DATA + ", plano ouro").price == 512.3


def test_new_price_or_rule_needs_no_code(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    respx_mock.post("/quote").mock(return_value=priced("completo", 9999.99))
    reply = agent.handle("a", DATA + ", plano completo")
    assert reply.price == 9999.99 and "R$ 9.999,99" in reply.text  # preço só vem da API


def test_new_refusal_rule_is_explained_with_the_api_reason(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    motivo = "CEP fora da area de atendimento."
    respx_mock.post("/quote").mock(
        return_value=httpx.Response(422, json={"error": "cotacao_recusada", "motivo": motivo})
    )
    reply = agent.handle("a", DATA + ", plano completo")
    assert reply.handoff_reason == "quote_refused" and motivo in reply.text


def test_plan_name_containing_another_is_not_ambiguous(agent, respx_mock):
    respx_mock.get("/planos").mock(
        return_value=catalog(("completo", "Completo"), ("completo_plus", "Completo Plus"))
    )
    respx_mock.post("/quote").mock(return_value=priced("completo_plus"))
    assert agent.handle("a", DATA + ", quero o completo plus").stage == "quoted"


def test_plan_id_with_underscore_matches_spoken_form(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=catalog(("top_plus", "Top+")))
    respx_mock.post("/quote").mock(return_value=priced("top_plus"))
    assert agent.handle("a", DATA + ", plano top plus").stage == "quoted"


def test_new_field_in_quote_response_does_not_break_the_reply(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    respx_mock.post("/quote").mock(
        return_value=priced("completo", 200.0, desconto={"pct": 10}, franquia="nao numerica")
    )
    reply = agent.handle("a", DATA + ", plano completo")
    assert reply.price == 200.0 and "R$ 200,00" in reply.text


# Plano removido: pergunta de novo em vez de perder o lead -------------------------------------


def test_plan_removed_while_cached_asks_for_another_plan(agent, respx_mock):
    planos = respx_mock.get("/planos").mock(return_value=ATUAL)
    agent.handle("a", "oi")  # catálogo antigo fica em cache
    planos.mock(return_value=catalog(("essencial", "Essencial"), ("completo", "Completo")))
    respx_mock.post("/quote").mock(
        side_effect=[
            httpx.Response(422, json={"error": "cotacao_recusada",
                                      "motivo": "Plano 'premium' inexistente."}),
            priced("completo"),
        ]
    )  # fmt: skip
    reply = agent.handle("a", DATA + ", plano premium")
    assert reply.stage == "collecting" and "premium não está mais disponível" in reply.text
    assert "Premium" not in reply.text and "Completo" in reply.text
    assert agent.handle("a", "completo").stage == "quoted"


def test_plan_removed_between_turns_is_asked_again(agent, respx_mock, clock):
    planos = respx_mock.get("/planos").mock(return_value=ATUAL)
    agent.handle("a", "Quero o premium")
    planos.mock(return_value=catalog(("essencial", "Essencial")))
    clock[0] = 301
    reply = agent.handle("a", DATA)
    assert reply.stage == "collecting" and "premium não está mais disponível" in reply.text


def test_refusal_with_plan_still_listed_still_hands_off(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    respx_mock.post("/quote").mock(
        return_value=httpx.Response(422, json={"error": "cotacao_recusada", "motivo": "x"})
    )
    assert agent.handle("a", DATA + ", plano premium").handoff_reason == "quote_refused"


# Muda o contrato: degrada com segurança (nunca inventa preço) e precisa de código -------------


def test_new_required_field_hands_off_without_price(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    respx_mock.post("/quote").mock(
        return_value=httpx.Response(
            422, json={"detail": [{"loc": ["body", "uso_veiculo"], "msg": "Field required"}]}
        )
    )
    reply = agent.handle("a", DATA + ", plano completo")
    assert reply.handoff_reason == "quote_rejected" and reply.price is None


def test_renamed_price_field_hands_off_without_price(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=ATUAL)
    respx_mock.post("/quote").mock(
        return_value=httpx.Response(200, json={"plano_id": "completo", "valor_mensal": 210.0})
    )
    reply = agent.handle("a", DATA + ", plano completo")
    assert reply.handoff_reason == "quote_unavailable" and "R$" not in reply.text


def test_planos_endpoint_down_keeps_last_known_catalog(agent, respx_mock, clock):
    planos = respx_mock.get("/planos").mock(return_value=ATUAL)
    agent.handle("a", "oi")
    planos.mock(return_value=httpx.Response(503))
    clock[0] = 301
    assert "Premium" in agent.handle("b", "oi").text


def test_plan_name_with_accent_matches_with_or_without_it(agent, respx_mock):
    respx_mock.get("/planos").mock(return_value=catalog(("basico", "Básico")))
    respx_mock.post("/quote").mock(return_value=priced("basico"))
    assert agent.handle("a", DATA + ", plano Básico").stage == "quoted"
