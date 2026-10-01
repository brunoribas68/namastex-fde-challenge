# Arquitetura, escala e operação

O que existe hoje, quanto aguenta (medido), onde está o gargalo e o caminho para escalar. Decisões
de produto ficam em [`DECISIONS.md`](DECISIONS.md); mudanças de negócio, em [`EVOLUCAO.md`](EVOLUCAO.md).

## Hoje: um processo, síncrono, estado em memória

```
WhatsApp/canal ──POST /messages──▶ agente (1 container, 1 processo uvicorn, pool de threads)
                     ◀── resposta ──    │  lock por conversa → extrai → decide → (cota) → responde
                                        │  conversas em memória, com expiração (CONVERSATION_TTL_S)
                                        ▼
                               quote-api (legada, instável): timeout 3 s, retry, deadline 15 s,
                               circuit breaker; catálogo /planos em cache (PLANS_CACHE_TTL_S)
```

O que já está pronto para produção:
- **Configuração** só por variáveis de ambiente.
- **Container:** imagem enxuta, usuário não-root, `HEALTHCHECK`, `restart: unless-stopped`, log
  JSON no stdout.
- **Idempotência** por `message_id`.
- **Concorrência:** mensagens da mesma conversa são serializadas e conversas diferentes rodam em
  paralelo (testado).
- **Proteção da API legada:** circuit breaker seguro entre threads e deadline por cotação.
- **Memória limitada:** conversas paradas expiram.

## Capacidade medida

Com `scripts/load_test.py`, contra a stack do compose: 1 container do agente e a quote-api com a
instabilidade padrão (20% de 5xx, 10% de chamadas lentas de 8 s), numa máquina de desenvolvimento.

| Cenário | Vazão | Latência | Desfecho |
|---|---|---|---|
| Mensagens de coleta (sem `/quote`), 50 em paralelo | **~330–380 msg/s** | p50 0,12 s, p95 0,3 s | 100% respondidas |
| Mensagem que cota, 10–100 em paralelo | **~15–30 cotações/s** (varia com as chamadas lentas sorteadas) | p50 0,01–1,5 s, **p95 4–9 s** | ~98–99% cotadas, ~1–2% `quote_unavailable` (nunca preço inventado) |
| Memória, 40 mil conversas novas | estável em **~50 MB** com expiração | | antes da expiração: +20 MB a cada 10 mil conversas, sem limite |

Uma conversa ativa ocupa ~2 KB. Com o `CONVERSATION_TTL_S` padrão (24 h), 1 milhão de leads/dia
cabem em ~2 GB.

**Onde está o gargalo:** a cotação é síncrona, e cada chamada lenta da `/quote` prende uma thread do
servidor por até 3 s (timeout), ou até 15 s (deadline) se as tentativas forem se repetindo. Pela lei
de Little, com ~40 threads e latência média de ~1–2 s, o teto fica em ~20–40 cotações/s por
processo. **Mais réplicas não resolvem sozinhas:** o limite real é a API legada, e réplicas a mais
só aumentam a pressão sobre ela (ver o passo 3).

## O que quebra se escalar do jeito errado

| Ação | Problema | Por quê |
|---|---|---|
| `docker compose up --scale agent=3` ou `uvicorn --workers 4` | A conversa se divide: cada processo vê parte das mensagens e pede os dados de novo; a idempotência deixa de funcionar | Estado em memória do processo |
| Restart / deploy | Conversas em andamento recomeçam; **um lead já encaminhado ao humano volta a falar com o bot** | Idem |
| Muitas réplicas com a `/quote` instável | Cada réplica tem o próprio circuit breaker e os próprios retries: a carga na API legada cresce com o número de réplicas | Breaker e retries são locais |

Por isso hoje a regra é **1 réplica, 1 worker**. O código já tem a interface para sair disso: o
agente depende do protocolo `Store` (`lock`, `get`, `save`), não do `InMemoryStore`.

