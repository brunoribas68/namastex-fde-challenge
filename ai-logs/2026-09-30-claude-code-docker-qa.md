# Claude Code — Docker de testes, revisão do README e roteiro de QA (30/09/2026)

Sessão do Claude Code (web). Resumo das mensagens e do que foi feito; sem segredos nem dados
pessoais.

## Pedidos

1. `uv run pytest --cov --cov-fail-under=85` dentro do container `agent` falhava com
   `failed to remove file .../_editable_impl_autoseguro_agent.pth: Permission denied`.
2. Mesmo erro com `uv run ruff check .` via `docker exec -it <agent> bash` (sem `sudo`).
3. "Arrume o build do Docker para não ter que usar esse comando (docker run com volume); a pessoa
   baixa o projeto, roda os comandos do README e tudo funciona. Valide o README, crie um roteiro de
   QA e leia o projeto todo para ver se o que o desafio pede está certo, com testes adicionais."

## Diagnóstico

- O `.venv` da imagem era criado como root e o container roda como `app`; a imagem é de produção
  (`--no-dev`, sem `tests/`), então `uv run` tentava sincronizar as deps de dev e não podia escrever.

## O que mudou

- `app/Dockerfile` multi-stage: `runtime` (padrão, enxuto, `.venv` do usuário `app`, `UV_NO_SYNC=1`)
  e `test` (deps de dev + testes). Novo serviço `tests` no compose (perfil `test`):
  `docker compose run --rm --build tests`. `.dockerignore` deixa de excluir `tests/` e `docs/`.
- `docker-compose.yml`: instabilidade da quote-api configurável por `.env`/shell (padrões mantidos).
- Bugs achados no QA manual contra a quote-api real e corrigidos com teste:
  - data de início **no passado** era cotada normalmente;
  - ano do veículo **no futuro** (erro de digitação) virava recusa + handoff em vez de pedir correção.
- `tests/test_challenge.py`: aceitação por critério do desafio, com o `QuoteClient` real contra uma
  `/quote` simulada (503, timeout, 200 malformado, recusa, validação, circuit breaker, trace, PII).
- Docs: `app/README.md` (Docker-first, PowerShell, testes em container), `DECISIONS.md`,
  `execution-log.md` regenerado, novo `app/docs/QA.md`, bloco "Solução" do README raiz, CI rodando o
  serviço `tests`.

## Como foi validado

Stack subida com `docker compose up --build`, `docker compose run --rm --build tests` (89 testes,
98% de cobertura), integração contra a quote-api real (5/5) e o roteiro de QA executado cenário a
cenário (caminho feliz, API 100% fora, lenta, parada, recusas, handoff, idempotência, PII).

Log bruto da sessão: `~/.claude/projects/<slug>/*.jsonl` do ambiente da sessão (não copiado por
conter contexto do ambiente; exporte pelo menu da sessão se quiser anexar).

## Continuação: acentos quebrados no PowerShell

No Windows PowerShell 5.1, `Invoke-RestMethod` mostrava "CotaÃ§Ã£o". O JSON já saía em UTF-8, mas
sem `charset` no `Content-Type` o PowerShell decodifica como Latin-1. A API passou a responder
`application/json; charset=utf-8` (com teste); o envio em UTF-8 já tinha sido corrigido na função
`m` do `QA.md`. Linux/macOS (`curl`) não eram afetados.

## Continuação (01/10): preparar o código para mudanças de planos e regras

Pedido: "Quais seriam as dificuldades caso mudassem os planos e coisas do tipo? Prepare o código e a
mim para essas perguntas na entrevista."

- Medi o comportamento atual com a API simulada mudando. Problemas encontrados: plano "Completo
  Plus" ao lado de "Completo" ficava ambíguo para sempre; plano removido com o catálogo em cache
  virava handoff; id `top_plus` não casava com "top plus".
- Correções: o nome de plano mais longo vence; recusa da `/quote` força recarregar `/planos`, e se o
  plano saiu o agente pergunta de novo; plano removido entre turnos também; `PLANS_CACHE_TTL_S`
  configurável; o LLM recebe as chaves de `SLOT_ORDER`; guardas de teste para campo novo.
- `tests/test_change_scenarios.py` (um teste por mudança; os 4 corrigidos falhavam antes),
  `docs/EVOLUCAO.md` (cenários, checklist, limites e perguntas prováveis) e a seção K do QA (demo ao
  vivo adicionando/removendo plano no `plans.json` da quote-api, validada com Docker).

## Continuação (01/10): arquitetura, elasticidade e escalabilidade

Pedido: "pensando em arquitetura de sistema, elasticidade, escalabilidade e outros parâmetros, veja
se está tudo certo".

- Teste de carga na stack do compose (instabilidade padrão): ~330 msg/s em coleta, ~15–30
  cotações/s; gargalo na `/quote` síncrona e lenta.
- Achado: **vazamento de memória**: conversas nunca saíam da memória (+20 MB a cada 10 mil leads).
  Correção: expiração por inatividade (`CONVERSATION_TTL_S`), O(1) amortizado, sem remover
  conversa em processamento; memória medida estável em ~50 MB depois de 40 mil conversas.
- Circuit breaker protegido por lock (é compartilhado entre threads); protocolo `Store`
  (`lock`/`get`/`save`) para o `RedisStore` futuro; testes de concorrência (mesma conversa
  serializada, conversas diferentes em paralelo, reenvio concorrente cota uma vez só).
- `scripts/load_test.py` e `docs/ARQUITETURA.md` (capacidade medida, o que quebra ao escalar errado,
  caminho por etapas, perguntas prováveis).
