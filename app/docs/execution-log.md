# Log de execução completa

Conversa de ponta a ponta contra a **`quote-service` oficial**, dentro da stack do compose
(`docker compose exec agent python -m autoseguro.cli --demo`), com `QUOTE_FAILURE_RATE=0.5` para
forçar instabilidade. Na cotação, a 1ª tentativa recebeu `503`; o cliente refez com backoff e a 2ª
tentativa (`attempt: 2`) retornou `200`. O `request_id` liga as tentativas ao `quote_id` da resposta,
e o CEP aparece mascarado no trace. O primeiro pagamento proporcional (25 de 31 dias, início em
07/10) e a carência de 30 dias vieram da API, não do agente.

Para reproduzir: `QUOTE_FAILURE_RATE=0.5 docker compose up -d quote-api` e o comando acima (as linhas
JSON do trace saem no mesmo terminal, intercaladas com a conversa). Cenários de falha total, lentidão e recusa estão em
[`QA.md`](QA.md).

## Conversa

```text
Lead   > Oi, quero cotar o seguro do meu carro
Agente > Olá! Sou o assistente da AutoSeguro e vou cotar o seguro do seu veículo. Para cotar, me informe:
- sua idade
- o ano do veículo
- seu CEP
- a data de início da vigência (dd/mm/aaaa)
- o plano desejado (Essencial, Completo, Premium)
[stage=collecting]

Lead   > Tenho 35 anos, o carro é 2022 e meu CEP é 01310-100
Agente > Para cotar, me informe:
- a data de início da vigência (dd/mm/aaaa)
- o plano desejado (Essencial, Completo, Premium)
[stage=collecting]

Lead   > Quero o plano completo, começando em 07/10/2026
Agente > Cotação do plano Completo: R$ 209,90 por mês.
Franquia: R$ 3.000,00.
Coberturas: colisao, roubo, furto, terceiros, vidros.
Carência: roubo e furto só valem após 30 dias do início da vigência.
Como a vigência não começa no dia 1º, o primeiro pagamento é proporcional: R$ 169,27 (25 de 31 dias). Os demais meses são integrais.
Código da cotação: db776007.
Quer simular outra opção? É só me dizer o que muda (ex.: outro plano).
[stage=quoted]
```

## Trace (JSONL; campo `text` omitido por brevidade)

```json
{"ts": "2026-09-30T18:26:28.577+00:00", "event": "message_in", "conversation_id": "cli-51a8c1c2", "message_id": "c8b86d33bfa141899ac1db79dd512541"}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "slots", "conversation_id": "cli-51a8c1c2", "message_id": "c8b86d33bfa141899ac1db79dd512541", "slots": {"plano_id": null, "idade": null, "veiculo_ano": null, "cep": null, "data_inicio": null}, "changed": 0, "invalid": []}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "message_out", "conversation_id": "cli-51a8c1c2", "message_id": "c8b86d33bfa141899ac1db79dd512541", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "message_in", "conversation_id": "cli-51a8c1c2", "message_id": "b4dcd5de4c0c4d67bb480fd49297b4e8"}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "slots", "conversation_id": "cli-51a8c1c2", "message_id": "b4dcd5de4c0c4d67bb480fd49297b4e8", "slots": {"plano_id": null, "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": null}, "changed": 3, "invalid": []}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "message_out", "conversation_id": "cli-51a8c1c2", "message_id": "b4dcd5de4c0c4d67bb480fd49297b4e8", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "message_in", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc"}
{"ts": "2026-09-30T18:26:28.583+00:00", "event": "slots", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc", "slots": {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": "2026-10-07"}, "changed": 2, "invalid": []}
{"ts": "2026-09-30T18:26:28.585+00:00", "event": "quote_attempt", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc", "request_id": "db77600741bd442f8ce3b3ecb931bc0c", "attempt": 1, "outcome": "http_503", "status": 503, "latency_ms": 2}
{"ts": "2026-09-30T18:26:29.098+00:00", "event": "quote_attempt", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc", "request_id": "db77600741bd442f8ce3b3ecb931bc0c", "attempt": 2, "outcome": "ok", "status": 200, "latency_ms": 3}
{"ts": "2026-09-30T18:26:29.098+00:00", "event": "quote_ok", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc", "request_id": "db77600741bd442f8ce3b3ecb931bc0c", "price": 209.9}
{"ts": "2026-09-30T18:26:29.099+00:00", "event": "message_out", "conversation_id": "cli-51a8c1c2", "message_id": "3f9a125288c544d19a6b34b5804daadc", "stage": "quoted", "handoff_reason": null, "quote_id": "db77600741bd442f8ce3b3ecb931bc0c"}
```