## Caminho para escalar (por ordem de impacto)

1. **Estado em Redis (`RedisStore`) → réplicas horizontais.** O `RedisStore` implementa o protocolo
   `Store`:
   - `get`/`save` gravam a conversa em JSON;
   - `lock` vira um lock distribuído por conversa (`SET NX PX` com token);
   - a expiração vira `EXPIRE` com `CONVERSATION_TTL_S`.

   Com isso o agente fica sem estado: N réplicas atrás de um load balancer, autoscaling por CPU ou
   latência, deploy sem perder conversas e idempotência entre réplicas.
2. **Webhook assíncrono + fila.** O WhatsApp quer um `200` rápido e reenvia quando não recebe.
   Responder dentro da requisição, com até 15 s de `/quote`, não escala. O caminho:
   - o webhook só valida, enfileira e devolve `200` (milissegundos);
   - a fila (SQS, Redis Streams ou Kafka) usa o `conversation_id` como chave de partição, o que
     preserva a ordem por conversa;
   - workers processam e respondem pela API de envio do WhatsApp;
   - os workers escalam pelo tamanho da fila (ex.: KEDA).

   O `Agent.handle` não muda: só passa a ser chamado pelo worker.
3. **Proteger a API legada globalmente.** Os mecanismos:
   - limite de concorrência e de taxa para a `/quote` (bulkhead), compartilhado entre réplicas;
   - **orçamento de retries**, para que os retries não multipliquem a carga numa queda;
   - circuit breaker compartilhado (estado no Redis).

   Assim, escalar o agente não derruba o sistema legado.
4. **Observabilidade de produção.** O trace JSON já traz `conversation_id`, `message_id` e
   `request_id`; faltam:
   - métricas (Prometheus): tentativas por `outcome`, histograma de latência da `/quote`, handoffs
     por motivo, estado do breaker;
   - alertas: taxa de `quote_unavailable`, pico de `malformed_response` (indício de contrato
     mudado), p95;
   - OpenTelemetry propagando o `request_id`.
5. **Readiness x liveness.** `/health` é liveness. A readiness **não** deve depender da `/quote`:
   com a API fora, o agente continua útil (coleta e faz o handoff honesto).
6. **Segurança e custo.**
   - Validar a assinatura do webhook (`X-Hub-Signature-256` do WhatsApp).
   - Rate limit por conversa, contra abuso e contra custo de LLM.
   - Chaves em secret manager.
   - Política de retenção dos logs (LGPD); os dados já saem mascarados.
   - Chamar o LLM só quando o regex não extrair nada, para reduzir o custo por mensagem.
7. **Desligamento gracioso.** O uvicorn termina as requisições em andamento no `SIGTERM`. Com fila,
   mensagem não confirmada volta para a fila.

## Perguntas prováveis

**"Aguenta quanto?"** Medido: ~330 msg/s em coleta e ~15–30 cotações/s por processo, com memória
estável. O gargalo é a `/quote` síncrona e lenta, não o agente.

**"Como escala para 10x?"** Primeiro Redis no lugar da memória (a interface `Store` já existe),
depois N réplicas. Para 100x: webhook assíncrono com fila particionada por conversa e limite global
de chamadas à API legada.

**"Por que não fez assim desde o início?"** Para o escopo do desafio, 1 processo síncrono é
testável, simples de rodar e atende com folga. As peças que mudam na escala (store, fila, limitador)
estão isoladas atrás de interfaces pequenas; o núcleo (`Agent.handle`) não muda.

**"E se reiniciar no meio da conversa?"** Hoje a conversa recomeça (estado em memória). Com o
`RedisStore`, nada se perde. O caso crítico é o lead já encaminhado ao humano voltar a falar com o
bot, e é o primeiro motivo para persistir o estado.

**"Escalar o agente não piora a API legada?"** Piora, se não houver limite global: cada réplica
retenta por conta própria. Por isso o passo 3: limite de concorrência e orçamento de retries
compartilhados.
