# Dois alvos:
#   test    -> dependências de dev + testes; roda lint e pytest (`docker compose run --rm tests`)
#   runtime -> imagem de produção enxuta (padrão; usada pelo serviço `agent` do compose)
# Tudo roda como o usuário não-root `app`, dono do /app e do .venv (sem "Permission denied").

FROM python:3.12-slim AS base
RUN pip install --no-cache-dir uv && useradd --create-home app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_FROZEN=1 \
    PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
RUN chown app:app /app
USER app
COPY --chown=app:app pyproject.toml uv.lock ./

FROM base AS test
RUN uv sync --no-install-project
COPY --chown=app:app . .
RUN uv sync
ENV QUOTE_API_URL=http://quote-api:8000
CMD ["sh", "-c", "ruff check . && ruff format --check . && pytest --cov --cov-fail-under=85"]

FROM base AS runtime
RUN uv sync --no-dev --no-install-project
COPY --chown=app:app src ./src
RUN uv sync --no-dev
# Imagem de produção não tem testes nem deps de dev: `uv run` não tenta instalar nada aqui.
ENV UV_NO_SYNC=1 TRACE_FILE=-
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8080/health', timeout=2)"
CMD ["uvicorn", "autoseguro.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
