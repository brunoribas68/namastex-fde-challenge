# Roteiro de QA (teste manual)

Cenários para validar o agente de ponta a ponta. Cada um tem o comando, o **resultado esperado** e
o critério do desafio que ele cobre. Só precisa de Docker; os comandos são a partir da raiz do repo.
Os preços esperados valem para cotações feitas em 2026 (a idade do veículo conta a partir do ano
corrente).

Ao final há um [checklist de entrega](#j-checklist-de-entrega-do-desafio).

## Preparação

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps        # quote-api e agent "healthy"
```

Função auxiliar para mandar mensagens (use a do seu terminal):

```bash
# bash / zsh / Git Bash
m() { curl -s localhost:8080/messages -H 'content-type: application/json' \
  -d "{\"conversation_id\":\"$1\",\"text\":\"$2\"${3:+,\"message_id\":\"$3\"}}"; echo; }
```

```powershell
# Windows PowerShell
function m($id, $text, $mid) {
    $body = @{ 
        conversation_id = $id
        text            = $text 
    }
    if ($mid) { 
        $body.message_id = $mid 
    }

    $jsonBody = [System.Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Compress))

    Invoke-RestMethod -Uri "http://localhost:8080/messages" -Method Post -ContentType "application/json; charset=utf-8" -Body $jsonBody | 
        Format-List stage, handoff_reason, price, quote_id, text
}
```

A resposta tem `stage` (`collecting`, `quoted`, `handed_off`), `handoff_reason`, `price`,
`quote_id` e `text`. Para ver o trace: `docker compose logs agent --no-log-prefix`. Filtre por
conversa com `| grep qa-b1` (PowerShell: `| Select-String qa-b1`).

O agente entende com ou sem acento. A resposta declara `charset=utf-8`, e a função do PowerShell
envia o corpo em UTF-8. Assim os acentos saem certos também no Windows PowerShell 5.1.

## A. Subida e testes automatizados

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| A1 | `curl localhost:8080/health` e `curl localhost:8000/health` | `{"status":"ok"}` nos dois | ☐ |
| A2 | `curl localhost:8000/planos` | Planos `essencial`, `completo`, `premium` e as regras | ☐ |
| A3 | `docker compose run --rm --build tests` | `All checks passed!`, 105 testes passando, cobertura ≥ 85% | ☐ |
| A4 | `docker compose run --rm --build tests pytest -m integration` | 5 testes passando contra a quote-api real | ☐ |
| A5 | `docker compose exec agent python -m autoseguro.cli --demo` | Três turnos; o último termina em `[stage=quoted]` com R$ 209,90 | ☐ |

## B. Caminho feliz (funciona de ponta a ponta?)

| # | Mensagens | Esperado | ✓ |
|---|---|---|---|
| B1 | `m qa-b1 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027, plano completo"` | `quoted`, **R$ 209,90/mês**, franquia R$ 3.000, coberturas, carência de 30 dias em roubo e furto, 1º pagamento pro-rata **R$ 115,11 (17 de 31 dias)**, código da cotação | ☐ |
| B2 | `m qa-b2 "Oi, quero cotar o seguro do meu carro"` | `collecting`, saudação + lista dos 5 dados | ☐ |
|    | `m qa-b2 "35"` → `m qa-b2 "2019"` → `m qa-b2 "08050-000"` → `m qa-b2 "01/03/2027"` | Cada resposta pede só o que ainda falta | ☐ |
|    | `m qa-b2 "premium"` | `quoted`, **R$ 508,15** (veículo 6–10 anos ×1,15 e CEP de risco `08` ×1,30); começa no dia 1º, então **sem** pro-rata | ☐ |
| B3 | `m qa-b2 "e no plano essencial?"` | Nova cotação: `quoted`, **R$ 179,25** | ☐ |
| B4 | `m qa-b2 "obrigado"` | "Sua cotação (R$ 179,25) continua valendo…"; nenhuma chamada nova à `/quote` no trace | ☐ |
| B5 | `m qa-b5 "Tenho 22 anos, carro 2012, CEP 21000-000, inicio em 01/12/2026, plano premium"` | `quoted`, **R$ 1.025,14** (18–24 anos ×1,60, 11–20 anos ×1,45, CEP `21` ×1,30) | ☐ |

