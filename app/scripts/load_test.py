"""Teste de carga do agente: N conversas, C em paralelo, uma mensagem cada.

    uv run python scripts/load_test.py 300 50          # mensagem completa: cota
    uv run python scripts/load_test.py 10000 50 oi     # só coleta (sem /quote)

Imprime vazão, latência (p50/p95/máx) e o desfecho de cada conversa. Ver docs/ARQUITETURA.md.
"""

from __future__ import annotations

import argparse
import collections
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

TEXTS = {
    "full": "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027, plano completo",
    "oi": "oi",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("n", type=int, help="número de conversas")
    parser.add_argument("concurrency", type=int, help="requisições em paralelo")
    parser.add_argument("kind", nargs="?", default="full", choices=TEXTS)
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.url, timeout=60, limits=httpx.Limits(max_connections=args.concurrency)
    )

    def one(_: int) -> tuple[float, str]:
        started = time.perf_counter()
        try:
            body = {"conversation_id": f"load-{uuid.uuid4().hex}", "text": TEXTS[args.kind]}
            resp = client.post("/messages", json=body)
            data = resp.json() if resp.status_code == 200 else {}
            outcome = data.get("handoff_reason") or data.get("stage") or f"http_{resp.status_code}"
        except httpx.HTTPError as exc:
            outcome = type(exc).__name__
        return time.perf_counter() - started, outcome

    started = time.perf_counter()
    with ThreadPoolExecutor(args.concurrency) as pool:
        results = list(pool.map(one, range(args.n)))
    wall = time.perf_counter() - started

    latencies = sorted(r[0] for r in results)

    def pct(p: float) -> float:
        return latencies[min(len(latencies) - 1, int(p * len(latencies)))]

    outcomes = dict(collections.Counter(r[1] for r in results))
    print(
        f"{args.n} conversas, {args.concurrency} em paralelo ({args.kind}): "
        f"{args.n / wall:.1f} msg/s | p50 {pct(0.5):.2f}s p95 {pct(0.95):.2f}s "
        f"máx {latencies[-1]:.2f}s | {outcomes}"
    )


if __name__ == "__main__":
    main()
