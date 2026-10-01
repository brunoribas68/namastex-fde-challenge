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
| 422 `cotacao_recusada` | **Sem retry.** Regra de negócio (idade > 75, veículo > 20 anos...): explica o motivo e faz handoff `quote_refused` |
| 400 / 422 de validação | **Sem retry.** Pede ao lead para corrigir o campo apontado; 2ª recusa (ou campo desconhecido) → handoff `quote_rejected` |
| 200 sem `premio_mensal` válido ou com `plano_id` diferente do pedido | Tratado como falha e refeito (a API assume `essencial` sem plano; conferir o eco evita cotar o plano errado) |
| 401/403/404 | Falha imediata (configuração), handoff |
| Falhas seguidas | Circuit breaker abre (5 falhas, cooldown 30 s): falha rápido em vez de empilhar timeouts |
| Esgotou tudo | Handoff `quote_unavailable` com mensagem honesta; **nenhum preço é inventado** |

Cada tentativa vai ao trace (`quote_attempt`) e a chamada leva `X-Request-ID`. O deadline total
mantém a conversa responsiva (4 tentativas de 3 s cabem em 15 s; a API tem chamadas lentas de 8 s). Mensagens repetidas do webhook (`message_id`) não recotam.

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
| `quote_refused` | A API recusou por regra de negócio (idade > 75, veículo > 20 anos) |

Depois do handoff o bot **para de responder** com conteúdo novo (não disputa a conversa com o humano).
O evento `handoff` leva o motivo e os dados já coletados, para o humano não recomeçar do zero.

## 4. Dados sensíveis (LGPD)

Logs mascaram CPF, e-mail, telefone, placa e CEP (`tracing.py`). O LLM recebe o texto sem esses
dados (exceto CEP, necessário para cotar). O histórico de conversas do desafio não é versionado nem
enviado a nenhum serviço.

## 5. Regras de cotação ficam na API

`GET /planos` publica as regras; duplicá-las no agente criaria divergência. O agente confia nas
recusas da API e repassa o motivo. Na resposta, mostra o que a API devolveu (franquia, coberturas,
**carência de 30 dias** de roubo/furto e **primeiro pagamento pro-rata**), sem calcular nada.
Coletamos `cep` e `data_inicio` (opcionais na API) porque omiti-los deixaria a cotação mais barata
do que a real (agravo de região, pro-rata).

A exceção são dados que a API **aceitaria** mas que não fazem sentido para o lead: vigência começando
**no passado** (a API cota sem reclamar) e **ano do veículo no futuro** (a API recusaria com
"idade do veículo fora das faixas", e o lead iria para um humano por um erro de digitação). O agente
descarta o valor, explica e pede de novo (evento `slots` com `invalid`). O ano que vem é aceito
(carro ano/modelo seguinte); a regra de negócio sobre ele continua sendo da API.

## 6. Catálogo de planos dinâmico

Os planos vêm de `GET /planos` com cache de `PLANS_CACHE_TTL_S` (300 s): plano novo, preço ou regra
nova não pedem deploy do agente. O cache poupa a API instável e mantém o último catálogo quando ela
cai; o custo é até um TTL de atraso. Para não perder o lead nesse intervalo, uma recusa da `/quote`
força recarregar o catálogo, e se o plano escolhido saiu dele o agente avisa e pergunta de novo em
vez de passar ao humano. O nome de plano mais longo vence ("Completo Plus" não é ambíguo com
"Completo"). Cenários, limites e o checklist para campo novo: [`EVOLUCAO.md`](EVOLUCAO.md).

## 7. Simplicidade operacional

Store em memória com lock por conversa (troca por Redis é uma classe); config só por variáveis de
ambiente; `uv` com lockfile; CI único. Um `Dockerfile` com dois alvos: `runtime` (padrão, enxuto,
sem testes nem deps de dev, usuário não-root dono do `.venv`) e `test` (deps de dev + testes, serviço
`tests` do compose). Assim quem clona o repo sobe, testa e faz QA só com Docker
(`docker compose run --rm --build tests`), sem instalar Python. Sem framework de agentes: o fluxo é
pequeno e cabe em ~150 linhas legíveis.

A API do agente responde `application/json; charset=utf-8`. O JSON já é UTF-8, mas sem o charset
explícito o Windows PowerShell 5.1 (`Invoke-RestMethod`) decodifica como Latin-1 e mostra "CotaÃ§Ã£o".