## C. Quando a `/quote` falha (o ponto que mais separa)

O circuit breaker abre depois de 5 cotações falhas seguidas e fica 30 s aberto. Entre C2, C3 e C4,
**espere 30 s**, senão a resposta é imediata por causa do circuito (o que também é correto).

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| C1 | Instabilidade padrão (20% de 5xx, 10% lentas): repita B1 com 10 ids diferentes (`qa-c1-1`…`qa-c1-10`) | Quase todas `quoted` com R$ 209,90. No trace, `quote_attempt` com `http_5xx` ou `ReadTimeout` seguido de `ok` com o mesmo `request_id`. Se uma esgotar as tentativas: `handed_off` / `quote_unavailable`, **sem preço** | ☐ |
| C2 | API sempre falhando: `QUOTE_FAILURE_RATE=1 docker compose up -d quote-api` (PowerShell: `$env:QUOTE_FAILURE_RATE="1"; docker compose up -d quote-api`). Mande B1 com 6 ids diferentes | Cada uma: `handed_off`, `quote_unavailable`, `price: null`, texto "sistema de cotação está instável… não quero te passar um valor errado", **nenhum "R$"**. As 5 primeiras levam ~3 s (4 tentativas); a 6ª responde na hora (`outcome: circuit_open` no trace) | ☐ |
| C3 | API lenta: `QUOTE_FAILURE_RATE=0 QUOTE_SLOW_RATE=1 docker compose up -d quote-api` (PowerShell: `$env:QUOTE_FAILURE_RATE="0"; $env:QUOTE_SLOW_RATE="1"; ...`). Espere 30 s e mande B1 | Resposta em **~15 s** (deadline), `quote_unavailable`, sem preço; tentativas `ReadTimeout` no trace | ☐ |
| C4 | API fora do ar: `docker compose stop quote-api`, espere 30 s, mande B1 | `quote_unavailable` em ~3 s, sem preço; `ConnectError` no trace | ☐ |
| C5 | Volta ao normal: `docker compose up -d quote-api` (no PowerShell, antes: `Remove-Item Env:QUOTE_*`). Espere 30 s e mande B1 com id novo | `quoted` de novo | ☐ |
| C6 | Depois do handoff por falha, na mesma conversa de C2: `m qa-c2-1 "e agora?"` | "Seu atendimento já foi encaminhado…"; o bot não tenta cotar de novo | ☐ |

## D. Regras de negócio e dados inválidos

| # | Mensagem | Esperado | ✓ |
|---|---|---|---|
| D1 | `m qa-d1 "Tenho 80 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027, plano completo"` | `handed_off`, `quote_refused`, texto com o motivo da API "Idade acima do limite de aceitacao (75 anos)" | ☐ |
| D2 | `m qa-d2 "Tenho 40 anos, carro 1998, CEP 01310-100, inicio em 15/03/2027, plano completo"` | `quote_refused`, "Veiculo com mais de 20 anos nao e aceito" | ☐ |
| D3 | `m qa-d3 "Tenho 17 anos, carro 2020, CEP 01310-100, inicio em 15/03/2027, plano essencial"` | `quote_refused`, "Idade fora das faixas aceitas" | ☐ |
| D4 | `m qa-d4 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/07/2026, plano completo"` e depois `m qa-d4 "15/03/2027"` | 1ª: `collecting`, "A vigência não pode começar no passado…", **sem cotação**. 2ª: `quoted` | ☐ |
| D5 | `m qa-d5 "Tenho 35 anos, carro 2031, CEP 01310-100, inicio em 15/03/2027, plano completo"` e depois `m qa-d5 "2021"` | 1ª: `collecting`, "O ano do veículo informado está no futuro…". 2ª: `quoted` | ☐ |
| D6 | `m qa-d6 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027. Qual a diferenca entre essencial e completo?"` | `collecting`, "Falta só o plano desejado…" (plano ambíguo não é escolhido pelo lead) | ☐ |
| D7 | `m qa-d7 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio amanha, plano essencial"` | `quoted`, data de início = amanhã (veja `data_inicio` no evento `slots`) | ☐ |

