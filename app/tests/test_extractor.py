import json
from datetime import date

import httpx
import pytest
import respx

from autoseguro.extractor import LLMExtractor, RegexExtractor
from autoseguro.models import HandoffReason

from .conftest import PLANS, TODAY

ex = RegexExtractor()


def run(text, asked=None):
    return ex.extract(text, PLANS, TODAY, asked)


def test_extracts_all_fields_from_one_message():
    out = run("Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026, plano completo")
    assert out.slots == {
        "idade": 35, "veiculo_ano": 2022, "cep": "01310-100",
        "data_inicio": date(2026, 7, 15), "plano_id": "completo",
    }  # fmt: skip


def test_iso_date_and_cep_without_dash():
    out = run("cep 01310100 início 2026-08-01")
    assert out.slots["cep"] == "01310-100"
    assert out.slots["data_inicio"] == date(2026, 8, 1)
    assert "veiculo_ano" not in out.slots  # o ano da data não vira ano do veículo


def test_relative_dates():
    assert run("pode ser amanhã").slots["data_inicio"] == date(2026, 7, 2)
    assert run("depois de amanhã").slots["data_inicio"] == date(2026, 7, 3)


def test_invalid_date_is_ignored():
    assert "data_inicio" not in run("31/02/2026").slots


def test_vehicle_age_is_not_lead_age():
    assert "idade" not in run("meu carro tem 20 anos").slots


def test_bare_number_uses_last_question():
    assert run("35", asked="idade").slots == {"idade": 35}
    assert run("2019", asked="veiculo_ano").slots == {"veiculo_ano": 2019}
    assert run("35", asked=None).slots == {}


def test_ambiguous_plan_is_not_chosen():
    assert "plano_id" not in run("qual a diferença entre básico e completo?").slots


@pytest.mark.parametrize(
    ("text", "human", "topic"),
    [
        ("quero falar com um atendente", True, None),
        ("preciso acionar o seguro, tive um sinistro", False, HandoffReason.OUT_OF_SCOPE),
        ("vou no Procon, isso é um absurdo", False, HandoffReason.COMPLAINT),
        ("quero cotar", False, None),
    ],
)
def test_intents(text, human, topic):
    out = run(text)
    assert (out.wants_human, out.topic) == (human, topic)


# --- LLMExtractor -----------------------------------------------------------------------------

URL = LLMExtractor.URL


@respx.mock
def test_llm_extractor_parses_and_validates():
    payload = {"idade": 40, "plano_id": "completo", "cep": None, "wants_human": False}
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"content": [{"text": json.dumps(payload)}]})
    )
    out = LLMExtractor("k", "m").extract("tenho 40, quero completo", PLANS, TODAY)
    assert out.slots == {"idade": 40, "plano_id": "completo"}


@respx.mock
def test_llm_extractor_drops_unknown_plan():
    payload = {"plano_id": "inventado"}
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"content": [{"text": json.dumps(payload)}]})
    )
    assert LLMExtractor("k", "m").extract("x", PLANS, TODAY).slots == {}


@respx.mock
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, json={"content": [{"text": "não é json"}]})],
)
def test_llm_extractor_falls_back_to_regex(response):
    respx.post(URL).mock(return_value=response)
    out = LLMExtractor("k", "m").extract("tenho 33 anos", PLANS, TODAY)
    assert out.slots == {"idade": 33}


@respx.mock
def test_llm_extractor_does_not_send_pii():
    route = respx.post(URL).mock(return_value=httpx.Response(500))
    LLMExtractor("k", "m").extract("meu cpf 123.456.789-09 e email a@b.com", PLANS, TODAY)
    body = route.calls[0].request.content.decode()
    assert "123.456.789-09" not in body
    assert "a@b.com" not in body
