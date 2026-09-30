import io
from datetime import date

import pytest

from autoseguro.agent import Agent
from autoseguro.extractor import RegexExtractor
from autoseguro.models import Plan
from autoseguro.quote_client import Quote, QuoteRefused, QuoteRejected, QuoteUnavailable
from autoseguro.store import InMemoryStore
from autoseguro.tracing import Tracer

PLANS = [Plan("essencial", "Essencial"), Plan("completo", "Completo"), Plan("premium", "Premium")]
TODAY = date(2026, 7, 1)


class FakeQuotes:
    """Cotação controlada pelo teste: `outcomes` é consumido em ordem (Quote ou exceção)."""

    def __init__(self, outcomes=None, plans=PLANS):
        self.outcomes = list(outcomes or [])
        self.plans = plans
        self.calls = []

    def list_plans(self):
        return self.plans

    def quote(self, slots, request_id, on_attempt=None):
        self.calls.append(slots.model_copy())
        outcome = self.outcomes.pop(0) if self.outcomes else Quote(request_id, 1234.5, {})
        if isinstance(outcome, Exception):
            raise outcome
        return Quote(request_id, outcome.price, outcome.raw)


@pytest.fixture
def trace_buffer():
    return io.StringIO()


@pytest.fixture
def make_agent(trace_buffer):
    def _make(quotes=None, **kwargs):
        quotes = quotes or FakeQuotes()
        agent = Agent(
            RegexExtractor(), quotes, InMemoryStore(), Tracer(trace_buffer),
            today=lambda: TODAY, **kwargs,
        )  # fmt: skip
        return agent, quotes

    return _make


__all__ = ["FakeQuotes", "QuoteRefused", "QuoteRejected", "QuoteUnavailable", "PLANS", "TODAY"]
