# Log de execução completa

Conversa de ponta a ponta (`make demo`) com a cotação saindo. **Gerada contra o stub instável
`scripts/fake_quote_server.py`**, não contra a `quote-service` oficial: regenere com a API real
(`docker compose up -d quote-service && make demo`) e substitua este arquivo antes de entregar.

Destaque: na cotação, a 1ª tentativa recebeu `503`; o cliente refez com backoff e a 2ª
tentativa (`attempt: 2`) retornou `200`. Todas as linhas compartilham `conversation_id`/`message_id`,
e o `request_id` liga as tentativas ao `quote_id` da resposta. O CEP aparece mascarado.

## Conversa

```text
Lead   > Oi, quero cotar o seguro do meu carro
Agente > Olá! Sou o assistente da AutoSeguro e vou cotar o seguro do seu veículo. Para cotar, me informe:
- sua idade
- o ano do veículo
- seu CEP
- a data de início da vigência (ex.: 15/07/2026)
- o plano desejado (Básico, Completo)
[stage=collecting]

Lead   > Tenho 35 anos, o carro é 2022 e meu CEP é 01310-100
Agente > Para cotar, me informe:
- a data de início da vigência (ex.: 15/07/2026)
- o plano desejado (Básico, Completo)
[stage=collecting]

Lead   > Quero o plano completo, começando em 06/10/2026
Agente > Cotação do plano Completo: R$ 1.500,00.
Código da cotação: e79d7f52.
Quer simular outra opção? É só me dizer o que muda (ex.: outro plano).
[stage=quoted]
```

## Trace (JSONL, campo `text` omitido por brevidade)

```json
{"ts": "2026-09-29T20:22:05.562+00:00", "event": "message_in", "conversation_id": "cli-dc5eb9ee", "message_id": "f7bc0fda3dfb4ef8aa61cb98d8ac6fd5"}
{"ts": "2026-09-29T20:22:05.642+00:00", "event": "slots", "conversation_id": "cli-dc5eb9ee", "message_id": "f7bc0fda3dfb4ef8aa61cb98d8ac6fd5", "slots": {"plano_id": null, "idade": null, "veiculo_ano": null, "cep": null, "data_inicio": null}, "changed": 0}
{"ts": "2026-09-29T20:22:05.642+00:00", "event": "message_out", "conversation_id": "cli-dc5eb9ee", "message_id": "f7bc0fda3dfb4ef8aa61cb98d8ac6fd5", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-29T20:22:05.642+00:00", "event": "message_in", "conversation_id": "cli-dc5eb9ee", "message_id": "18a755a10ac74e709cde9b8951719a06"}
{"ts": "2026-09-29T20:22:05.642+00:00", "event": "slots", "conversation_id": "cli-dc5eb9ee", "message_id": "18a755a10ac74e709cde9b8951719a06", "slots": {"plano_id": null, "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": null}, "changed": 3}
{"ts": "2026-09-29T20:22:05.643+00:00", "event": "message_out", "conversation_id": "cli-dc5eb9ee", "message_id": "18a755a10ac74e709cde9b8951719a06", "stage": "collecting", "handoff_reason": null, "quote_id": null}
{"ts": "2026-09-29T20:22:05.643+00:00", "event": "message_in", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432"}
{"ts": "2026-09-29T20:22:05.643+00:00", "event": "slots", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432", "slots": {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-***", "data_inicio": "2026-10-06"}, "changed": 2}
{"ts": "2026-09-29T20:22:05.646+00:00", "event": "quote_attempt", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432", "request_id": "e79d7f52dfe444c184432bebe51a4db9", "attempt": 1, "outcome": "http_503", "status": 503, "latency_ms": 3}
{"ts": "2026-09-29T20:22:06.207+00:00", "event": "quote_attempt", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432", "request_id": "e79d7f52dfe444c184432bebe51a4db9", "attempt": 2, "outcome": "ok", "status": 200, "latency_ms": 3}
{"ts": "2026-09-29T20:22:06.207+00:00", "event": "quote_ok", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432", "request_id": "e79d7f52dfe444c184432bebe51a4db9", "price": 1500.0}
{"ts": "2026-09-29T20:22:06.207+00:00", "event": "message_out", "conversation_id": "cli-dc5eb9ee", "message_id": "9fb7ef50ec6b4599b53b1f357a3cf432", "stage": "quoted", "handoff_reason": null, "quote_id": "e79d7f52dfe444c184432bebe51a4db9"}
```
