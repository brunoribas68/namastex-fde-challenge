# AutoSeguro Agent

Agente de WhatsApp que qualifica leads de seguro de veículo, **cota via `POST /quote`** e decide, com
critério explícito, entre resolver sozinho ou **passar para um humano**. Feito para o desafio
técnico FDE / AI Engineer da Namastex.

> Este README cobre o código em `app/`. O enunciado do desafio está em [`../README.md`](../README.md).
> Regra do projeto: **toda mudança de código atualiza a documentação** (este README e `docs/`).
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

Pré-requisito: **Docker** (com Docker Compose v2). Todos os comandos são a partir da **raiz do
repositório** e funcionam igual no Linux, macOS e Windows (PowerShell). Não é preciso instalar
Python nem `uv` para subir, testar e fazer QA.

### 1. Subir a stack

```bash
cp .env.example .env            # opcional: ANTHROPIC_API_KEY liga o extrator LLM
docker compose up --build -d    # quote-api em :8000, agente em :8080
docker compose ps               # os dois serviços devem ficar "healthy"
```

### 2. Conversar com o agente

Pela API HTTP (é o que o canal do WhatsApp chamaria):

```bash
curl localhost:8080/health
curl -X POST localhost:8080/messages -H 'content-type: application/json' -d '{
  "conversation_id": "lead-1",
  "text": "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/12/2026, plano completo"
}'
```

No **Windows PowerShell**, `curl` é um apelido de outro comando; use `Invoke-RestMethod`:

```powershell
Invoke-RestMethod localhost:8080/health
Invoke-RestMethod localhost:8080/messages -Method Post -ContentType 'application/json' -Body '{"conversation_id":"lead-1","text":"Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/12/2026, plano completo"}'
```

Ou pelo terminal, dentro do container do agente:

```bash
docker compose exec agent python -m autoseguro.cli --demo   # conversa roteirizada
docker compose exec agent python -m autoseguro.cli          # chat interativo (Ctrl+D sai)
```

O trace (JSONL) sai no stdout do agente: `docker compose logs -f agent`.

### 3. Rodar os testes (também em Docker)

```bash
docker compose run --rm --build tests                          # ruff + unitários com cobertura >= 85%
docker compose run --rm --build tests pytest -m integration    # contra a quote-api real do compose
```

O serviço `tests` usa o alvo `test` do `app/Dockerfile` (dependências de dev + testes). Ele não
sobe no `docker compose up`; o `--build` garante que a imagem tem o código atual.

> **Não rode `uv run pytest` dentro do container `agent`.** Ele é a imagem de produção: não tem
> testes nem dependências de dev (por isso o `pytest` não existe lá). Use o serviço `tests` acima.

### 4. Simular instabilidade da `/quote`

As taxas de falha da quote-api vêm do `.env` (ou do shell) e têm os padrões do desafio
(`QUOTE_FAILURE_RATE=0.20`, `QUOTE_SLOW_RATE=0.10`, `QUOTE_SLOW_SECONDS=8`, `QUOTE_SEED` vazio).
Ex.: API sempre fora do ar, depois volta ao padrão:

```bash
QUOTE_FAILURE_RATE=1 docker compose up -d quote-api     # PowerShell: $env:QUOTE_FAILURE_RATE="1"; docker compose up -d quote-api
docker compose up -d quote-api                          # (sem a variável) volta ao padrão
```

Roteiro de QA completo, com resultado esperado para cada cenário: [`docs/QA.md`](docs/QA.md).

Em servidor: mesmo `docker compose up -d`. O container roda como usuário não-root, tem
`HEALTHCHECK`, `restart: unless-stopped` e escreve o trace no stdout.

### Local (sem Docker, para desenvolver)

