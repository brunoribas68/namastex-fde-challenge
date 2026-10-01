import threading
import time
from concurrent.futures import ThreadPoolExecutor

from autoseguro.models import Stage
from autoseguro.store import InMemoryStore

from .conftest import FakeQuotes

FULL = "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/07/2026, plano completo"


def test_idle_conversations_are_evicted_so_memory_is_bounded():
    now = [0.0]
    store = InMemoryStore(ttl=100, clock=lambda: now[0])
    for i in range(1000):
        store.get(f"c{i}").turns = 1
    now[0] = 50
    store.get("recente")
    now[0] = 120  # c0..c999 parados há 120 s; "recente" há 70 s
    store.get("nova")
    assert len(store) == 2
    assert store.get("c0").turns == 0  # quem volta depois de expirar recomeça


def test_activity_keeps_a_conversation_alive():
    now = [0.0]
    store = InMemoryStore(ttl=100, clock=lambda: now[0])
    store.get("c1").turns = 3
    for t in (90, 180, 270):
        now[0] = t
        assert store.get("c1").turns == 3


def test_conversation_being_processed_is_never_evicted():
    now = [0.0]
    store = InMemoryStore(ttl=100, clock=lambda: now[0])
    with store.lock("c1"):
        store.get("c1").turns = 7
        now[0] = 500
        store.get("outra")  # dispara a limpeza enquanto c1 está em uso
        assert store.get("c1").turns == 7


def test_same_conversation_is_serialized_and_different_ones_run_in_parallel():
    store = InMemoryStore()
    both_inside = threading.Barrier(2, timeout=2)  # só passa se "a" e "b" estiverem dentro juntos
    active, peak, guard = {"a": 0, "b": 0}, {"a": 0, "b": 0}, threading.Lock()

    def work(cid, first):
        with store.lock(cid):
            with guard:
                active[cid] += 1
                peak[cid] = max(peak[cid], active[cid])
            if first:
                both_inside.wait()
            time.sleep(0.005)
            with guard:
                active[cid] -= 1

    jobs = [("a", True), ("b", True)] + [("a", False), ("b", False)] * 5
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(lambda j: work(*j), jobs))
    assert peak == {"a": 1, "b": 1}


def test_concurrent_webhook_retries_quote_only_once(make_agent):
    agent, quotes = make_agent()
    with ThreadPoolExecutor(20) as ex:
        replies = list(ex.map(lambda _: agent.handle("c1", FULL, "m1"), range(20)))
    assert len(quotes.calls) == 1 and len({r.quote_id for r in replies}) == 1


def test_many_leads_in_parallel_are_isolated(make_agent):
    agent, quotes = make_agent(FakeQuotes())
    with ThreadPoolExecutor(32) as ex:
        replies = list(ex.map(lambda i: agent.handle(f"lead-{i}", FULL), range(200)))
    assert all(r.stage is Stage.QUOTED for r in replies) and len(quotes.calls) == 200
