"""Armazenamento de conversas. Em memória por padrão; troque por Redis/DB para várias réplicas."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from .models import Conversation


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, Conversation] = {}
        self._locks: defaultdict[str, threading.RLock] = defaultdict(threading.RLock)
        self._guard = threading.Lock()

    def get(self, conversation_id: str) -> Conversation:
        with self._guard:
            return self._data.setdefault(conversation_id, Conversation(conversation_id))

    @contextmanager
    def lock(self, conversation_id: str) -> Iterator[None]:
        """Serializa mensagens da mesma conversa (webhooks do WhatsApp podem chegar em paralelo)."""
        with self._guard:
            lock = self._locks[conversation_id]
        with lock:
            yield
