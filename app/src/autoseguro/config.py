"""Configuração via variáveis de ambiente (12-factor). Toda variável nova deve entrar no README."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    quote_api_url: str = "http://localhost:8000"
    quote_timeout_s: float = 3.0
    quote_max_attempts: int = 4
    quote_backoff_s: float = 0.4
    quote_deadline_s: float = 15.0
    conversation_ttl_s: float = 86_400.0  # conversa parada há mais que isso sai da memória
    plans_cache_ttl_s: float = 300.0  # quanto tempo um plano novo/removido leva para aparecer
    trace_file: str = "logs/trace.jsonl"  # "-" escreve no stdout
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5-5"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        kwargs = {attr: cast(env[name]) for name, (attr, cast) in _ENV.items() if env.get(name)}
        return cls(**kwargs)


_ENV = {
    "QUOTE_API_URL": ("quote_api_url", str),
    "QUOTE_TIMEOUT_S": ("quote_timeout_s", float),
    "QUOTE_MAX_ATTEMPTS": ("quote_max_attempts", int),
    "QUOTE_BACKOFF_S": ("quote_backoff_s", float),
    "QUOTE_DEADLINE_S": ("quote_deadline_s", float),
    "CONVERSATION_TTL_S": ("conversation_ttl_s", float),
    "PLANS_CACHE_TTL_S": ("plans_cache_ttl_s", float),
    "TRACE_FILE": ("trace_file", str),
    "ANTHROPIC_API_KEY": ("anthropic_api_key", str),
    "LLM_MODEL": ("llm_model", str),
}
ENV_VARS = tuple(_ENV)
