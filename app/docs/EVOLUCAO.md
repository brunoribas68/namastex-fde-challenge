# E se o negócio mudar? (planos, regras, campos, contrato da API)

Guia para quem vai manter o agente: o que muda sozinho, o que degrada com segurança e o que exige
código. Cada linha das tabelas tem teste em `tests/test_change_scenarios.py`. No fim, as perguntas
que costumam aparecer sobre isso.

## O princípio

**Catálogo, preço e regras pertencem à API de cotação**, não ao agente.

- Os planos (id e nome) vêm de `GET /planos`, com cache de `PLANS_CACHE_TTL_S` (padrão 300 s).
- O preço e os detalhes (franquia, coberturas, carência, pro-rata) vêm só da resposta da
  `POST /quote`.
- Para recusas, o agente repassa o `motivo` da API, sem duplicar regra nenhuma.

O agente só conhece **quais dados pedir** (`SLOT_ORDER`) e **o que é absurdo** para o lead (vigência
no passado, carro do futuro). Com isso a maioria das mudanças de negócio não exige deploy do agente.

## 1. Muda sozinho, sem código

| Mudança na API | O que o agente faz | Teste |
|---|---|---|
| Plano novo | Aparece na lista e é cotável em até `PLANS_CACHE_TTL_S` | `test_new_plan_is_offered_and_quoted_after_cache_expires` |
| Preço base, multiplicador, faixa de idade, região de risco | Nada a fazer: o preço exibido é o que a API devolveu | `test_new_price_or_rule_needs_no_code` |
| Regra de recusa nova (ex.: CEP fora da área) | Explica com o `motivo` da API e passa ao humano (`quote_refused`) | `test_new_refusal_rule_is_explained_with_the_api_reason` |
| Plano com nome que contém outro ("Completo" e "Completo Plus") | O nome mais longo vence; "completo plus" não é ambíguo | `test_plan_name_containing_another_is_not_ambiguous` |
| id com `_`/`-` (`top_plus`) | Reconhece "top plus" | `test_plan_id_with_underscore_matches_spoken_form` |
| Nome com acento ("Básico") | Reconhece com ou sem acento | `test_plan_name_with_accent_matches_with_or_without_it` |
| Campo novo na resposta da `/quote` (ex.: `desconto`) | Ignorado; a resposta continua saindo. Detalhe em formato inesperado é omitido, nunca adivinhado | `test_new_field_in_quote_response_does_not_break_the_reply` |
| `GET /planos` fora do ar | Usa o último catálogo conhecido | `test_planos_endpoint_down_keeps_last_known_catalog` |

## 2. Plano removido: o lead não se perde

| Situação | O que o agente faz | Teste |
|---|---|---|
| Plano removido enquanto o catálogo velho estava em cache | A API recusa ("Plano inexistente"). O agente recarrega `/planos` na hora (`list_plans(refresh=True)`), avisa "O plano X não está mais disponível" e pergunta de novo, já com a lista nova | `test_plan_removed_while_cached_asks_for_another_plan` |
| Plano removido entre um turno e outro | Ao ver o catálogo novo, esquece a escolha e pergunta de novo | `test_plan_removed_between_turns_is_asked_again` |
| Recusa com o plano ainda no catálogo | É regra de negócio: handoff `quote_refused`, como antes | `test_refusal_with_plan_still_listed_still_hands_off` |

## 3. Muda o contrato: degrada com segurança, precisa de código

O pior caso é cotar errado, e isso não acontece: o agente **nunca mostra um preço que não seja o
`premio_mensal` válido da API para o plano pedido**.

| Mudança | O que acontece hoje | O que fazer |
|---|---|---|
| Campo **obrigatório novo** na `/quote` (ex.: `uso_veiculo`) | 422 com um campo que o agente não conhece → handoff `quote_rejected`, sem preço (`test_new_required_field_hands_off_without_price`) | Seguir o checklist abaixo |
| `premio_mensal` renomeado / formato novo | Resposta vira `malformed_response` → retry → handoff `quote_unavailable` (`test_renamed_price_field_hands_off_without_price`) | Ajustar `parse_quote`. Em produção, alertar sobre `outcome: malformed_response` no trace: muitos seguidos indicam mudança de contrato, não instabilidade (e abrem o circuit breaker) |
| `GET /planos` com outro formato | `parse_plans` já aceita lista, `{"planos": [...]}` e `{id: {...}}`; formato desconhecido = lista vazia → handoff `quote_unavailable` se precisar perguntar o plano | Ajustar `parse_plans` |
| Moeda diferente de BRL | O template formata como `R$` | Usar o `moeda` da resposta em `messages.money` |
| Detalhe novo que o lead **deve** ver (ex.: desconto) | Ignorado (seguro, mas incompleto) | Uma linha em `messages._details` + teste |

