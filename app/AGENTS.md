# Instruções para quem contribui (humanos e ferramentas de IA)

1. **Documentação junto com o código.** Alterou comportamento, variável de ambiente, rota,
   critério de handoff ou decisão? Atualize `README.md` e/ou `docs/DECISIONS.md` no mesmo commit.
2. **Testes junto com o código.** Toda regra nova ganha teste unitário; `uv run pytest --cov` e
   `uv run ruff check . && uv run ruff format --check .` devem passar.
3. **Nunca invente preço.** Preço só existe se `/quote` retornou. Falha vira handoff.
4. **Sem dados pessoais** em logs, testes ou commits (use os mascaradores de `tracing.py`).
5. **Registre o uso de IA** em `ai-logs/` (exigência do desafio), sem segredos.
6. Mantenha simples: prefira mudar um módulo existente a criar abstrações novas.
