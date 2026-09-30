# Instruções para quem contribui (humanos e ferramentas de IA)

O código do agente fica em `app/` (rode `uv` e `pytest` de dentro dela).

1. **Documentação junto com o código.** Alterou comportamento, variável de ambiente, rota,
   critério de handoff ou decisão? Atualize `app/README.md`, `app/docs/DECISIONS.md` e, se mudar
   onde algo está ou como subir, o bloco "Solução" no topo do `README.md` da raiz (o resto desse
   arquivo é o enunciado original: não edite), no mesmo commit.
2. **Testes junto com o código.** Toda regra nova ganha teste unitário; em `app/`:
   `uv run pytest --cov` e `uv run ruff check . && uv run ruff format --check .` devem passar.
3. **Nunca invente preço.** Preço só existe se `/quote` retornou. Falha vira handoff.
4. **Sem dados pessoais** em logs, testes ou commits (use os mascaradores de `tracing.py`).
5. **Registre o uso de IA** em `ai-logs/` (exigência do desafio), sem segredos.
6. Mantenha simples: prefira mudar um módulo existente a criar abstrações novas.
