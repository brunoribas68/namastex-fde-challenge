"""Smoke contra a quote-service REAL: `QUOTE_API_URL=... pytest -m integration`."""

import os
import uuid
from datetime import date, timedelta

import pytest

from autoseguro.agent import Agent
from autoseguro.extractor import RegexExtractor
from autoseguro.models import Stage
from autoseguro.quote_client import QuoteClient
from autoseguro.store import InMemoryStore
from autoseguro.tracing import Tracer

pytestmark = pytest.mark.integration


@pytest.fixture
def agent(tmp_path):
    url = os.environ.get("QUOTE_API_URL", "http://localhost:8000")
    sink = (tmp_path / "trace.jsonl").open("w")
    return Agent(RegexExtractor(), QuoteClient(url), InMemoryStore(), Tracer(sink))


@pytest.mark.parametrize("run", range(5))  # a API é instável: repete para exercitar retries
def test_end_to_end_never_crashes_and_never_invents_price(agent, run):
    plans = agent.quotes.list_plans()
    assert plans, "GET /planos não retornou planos; ajuste parse_plans"
    start = (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")
    reply = agent.handle(
        f"it-{uuid.uuid4().hex[:6]}",
        f"Tenho 35 anos, carro 2022, CEP 01310-100, início {start}, plano {plans[0].id}",
    )
    assert reply.stage in (Stage.QUOTED, Stage.HANDED_OFF, Stage.COLLECTING)
    assert (reply.price is not None) == (reply.stage is Stage.QUOTED)