Requer [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

```bash
(cd quote-service && uv run uvicorn app.main:app --port 8000)   # API de cotação, na raiz do repo
cd app && uv sync                          # instala dependências (inclui as de dev)
uv run python -m autoseguro.cli            # conversa no terminal
uv run python -m autoseguro.cli --demo     # conversa roteirizada (gera o log de execução)
uv run uvicorn autoseguro.api:create_app --factory --port 8080
```

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
| `QUOTE_DEADLINE_S` | `15.0` | Orçamento total de tempo por cotação |
| `TRACE_FILE` | `logs/trace.jsonl` | Arquivo do trace; `-` escreve no stdout (padrão no Docker) |
| `ANTHROPIC_API_KEY` | vazio | Se definida, usa LLM para extrair dados; senão, regex |
| `LLM_MODEL` | `claude-sonnet-5-5` | Modelo do extrator LLM |

## Quando passa para um humano

Sete critérios explícitos (`src/autoseguro/policy.py`), tabela completa em
[`docs/DECISIONS.md`](docs/DECISIONS.md#3-critérios-de-handoff): `user_request`, `complaint`,
`out_of_scope`, `no_progress`, `quote_unavailable`, `quote_rejected`, `quote_refused`.

## Quando a `/quote` falha

Timeout curto (a API tem chamadas lentas de 8 s e ~20% de 5xx) → retry com backoff exponencial +
jitter dentro de um deadline → circuit breaker → handoff com mensagem honesta. **Nunca inventa
preço.** Recusa de negócio (422 `cotacao_recusada`, ex.: idade > 75) e erro de validação não são
repetidos: a primeira explica o motivo e passa ao humano; a segunda pede ao lead que corrija o campo. Ver [`docs/DECISIONS.md`](docs/DECISIONS.md).

Antes de cotar, o agente descarta valores que a API aceitaria mas não fazem sentido e pede de novo:
**data de início no passado** e **ano do veículo no futuro** (além do ano que vem, para aceitar
carro "ano/modelo" seguinte).

## Rastreabilidade e dados sensíveis

Cada evento é uma linha JSON (`message_in`, `slots`, `quote_attempt`, `quote_ok`, `quote_failed`,
`quote_rejected`, `quote_refused`, `handoff`, `message_out`) com `conversation_id`, `message_id` e, nas cotações,
`request_id` (enviado à API como `X-Request-ID`). CPF, e-mail, telefone, placa e CEP são mascarados
antes de logar. O extrator LLM recebe o texto já sem CPF/e-mail/telefone/placa.

## Testes e CI

Em Docker, ver [Rodar os testes](#3-rodar-os-testes-também-em-docker). Local, de dentro de `app/`:

```bash
uv run pytest --cov              # unitários (API de cotação mockada com respx)
uv run ruff check . && uv run ruff format --check .
QUOTE_API_URL=http://localhost:8000 uv run pytest -m integration   # contra a quote-api real
```

`tests/test_challenge.py` tem um teste de aceitação por critério de avaliação do desafio (ponta a
ponta, `/quote` falhando, handoff, rastreabilidade, dados sensíveis), usando o `QuoteClient` real
contra uma `/quote` simulada e entrando pela API HTTP.

O GitHub Actions (`.github/workflows/ci.yml`, na raiz do repo) roda lint, testes com cobertura
mínima de 85%, build da imagem Docker com smoke test do `/health`, os testes pelo serviço `tests`
do compose e os testes de integração contra a `quote-api` real.

## Estrutura

```
app/src/autoseguro/   agent.py (estados) · quote_client.py (resiliência) · extractor.py
                      policy.py (handoff) · tracing.py (JSONL + PII) · api.py · cli.py · messages.py
app/tests/            unitários por módulo + test_challenge.py (aceitação) + test_docs.py
                      (guarda de documentação) + test_integration.py
app/docs/             DECISIONS.md (decisões e critérios) · execution-log.md (execução completa)
                      QA.md (roteiro de teste manual)
```

## Contrato da API de cotação (validado contra a `quote-service`)

- `GET /planos` → `{moeda, planos: [{id, nome, base_mensal, franquia, coberturas}], regras}`;
  ids: `essencial`, `completo`, `premium`.
- `POST /quote` 200 → `premio_mensal`, `plano_id`, `franquia`, `coberturas`, `carencia`,
  `primeiro_pagamento_pro_rata` (só se a vigência não começa no dia 1º).
- Erros: 5xx (instabilidade simulada), 422 `{"error": "cotacao_recusada", "motivo"}` (regra de
  negócio), 422 `{"detail": [...]}` (validação do FastAPI) e 400 `{"error": "payload_invalido"}`.
- `plano_id` ausente vira `essencial` na API; por isso o agente sempre envia o plano e confere o
  `plano_id` da resposta.

## Premissas e limitações

- As regras de cotação ficam **na API** (fonte única): o agente não as duplica, reage às recusas.
- Coletamos os cinco campos mesmo com `cep` e `data_inicio` opcionais na API: sem CEP o agravo de
  região some do preço e sem data não há pro-rata, e a cotação sairia enganosamente mais barata.
- Estado de conversas em memória (1 réplica). Para escalar, implemente outra `Store` (Redis).
- O dataset do desafio (`dataset/`, com dados pessoais) foi removido deste repositório de propósito
  e não é usado; próximo passo natural: avaliar o extrator nele, fora do repo público.
- Lead menor de 18 anos ou com mais de 75 é recusado pela API e cai em `quote_refused`.

## Contribuindo

Veja [`../AGENTS.md`](../AGENTS.md). Resumo: mudou comportamento, config ou critério → atualize README /
`docs/DECISIONS.md` no mesmo PR, com testes.