## E. Critérios de handoff (explícitos e defensáveis?)

| # | Mensagens | Esperado | ✓ |
|---|---|---|---|
| E1 | `m qa-e1 "quero falar com um atendente"` | `handed_off`, `user_request` | ☐ |
|    | `m qa-e1 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027, plano completo"` | Continua `handed_off`, "Seu atendimento já foi encaminhado…", **sem cotar** | ☐ |
| E2 | `m qa-e2 "isso e um absurdo, vou no procon"` | `complaint` | ☐ |
| E3 | `m qa-e3 "bati o carro, preciso acionar o seguro"` | `out_of_scope` | ☐ |
| E4 | `m qa-e4 "quero a segunda via do boleto"` | `out_of_scope` | ☐ |
| E5 | `m qa-e5 "oi"`, `m qa-e5 "hmm"`, `m qa-e5 "nao sei"`, `m qa-e5 "talvez"` | As três primeiras `collecting`; a 4ª `handed_off`, `no_progress` | ☐ |
| E6 | Veja o evento `handoff` no trace de qualquer um acima | Leva `reason` e `collected` (dados já coletados, CEP mascarado) para o humano não recomeçar do zero | ☐ |

## F. Rastreabilidade (dá pra rastrear o que aconteceu?)

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| F1 | `m qa-f1 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 15/03/2027, plano premium" wamid-1` duas vezes | As duas respostas idênticas (mesmo `quote_id`); no trace, **um** `quote_ok` só (reenvio do webhook não recota) | ☐ |
| F2 | `docker compose logs agent --no-log-prefix \| grep qa-f1` | Uma linha JSON por evento: `message_in`, `slots`, `quote_attempt`, `quote_ok`, `message_out`; todas com `ts`, `conversation_id` e `message_id` = `wamid-1` | ☐ |
| F3 | Compare `request_id` dos `quote_attempt` com o `quote_id` da resposta | Iguais (também vão para a API no header `X-Request-ID`) | ☐ |

## G. Dados sensíveis (LGPD)

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| G1 | `m qa-g1 "meu cpf e 123.456.789-09, email joao@exemplo.com, tel (11) 98888-7777, placa ABC1D23"` | Resposta normal (`collecting`) | ☐ |
| G2 | `docker compose logs agent --no-log-prefix \| grep qa-g1` | Aparecem `[CPF]`, `[EMAIL]`, `[TELEFONE]`, `[PLACA]`; **nenhum** dado real | ☐ |
| G3 | Trace de B1 | CEP como `[CEP]` no texto e `01310-***` nos `slots` | ☐ |

## H. Robustez da API do agente

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| H1 | `m qa-h1 ""` (texto vazio) | HTTP 422 (validação), agente não quebra | ☐ |
| H2 | `curl -s -X POST localhost:8080/messages -H 'content-type: application/json' -d '{"text":"oi"}'` | HTTP 422 (`conversation_id` obrigatório) | ☐ |
| H3 | `docker compose ps` depois de todo o roteiro | `agent` continua `healthy`, sem restart | ☐ |

## I. Extrator LLM (opcional, precisa de chave)

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| I1 | Ponha `ANTHROPIC_API_KEY=...` no `.env`, `docker compose up -d agent` e mande `m qa-i1 "Nasci em 1990, tenho um Onix 2021 e moro no CEP 01310-100; quero o completo a partir de 15/03/2027"` | O LLM extrai os campos; `quoted`. O preço continua vindo só da API | ☐ |
| I2 | Com uma chave inválida, repita B1 | Cai no extrator regex e cota normalmente (falha do LLM não derruba o agente) | ☐ |

