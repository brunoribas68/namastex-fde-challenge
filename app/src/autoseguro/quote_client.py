"""Cliente resiliente da API de cotação (sistema legado instável).

Estratégia: timeout curto por tentativa, retry com backoff exponencial + jitter dentro de um
orçamento total de tempo, circuit breaker e, no fim, uma exceção explícita. Nunca devolve um
preço que a API não retornou.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from .models import SLOT_ORDER, Plan, Slots

# Nomes de campo aceitos para o preço na resposta. Ajuste aqui após ver o payload real.
PRICE_KEYS = ("preco", "premio", "valor", "preco_total", "premio_total", "total")


class QuoteUnavailable(Exception):
    """/quote não entregou um preço válido (retries esgotados, circuito aberto, config errada)."""

    def __init__(self, reason: str, attempts: int) -> None:
        super().__init__(f"{reason} (tentativas={attempts})")
        self.reason = reason
        self.attempts = attempts


class QuoteRejected(Exception):
    """A API respondeu 4xx de validação: os dados enviados não servem. Não adianta repetir."""

    def __init__(self, detail: str, fields: list[str]) -> None:
        super().__init__(detail)
        self.detail = detail
        self.fields = fields


@dataclass(frozen=True)
class Quote:
    request_id: str
    price: float
    raw: dict


def parse_quote(data: object, request_id: str) -> Quote:
    if isinstance(data, dict):
        for key in PRICE_KEYS:
            value = data.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
                return Quote(request_id, float(value), data)
    raise ValueError("resposta sem preço válido")


def parse_plans(data: object) -> list[Plan]:
    """Aceita lista de planos, {"planos": [...]} ou {id: {...}}."""
    if isinstance(data, dict):
        data = data.get("planos") or data.get("plans") or data
    if isinstance(data, dict):
        data = [{"id": k, **v} for k, v in data.items() if isinstance(v, dict)]
    plans = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        plan_id = item.get("id") or item.get("plano_id")
        if plan_id:
            plans.append(Plan(str(plan_id), str(item.get("nome") or plan_id)))
    return plans


def parse_rejection(resp: httpx.Response) -> QuoteRejected:
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        detail = resp.text
    if isinstance(detail, list):  # formato de validação do FastAPI
        message = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
        blob = " ".join(str(d.get("loc", "")) if isinstance(d, dict) else "" for d in detail)
    else:
        message = blob = str(detail)
    fields = [s for s in SLOT_ORDER if s in blob or s in message]
    return QuoteRejected(message[:200], fields)


class CircuitBreaker:
    """Abre após N falhas seguidas e volta a tentar depois do cooldown."""

    def __init__(
        self,
        threshold: int = 5,
        cooldown: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold, self.cooldown, self._clock = threshold, cooldown, clock
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if self._clock() - self._opened_at >= self.cooldown:
            self._opened_at = None  # half-open: deixa uma tentativa passar
            self._failures = self.threshold - 1
            return True
        return False

    def success(self) -> None:
        self._failures, self._opened_at = 0, None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._opened_at = self._clock()


class QuoteClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        max_attempts: int = 4,
        backoff: float = 0.4,
        deadline: float = 12.0,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: Callable[[], float] = random.random,
        plans_ttl: float = 300.0,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=timeout)
        self.max_attempts, self.backoff, self.deadline = max_attempts, backoff, deadline
        self._breaker = breaker or CircuitBreaker()
        self._sleep, self._clock, self._rng = sleep, clock, rng
        self._plans: list[Plan] = []
        self._plans_at: float | None = None
        self._plans_ttl = plans_ttl

    def list_plans(self) -> list[Plan]:
        """Planos vigentes (cache com TTL; em falha, devolve o último cache ou lista vazia)."""
        fresh = self._plans_at is not None and self._clock() - self._plans_at < self._plans_ttl
        if fresh:
            return self._plans
        try:
            resp = self._http.get("/planos")
            resp.raise_for_status()
            plans = parse_plans(resp.json())
        except (httpx.HTTPError, ValueError):
            return self._plans
        if plans:
            self._plans, self._plans_at = plans, self._clock()
        return self._plans

    def quote(
        self,
        slots: Slots,
        request_id: str,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> Quote:
        """Cota ou levanta QuoteRejected (dados inválidos) / QuoteUnavailable (infra)."""
        report = on_attempt or (lambda _: None)
        if not self._breaker.allow():
            report({"attempt": 0, "outcome": "circuit_open"})
            raise QuoteUnavailable("circuit_open", 0)

        started, outcome, attempt = self._clock(), "unknown", 0
        while attempt < self.max_attempts:
            attempt += 1
            t0 = self._clock()
            status: int | None = None
            try:
                resp = self._http.post(
                    "/quote", json=slots.payload(), headers={"X-Request-ID": request_id}
                )
                status = resp.status_code
            except httpx.HTTPError as exc:
                outcome = type(exc).__name__
            else:
                if status == 200:
                    try:
                        quote = parse_quote(resp.json(), request_id)
                    except ValueError:
                        outcome = "malformed_response"
                    else:
                        self._breaker.success()
                        report(self._info(attempt, "ok", status, t0))
                        return quote
                elif status in (400, 422):
                    self._breaker.success()  # o serviço está de pé; o dado é que está ruim
                    report(self._info(attempt, "rejected", status, t0))
                    raise parse_rejection(resp)
                elif status == 429 or status >= 500:
                    outcome = f"http_{status}"
                else:  # 401/403/404...: erro de configuração, repetir não resolve
                    report(self._info(attempt, f"http_{status}", status, t0))
                    self._breaker.failure()
                    raise QuoteUnavailable(f"http_{status}", attempt)

            report(self._info(attempt, outcome, status, t0))
            if attempt >= self.max_attempts:
                break
            delay = self.backoff * 2 ** (attempt - 1) * (0.5 + self._rng())
            if self._clock() - started + delay > self.deadline:
                break
            self._sleep(delay)

        self._breaker.failure()
        raise QuoteUnavailable(outcome, attempt)

    def _info(self, attempt: int, outcome: str, status: int | None, t0: float) -> dict:
        return {
            "attempt": attempt,
            "outcome": outcome,
            "status": status,
            "latency_ms": round((self._clock() - t0) * 1000),
        }
