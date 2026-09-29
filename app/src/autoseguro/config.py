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
    quote_deadline_s: float = 12.0
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
    "TRACE_FILE": ("trace_file", str),
    "ANTHROPIC_API_KEY": ("anthropic_api_key", str),
    "LLM_MODEL": ("llm_model", str),
}
ENV_VARS = tuple(_ENV)
