# AutoSeguro Agent

Agente de WhatsApp que qualifica leads de seguro de veículo, **cota via `POST /quote`** e decide, com
critério explícito, entre resolver sozinho ou **passar para um humano**. Feito para o desafio
técnico FDE / AI Engineer da Namastex.

> Regra do projeto: **toda mudança de código atualiza a documentação** (README e `docs/`).
> Os testes em `tests/test_docs.py` e o checklist do PR reforçam isso.

## Como funciona

```
WhatsApp/canal ──POST /messages──▶ API (FastAPI)
                                     │
                                     ▼
                       Agent (máquina de estados)
        ┌───────────────┬───────────┴──────────┬────────────────┐
        ▼               ▼                      ▼                ▼
   Extractor        Policy               QuoteClient          Tracer
 (regex | LLM)   (quando escalar)   (retry, backoff,       (JSONL, sem PII)
                                    deadline, breaker)
                                         │
                                         ▼
                                  quote-service /quote
```

Fluxo: **coletando** (idade, ano do veículo, CEP, data de início, plano) → **cotando** →
**cotado** ou **encaminhado ao humano**. As respostas ao lead são *templates*: o preço só vem da
API, nunca de um LLM. Detalhes e justificativas em [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Rodando

### Docker (recomendado)

```bash
cp .env.example .env            # opcional: ANTHROPIC_API_KEY liga o extrator LLM
docker compose up --build       # quote-service em :8000, agente em :8080
curl localhost:8080/health
curl -X POST localhost:8080/messages -H 'content-type: application/json' -d '{
  "conversation_id": "lead-1",
  "text": "Tenho 35 anos, carro 2022, CEP 01310-100, começo em 15/12/2026, plano completo"
}'
```

Em servidor: mesmo comando com `-d`. O container roda como usuário não-root, tem `HEALTHCHECK`,
`restart: unless-stopped` e escreve o trace no stdout (`docker compose logs -f agent`).

### Local (sem Docker)

```bash
uv sync                                   # instala dependências
(cd quote-service && uv run uvicorn app.main:app --port 8000)   # API de cotação
uv run python -m autoseguro.cli           # conversa no terminal
uv run python -m autoseguro.cli --demo    # conversa roteirizada (gera o log de execução)
uv run uvicorn autoseguro.api:create_app --factory --port 8080
```

Sem a `quote-service` à mão, `uv run python scripts/fake_quote_server.py` sobe um stub instável
(**apenas desenvolvimento**).

## API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/messages` | Body `{conversation_id, text, message_id?}` → `Reply` (`text`, `stage`, `handoff_reason`, `quote_id`, `price`) |

`message_id` é a chave de idempotência: o WhatsApp reenvia webhooks, e reenvio com o mesmo id devolve
a mesma resposta **sem cotar de novo**.

## Configuração (variáveis de ambiente)

| Variável | Padrão | Uso |
|---|---|---|
| `QUOTE_API_URL` | `http://localhost:8000` | URL da API de cotação |
| `QUOTE_TIMEOUT_S` | `3.0` | Timeout por tentativa |
| `QUOTE_MAX_ATTEMPTS` | `4` | Máximo de tentativas por cotação |
| `QUOTE_BACKOFF_S` | `0.4` | Base do backoff exponencial (com jitter) |
| `QUOTE_DEADLINE_S` | `12.0` | Orçamento total de tempo por cotação |
| `TRACE_FILE` | `logs/trace.jsonl` | Arquivo do trace; `-` escreve no stdout (padrão no Docker) |
| `ANTHROPIC_API_KEY` | vazio | Se definida, usa LLM para extrair dados; senão, regex |
| `LLM_MODEL` | `claude-sonnet-5-5` | Modelo do extrator LLM |

## Quando passa para um humano

Seis critérios explícitos (`src/autoseguro/policy.py`), tabela completa em
[`docs/DECISIONS.md`](docs/DECISIONS.md#critérios-de-handoff): `user_request`, `complaint`,
`out_of_scope`, `no_progress`, `quote_unavailable`, `quote_rejected`.

## Quando a `/quote` falha

Timeout curto → retry com backoff exponencial + jitter dentro de um deadline → circuit breaker →
handoff com mensagem honesta. **Nunca inventa preço.** Erros de validação (422) não são repetidos:
o agente pede ao lead para corrigir o campo apontado. Ver [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Rastreabilidade e dados sensíveis

Cada evento é uma linha JSON (`message_in`, `slots`, `quote_attempt`, `quote_ok`, `quote_failed`,
`quote_rejected`, `handoff`, `message_out`) com `conversation_id`, `message_id` e, nas cotações,
`request_id` (enviado à API como `X-Request-ID`). CPF, e-mail, telefone, placa e CEP são mascarados
antes de logar. O extrator LLM recebe o texto já sem CPF/e-mail/telefone/placa.

## Testes e CI

```bash
uv run pytest --cov              # unitários (API de cotação mockada com respx)
uv run ruff check . && uv run ruff format --check .
QUOTE_API_URL=http://localhost:8000 uv run pytest -m integration   # contra a API real
```

O GitHub Actions (`.github/workflows/ci.yml`) roda lint, testes com cobertura mínima de 85%, build
da imagem Docker com smoke test do `/health` e, quando há `quote-service/`, os testes de integração
contra a API real.

## Estrutura

```
src/autoseguro/   agent.py (estados) · quote_client.py (resiliência) · extractor.py
                  policy.py (handoff) · tracing.py (JSONL + PII) · api.py · cli.py · messages.py
tests/            unitários por módulo + test_docs.py (guarda de documentação) + integração
docs/             DECISIONS.md (decisões e critérios) · execution-log.md (execução completa)
ai-logs/          conversas com IAs usadas no desafio
scripts/          fake_quote_server.py (stub de desenvolvimento)
```

## Premissas e limitações

- O formato exato das respostas de `/planos` e `/quote` não estava disponível ao escrever o código.
  `parse_plans` e `PRICE_KEYS` (em `quote_client.py`) aceitam variações comuns; **confira contra a
  API real** e ajuste ali (um único lugar). Resposta sem preço válido é tratada como falha.
- As regras de cotação ficam **na API** (fonte única): o agente não as duplica, reage aos 422.
- Estado de conversas em memória (1 réplica). Para escalar, implemente outra `Store` (Redis).
- O dataset de conversas ainda não é usado; próximo passo natural: avaliação offline do extrator e
  levantamento de objeções.

## Contribuindo

Veja [`AGENTS.md`](AGENTS.md). Resumo: mudou comportamento, config ou critério → atualize README /
`docs/DECISIONS.md` no mesmo PR, com testes.
