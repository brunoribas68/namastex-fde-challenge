# Logs de uso de IA

Conversas com as IAs usadas no desafio (fazem parte da avaliação). Segredos e dados pessoais foram
removidos.

| Ferramenta | Conversa | Para que foi usada |
|---|---|---|
| Claude.ai | [Conversa compartilhada](https://claude.ai/share/0a2fe53e-8f7b-4af2-bc5c-fdf118460a5c) | Construção do agente: arquitetura, código, testes, Docker, CI e documentação |
| Claude Code (web) | [Sessão](https://claude.ai/code/session_01C6q6vTGZ8zKs6cvuGKgxuB) · resumo em [`2026-09-30-claude-code-docker-qa.md`](2026-09-30-claude-code-docker-qa.md) | Revisão e endurecimento: Docker de testes, README e roteiro de QA, testes de aceitação, acentos no PowerShell, mudanças de catálogo, arquitetura/escala (teste de carga, vazamento de memória) |

## Como a IA foi usada (resumo)

1. **Claude.ai**: desenho da solução e primeira versão completa (agente, cliente resiliente da
   `/quote`, critérios de handoff, trace sem dados pessoais, testes, Docker e CI).
2. **Claude Code**: revisão contra o enunciado, com a stack real rodando. Ele achou e corrigiu bugs
   que os testes não pegavam:
   - data de início no passado era cotada;
   - plano removido do catálogo levava o lead para um humano;
   - acentos quebrados no PowerShell;
   - memória sem limite.

   Também mediu a capacidade com teste de carga e preparou as respostas para as perguntas de
   evolução e escala (`app/docs/EVOLUCAO.md`, `app/docs/ARQUITETURA.md`).

Em todos os passos, as decisões e a validação final (QA manual no Windows/PowerShell, merges) foram
minhas; os commits gerados com IA têm o rodapé `Co-Authored-By`.
