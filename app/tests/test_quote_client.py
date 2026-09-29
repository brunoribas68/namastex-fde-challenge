import httpx
import pytest

from autoseguro.models import Slots
from autoseguro.quote_client import (
    CircuitBreaker,
    QuoteClient,
    QuoteRejected,
    QuoteUnavailable,
    parse_plans,
)

BASE = "http://quote.test"
SLOTS = Slots(plano_id="completo", idade=35, veiculo_ano=2022, cep="01310-100",
              data_inicio="2026-07-15")  # fmt: skip
OK = httpx.Response(200, json={"preco": 1500.0})

pytestmark = pytest.mark.respx(base_url=BASE)


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(sleeps):
    return QuoteClient(BASE, max_attempts=4, backoff=0.1, sleep=sleeps.append, rng=lambda: 0.5)


def test_success_first_try(respx_mock, client):
    respx_mock.post("/quote").mock(return_value=OK)
    assert client.quote(SLOTS, "req1").price == 1500.0


def test_sends_request_id_and_payload(respx_mock, client):
    route = respx_mock.post("/quote").mock(return_value=OK)
    client.quote(SLOTS, "req-abc")
    request = route.calls[0].request
    assert request.headers["x-request-id"] == "req-abc"
    assert b'"plano_id":"completo"' in request.content.replace(b" ", b"")


def test_retries_transient_failures_then_succeeds(respx_mock, client, sleeps):
    respx_mock.post("/quote").mock(
        side_effect=[httpx.Response(503), httpx.ConnectTimeout("t"), httpx.Response(429), OK]
    )
    attempts = []
    assert client.quote(SLOTS, "r", attempts.append).price == 1500.0
    assert [a["outcome"] for a in attempts] == ["http_503", "ConnectTimeout", "http_429", "ok"]
    assert sleeps == [0.1, 0.2, 0.4]  # backoff exponencial


def test_gives_up_after_max_attempts(respx_mock, client):
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(500))
    with pytest.raises(QuoteUnavailable) as exc:
        client.quote(SLOTS, "r")
    assert route.call_count == 4
    assert exc.value.attempts == 4


def test_malformed_body_is_retried_and_never_invents_price(respx_mock, client):
    respx_mock.post("/quote").mock(
        side_effect=[httpx.Response(200, json={"foo": 1}), httpx.Response(200, text="oops"), OK]
    )
    assert client.quote(SLOTS, "r").price == 1500.0


def test_validation_error_is_not_retried(respx_mock, client):
    detail = [{"loc": ["body", "veiculo_ano"], "msg": "ano inválido"}]
    route = respx_mock.post("/quote").mock(
        return_value=httpx.Response(422, json={"detail": detail})
    )
    with pytest.raises(QuoteRejected) as exc:
        client.quote(SLOTS, "r")
    assert route.call_count == 1
    assert exc.value.fields == ["veiculo_ano"]
    assert "ano inválido" in exc.value.detail


def test_config_error_fails_fast(respx_mock, client):
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(401))
    with pytest.raises(QuoteUnavailable):
        client.quote(SLOTS, "r")
    assert route.call_count == 1


def test_deadline_limits_total_time(respx_mock, sleeps):
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    client = QuoteClient(BASE, max_attempts=10, backoff=5, deadline=6, rng=lambda: 0.5,
                         clock=lambda: now[0], sleep=sleep)  # fmt: skip
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(503))
    with pytest.raises(QuoteUnavailable):
        client.quote(SLOTS, "r")
    assert route.call_count < 10


def test_circuit_breaker_opens_and_recovers(respx_mock, sleeps):
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown=30, clock=lambda: now[0])
    client = QuoteClient(BASE, max_attempts=1, sleep=sleeps.append, breaker=breaker,
                         clock=lambda: now[0])  # fmt: skip
    route = respx_mock.post("/quote").mock(return_value=httpx.Response(503))
    for _ in range(2):
        with pytest.raises(QuoteUnavailable):
            client.quote(SLOTS, "r")
    with pytest.raises(QuoteUnavailable, match="circuit_open"):
        client.quote(SLOTS, "r")
    assert route.call_count == 2  # aberto: nem chamou a API
    now[0] = 31
    route.mock(return_value=OK)
    assert client.quote(SLOTS, "r").price == 1500.0


def test_list_plans_caches_and_survives_failure(respx_mock, client):
    route = respx_mock.get("/planos").mock(
        return_value=httpx.Response(200, json={"planos": [{"id": "basico", "nome": "Básico"}]})
    )
    assert [p.id for p in client.list_plans()] == ["basico"]
    client.list_plans()
    assert route.call_count == 1
    client._plans_at = None  # força expirar o cache
    route.mock(return_value=httpx.Response(500))
    assert [p.id for p in client.list_plans()] == ["basico"]  # usa o último cache


@pytest.mark.parametrize(
    "data",
    [
        [{"id": "a"}],
        {"planos": [{"plano_id": "a"}]},
        {"a": {"nome": "A"}},
    ],
)
def test_parse_plans_shapes(data):
    assert [p.id for p in parse_plans(data)] == ["a"]
