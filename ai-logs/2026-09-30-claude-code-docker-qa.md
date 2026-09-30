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
