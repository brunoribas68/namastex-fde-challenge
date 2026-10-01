"""Armazenamento de conversas. Em memória por padrão; troque por Redis/DB para várias réplicas."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from .models import Conversation


class Store(Protocol):
    """O que o agente precisa do armazenamento. Um RedisStore implementa os mesmos três métodos:
    `lock` vira um lock distribuído por conversa e `save` grava a conversa serializada."""

    def lock(self, conversation_id: str) -> AbstractContextManager[None]: ...
    def get(self, conversation_id: str) -> Conversation: ...
    def save(self, conversation: Conversation) -> None: ...


@dataclass
class _Entry:
    conversation: Conversation
    seen: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class InMemoryStore:
    """Conversas no processo, com expiração por inatividade (`ttl`) para a memória não crescer sem
    limite. Uma conversa expirada recomeça do zero na próxima mensagem do lead."""

    def __init__(self, ttl: float = 86_400.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self._clock = ttl, clock
        self._data: OrderedDict[str, _Entry] = OrderedDict()  # do menos para o mais recente
        self._guard = threading.Lock()

    def __len__(self) -> int:
        return len(self._data)

    def get(self, conversation_id: str) -> Conversation:
        with self._guard:
            return self._touch(conversation_id).conversation

    def save(self, conversation: Conversation) -> None:
        """Nada a fazer: o objeto já está na memória (num store remoto, grava aqui)."""

    @contextmanager
    def lock(self, conversation_id: str) -> Iterator[None]:
        """Serializa mensagens da mesma conversa (webhooks do WhatsApp podem chegar em paralelo)."""
        with self._guard:
            lock = self._touch(conversation_id).lock
        with lock:
            yield

    def _touch(self, conversation_id: str) -> _Entry:
        now = self._clock()
        self._evict(now)
        entry = self._data.pop(conversation_id, None) or _Entry(Conversation(conversation_id), now)
        entry.seen = now
        self._data[conversation_id] = entry
        return entry

    def _evict(self, now: float) -> None:
        """Remove as conversas paradas há mais de `ttl`, sempre a partir da mais antiga (O(1)
        amortizado). Conversa com mensagem em processamento (lock tomado) nunca é removida."""
        while self._data:
            conversation_id, entry = next(iter(self._data.items()))
            if now - entry.seen < self.ttl:
                return
            if entry.lock.acquire(blocking=False):
                entry.lock.release()
                del self._data[conversation_id]
            else:
                entry.seen = now
                self._data.move_to_end(conversation_id)