### Checklist: adicionar um campo que a cotação passou a exigir

1. `models.py`: adicionar o atributo em `Slots` e o nome em `SLOT_ORDER` (a ordem é a das perguntas).
2. `messages.py`: texto da pergunta em `LABELS`.
3. `extractor.py`: regex no `RegexExtractor` e a chave no prompt do `LLMExtractor`. O LLM já recebe
   as chaves de `SLOT_ORDER`; falta só a descrição do tipo.
4. Se houver valor "absurdo" para o lead, uma regra em `Agent._drop_invalid` e uma mensagem em
   `messages.INVALID`.
5. Testes e docs (README, `DECISIONS.md`).

Dois testes de guarda falham se você esquecer o 2 ou o 3: `test_every_slot_has_a_question` e
`test_llm_extractor_asks_for_every_slot`. Campo **opcional** novo não precisa de nada: o agente só
deixa de enviá-lo, e a API usa o padrão dela.

## Demo ao vivo (sem deploy do agente)

A quote-service relê `data/plans.json` a cada requisição, então dá para mudar o catálogo com a stack
no ar. Ponha `PLANS_CACHE_TTL_S=5` no `.env` e rode `docker compose up -d`. Os passos estão no
[roteiro de QA, seção K](QA.md#k-mudança-de-catálogo-ao-vivo).

## Limites conhecidos e próximos passos

- **Cache por réplica.** Com várias réplicas, cada uma vê o plano novo no seu tempo (≤ TTL). Para
  ser instantâneo: webhook/evento de "catálogo mudou" ou cache compartilhado (Redis).
- **Recusa específica de um plano** (ex.: premium só para carro até 5 anos). Hoje vira handoff.
  Melhoria: em `quote_refused`, oferecer cotar outro plano antes de passar ao humano. Isso exige que
  a API diga se a recusa é do plano ou do lead (código de erro estruturado em vez de texto).
- **Palavras de handoff** (`HUMAN`, `COMPLAINT`, `OUT_OF_SCOPE` em `extractor.py`) e limites da
  `Policy` estão no código. Se o time de vendas quiser ajustá-los sem deploy, eles vão para
  config/env.
- **Validade da cotação.** O agente não guarda prazo; se a API passar a devolver `valida_ate`, basta
  exibir em `_details`.
- **Avaliação contínua.** Rodar o extrator contra o dataset de conversas (fora do repo público) a
  cada mudança de catálogo, para medir quantos leads ele entende.

## Perguntas prováveis (e respostas curtas)

**"E se amanhã entrar um plano novo?"**
Nada no agente. Ele lê `/planos`; em até `PLANS_CACHE_TTL_S` o plano aparece na pergunta e é
reconhecido pelo nome ou id. Dá para mostrar ao vivo (seção K do QA).

**"E se mudarem o preço ou uma regra (idade, região, carência)?"**
Nada no agente. Preço e regras são da API; o agente mostra o `premio_mensal` e repassa o `motivo` da
recusa. Duplicar regra no agente criaria duas fontes de verdade.

**"E se tirarem um plano que o lead já escolheu?"**
A API recusa, o agente recarrega o catálogo na hora, avisa que o plano saiu e oferece os atuais. O
lead não vai para um humano por causa disso.

**"E se a API passar a exigir um campo novo?"**
Até o deploy: handoff `quote_rejected`, sem preço, com os dados já coletados no evento `handoff`.
O deploy segue o checklist de 5 passos, protegido por dois testes de guarda.

**"E se mudarem o formato da resposta?"**
O agente valida `premio_mensal` (número > 0) e o eco do `plano_id`; fora disso é
`malformed_response`, nunca preço. Em produção eu alertaria nesse `outcome`.

**"Por que cache de planos e não buscar sempre?"**
`/planos` é chamado a cada mensagem; o cache poupa a API legada instável e mantém o catálogo
quando ela cai. O custo é o atraso de até TTL, mitigado pela recarga forçada quando a API recusa.

**"Por que não deixar o LLM responder livremente?"**
Porque o erro mais caro em vendas é o preço errado. O LLM só extrai campos; texto e preço são
templates e dados da API. Isso também deixa toda mudança testável.
