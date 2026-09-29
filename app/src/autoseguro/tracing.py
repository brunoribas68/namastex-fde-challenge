"""Trace estruturado em JSON Lines, com mascaramento de dados pessoais (LGPD)."""

from __future__ import annotations

import json
import re
import sys
import threading
from datetime import UTC, datetime
from typing import Any, TextIO

_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"\b[A-Za-z]{3}-?\d[A-Za-z0-9]\d{2}\b"), "[PLACA]"),
)
_CEP = (re.compile(r"\b\d{5}-?\d{3}\b"), "[CEP]")
_PHONE = (re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"), "[TELEFONE]")


def redact_text(text: str, *, mask_cep: bool = True) -> str:
    """Remove e-mail, CPF, placa, telefone e (opcional) CEP de um texto livre."""
    patterns = _PATTERNS + ((_CEP,) if mask_cep else ()) + (_PHONE,)
    for regex, label in patterns:
        text = regex.sub(label, text)
    return text


def _clean(value: Any, key: str = "") -> Any:
    if key == "cep" and isinstance(value, str):
        return value[:5] + "-***"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _clean(v, k) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


class Tracer:
    """Um evento por linha: ts, event, conversation_id, message_id + dados já mascarados."""

    def __init__(self, sink: TextIO | None = None) -> None:
        self._sink = sink or sys.stdout
        self._lock = threading.Lock()

    def emit(
        self, event: str, conversation_id: str, message_id: str | None = None, **data: Any
    ) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": event,
            "conversation_id": conversation_id,
            "message_id": message_id,
            **_clean(data),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._sink.write(line + "\n")
            self._sink.flush()
