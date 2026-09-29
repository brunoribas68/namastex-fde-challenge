# Decisões de engenharia

Cada decisão: o que, por quê e o que foi trocado por isso. Mudou o código? Atualize aqui.

## 1. Máquina de estados determinística; LLM só extrai dados

O agente segue `collecting → quoted | handed_off`. O LLM (opcional) apenas extrai campos da
mensagem; **respostas são templates** e o **preço vem só da API**. Motivo: em vendas por WhatsApp,
um preço alucinado é o pior erro possível, e fluxo determinístico é testável e auditável.
Custo: conversa menos "natural". Sem `ANTHROPIC_API_KEY`, o extrator é regex (offline, rápido,
usado também como fallback quando o LLM falha).

## 2. Resiliência da `/quote`

| Situação | Comportamento |
|---|---|
| Timeout, erro de rede, 429, 5xx, resposta sem preço | Retry com backoff exponencial + jitter, até `QUOTE_MAX_ATTEMPTS` e `QUOTE_DEADLINE_S` |
| 400/422 | **Sem retry.** Pede ao lead para corrigir o campo apontado; 2ª recusa → handoff |
| 401/403/404 | Falha imediata (configuração), handoff |
| Falhas seguidas | Circuit breaker abre (5 falhas, cooldown 30 s): falha rápido em vez de empilhar timeouts |
| Esgotou tudo | Handoff `quote_unavailable` com mensagem honesta; **nenhum preço é inventado** |

Cada tentativa vai ao trace (`quote_attempt`) e a chamada leva `X-Request-ID`. O deadline total
mantém a conversa responsiva. Mensagens repetidas do webhook (`message_id`) não recotam.

## 3. Critérios de handoff

Definidos em `src/autoseguro/policy.py` (`HANDOFF_RULES`) e cobertos por testes.

| `handoff_reason` | Quando |
|---|---|
| `user_request` | Lead pede atendente/humano |
| `complaint` | Reclamação, Procon, advogado, insatisfação forte |
| `out_of_scope` | Sinistro, cancelamento, boleto/apólice, outro produto |
| `no_progress` | 3 turnos seguidos (após o primeiro) sem nenhum dado novo |
| `quote_unavailable` | `/quote` falhou após retries, circuito aberto ou sem lista de planos |
| `quote_rejected` | A API recusou os dados de novo depois de o lead corrigir |

Depois do handoff o bot **para de responder** com conteúdo novo (não disputa a conversa com o humano).
O evento `handoff` leva o motivo e os dados já coletados, para o humano não recomeçar do zero.

## 4. Dados sensíveis (LGPD)

Logs mascaram CPF, e-mail, telefone, placa e CEP (`tracing.py`). O LLM recebe o texto sem esses
dados (exceto CEP, necessário para cotar). O histórico de conversas do desafio não é versionado nem
enviado a nenhum serviço.

## 5. Regras de cotação ficam na API

`GET /planos` publica as regras; duplicá-las no agente criaria divergência. O agente confia no
422 e conversa com o lead sobre o campo recusado.

## 6. Simplicidade operacional

Store em memória com lock por conversa (troca por Redis é uma classe); config só por variáveis de
ambiente; uma imagem Docker; `uv` com lockfile; CI único. Sem framework de agentes: o fluxo é
pequeno e cabe em ~150 linhas legíveis.
