# Log de execução completa

Conversa de ponta a ponta contra a **`quote-service` oficial** (`make demo`), rodada com
`QUOTE_FAILURE_RATE=0.5` para forçar instabilidade. Na cotação, a 1ª tentativa recebeu `503`; o
cliente refez com backoff e a 2ª tentativa (`attempt: 2`) retornou `200`. O `request_id` liga as
tentativas ao `quote_id` da resposta, e o CEP aparece mascarado no trace. O primeiro pagamento
proporcional (26 de 31 dias, início em 06/10) e a carência de 30 dias vieram da API, não do agente.

## Conversa

```text
Lead   > Oi, quero cotar o seguro do meu carro
Agente > Olá! Sou o assistente da AutoSeguro e vou cotar o seguro do seu veículo. Para cotar, me informe:
- sua idade
- o ano do veículo
- seu CEP
- a data de início da vigência (ex.: 15/07/2026)
- o plano desejado (Essencial, Completo, Premium)
[stage=collecting]

Lead   > Tenho 35 anos, o carro é 2022 e meu CEP é 01310-100
Agente > Para cotar, me informe:
- a data de início da vigência (ex.: 15/07/2026)
- o plano desejado (Essencial, Completo, Premium)
[stage=collecting]

Lead   > Quero o plano completo, começando em 06/10/2026
Agente > Cotação do plano Completo: R$ 209,90 por mês.
Franquia: R$ 3.000,00.
Coberturas: colisao, roubo, furto, terceiros, vidros.
Carência: roubo e furto só valem após 30 dias do início da vigência.
Como a vigência não começa no dia 1º, o primeiro pagamento é proporcional: R$ 176,05 (26 de 31 dias). Os demais meses são integrais.
Código da cotação: f3463779.
Quer simular outra opção? É só me dizer o que muda (ex.: outro plano).
[stage=quoted]
```

## Trace (JSONL; campo `text` omitido por brevidade)

```json
{"ts": "2026-09-29T20:58:34.735+00:00", "event": "message_in", "conversation_id": "cli-f9f50d0b", "message_id": "9d5ab440bdc74995994248fe6cb88626"}
{"ts": "2026-09-29T20:58:34.742+00:00", "event": "slots", "conversation_id": "cli-f9f50d0b", "message_id": "9d5ab440bdc74995994248fe6cb88626", "slots": {"plano_id": null, "idade": null, "veiculo_ano": null, "cep": null, "data_inicio": null}, "changed": 0}
{"ts": "2026-09-29T20:58:34.742+00:00", "event": "message_out", "conversation_id": "cli-f9f50d0b", "message_id": "9d5ab440bdc74995994248fe6cb88626", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-29T20:58:34.743+00:00", "event": "message_in", "conversation_id": "cli-f9f50d0b", "message_id": "c7ffa9f9ea4a4a509250543607f6204e"}
{"ts": "2026-09-29T20:58:34.743+00:00", "event": "slots", "conversation_id": "cli-f9f50d0b", "message_id": "c7ffa9f9ea4a4a509250543607f6204e", "slots": {"plano_id": null, "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": null}, "changed": 3}
{"ts": "2026-09-29T20:58:34.743+00:00", "event": "message_out", "conversation_id": "cli-f9f50d0b", "message_id": "c7ffa9f9ea4a4a509250543607f6204e", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-29T20:58:34.743+00:00", "event": "message_in", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280"}
{"ts": "2026-09-29T20:58:34.743+00:00", "event": "slots", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280", "slots": {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": "2026-10-06"}, "changed": 2}
{"ts": "2026-09-29T20:58:34.745+00:00", "event": "quote_attempt", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280", "request_id": "f3463779a54a41afbf534b920b41fcca", "attempt": 1, "outcome": "http_503", "status": 503, "latency_ms": 2}
{"ts": "2026-09-29T20:58:35.270+00:00", "event": "quote_attempt", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280", "request_id": "f3463779a54a41afbf534b920b41fcca", "attempt": 2, "outcome": "ok", "status": 200, "latency_ms": 3}
{"ts": "2026-09-29T20:58:35.270+00:00", "event": "quote_ok", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280", "request_id": "f3463779a54a41afbf534b920b41fcca", "price": 209.9}
{"ts": "2026-09-29T20:58:35.270+00:00", "event": "message_out", "conversation_id": "cli-f9f50d0b", "message_id": "4619cea0429840b1920088a5c76bc280", "stage": "quoted", "handoff_reason": null, "quote_id": "f3463779a54a41afbf534b920b41fcca"}
```