## K. Mudança de catálogo ao vivo

Mostra que plano novo, preço novo e plano removido **não precisam de deploy do agente** (detalhes em
[`EVOLUCAO.md`](EVOLUCAO.md)). A quote-service relê `data/plans.json` a cada requisição. Antes,
ponha `PLANS_CACHE_TTL_S=5` no `.env` e rode `docker compose up -d agent` (assim o agente vê a
mudança em 5 s; o padrão é 300 s).

| # | Passo | Esperado | ✓ |
|---|---|---|---|
| K1 | `m qa-k1 "oi"` | Lista Essencial, Completo, Premium | ☐ |
| K2 | Adicione o plano Ouro: `docker compose exec quote-api python -c "import json,pathlib as p; f=p.Path('data/plans.json'); d=json.loads(f.read_text()); d['planos'].append({'id':'ouro','nome':'Ouro','base_mensal':499.9,'franquia':1000,'coberturas':['colisao','roubo','furto','terceiros','vidros','carro_reserva','assistencia_24h']}); f.write_text(json.dumps(d))"`, espere 5 s e mande `m qa-k2 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 01/03/2027, plano ouro"` | `quoted`, **R$ 499,90**, franquia R$ 1.000 | ☐ |
| K3 | `m qa-k3 "Tenho 35 anos, carro 2022, CEP 01310-100, inicio em 01/03/2027"` | "Falta só o plano desejado (Essencial, Completo, Premium, Ouro)" | ☐ |
| K4 | Remova o Premium: `docker compose exec quote-api python -c "import json,pathlib as p; f=p.Path('data/plans.json'); d=json.loads(f.read_text()); d['planos']=[x for x in d['planos'] if x['id']!='premium']; f.write_text(json.dumps(d))"` e, **sem esperar**, `m qa-k3 "premium"` | `collecting`, **sem** ir para humano. Dentro dos 5 s de cache: "O plano premium não está mais disponível. Falta só o plano desejado (Essencial, Completo, Ouro)" (a API recusou e o agente recarregou o catálogo). Depois disso o Premium já sumiu da lista e o agente só pergunta de novo entre Essencial, Completo e Ouro | ☐ |
| K5 | `m qa-k3 "completo"` | `quoted`, R$ 209,90 | ☐ |
| K6 | Volte ao catálogo original: `docker compose up -d --force-recreate quote-api` e tire `PLANS_CACHE_TTL_S` do `.env` | `/planos` com os 3 planos originais | ☐ |

Ao terminar: `docker compose down`.

## J. Checklist de entrega do desafio

| Item pedido no enunciado | Onde | ✓ |
|---|---|---|
| Agente de ponta a ponta: conversa → qualifica → cota → decide | Seções B, D, E | ☐ |
| Não trava nem inventa preço quando a infra falha | Seção C | ☐ |
| Critério de handoff claro | `app/docs/DECISIONS.md` §3 e seção E | ☐ |
| Rastreabilidade (id e status de cada mensagem/cotação) | Seção F | ☐ |
| Cuidado com dados sensíveis | Seção G; `dataset/` fora do repo público | ☐ |
| Repositório **público** no GitHub | Configuração do repo | ☐ |
| README com como rodar e decisões | `README.md` (bloco Solução), `app/README.md`, `app/docs/DECISIONS.md` | ☐ |
| Log de uma execução completa com a cotação saindo | `app/docs/execution-log.md` | ☐ |
| **Conversas com as IAs exportadas** em `ai-logs/`, sem segredos | `ai-logs/` | ☐ |
| Nenhum segredo commitado (`.env`, chaves) | `git ls-files \| grep -i env` só mostra `.env.example` | ☐ |
