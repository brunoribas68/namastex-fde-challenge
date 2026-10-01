"""Monta o agente a partir das Settings (usado pela API HTTP e pelo CLI)."""

from __future__ import annotations

import sys
from pathlib import Path

from .agent import Agent
from .config import Settings
from .extractor import Extractor, LLMExtractor, RegexExtractor
from .quote_client import QuoteClient
from .store import InMemoryStore
from .tracing import Tracer


def build_agent(settings: Settings) -> Agent:
    if settings.trace_file == "-":
        sink = sys.stdout
    else:
        path = Path(settings.trace_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        sink = path.open("a", encoding="utf-8")
    extractor: Extractor = (
        LLMExtractor(settings.anthropic_api_key, settings.llm_model)
        if settings.anthropic_api_key
        else RegexExtractor()
    )
    quotes = QuoteClient(
        settings.quote_api_url,
        timeout=settings.quote_timeout_s,
        max_attempts=settings.quote_max_attempts,
        backoff=settings.quote_backoff_s,
        deadline=settings.quote_deadline_s,
        plans_ttl=settings.plans_cache_ttl_s,
    )
    return Agent(extractor, quotes, InMemoryStore(settings.conversation_ttl_s), Tracer(sink))
