import io
import json

import pytest

from autoseguro.tracing import Tracer, redact_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("cpf 123.456.789-09", "cpf [CPF]"),
        ("cpf 12345678909", "cpf [CPF]"),
        ("mail joao@ex.com.br", "mail [EMAIL]"),
        ("tel (41) 99999-1234", "tel [TELEFONE]"),
        ("placa ABC-1D23", "placa [PLACA]"),
        ("cep 01310-100", "cep [CEP]"),
        ("tenho 35 anos, carro 2022", "tenho 35 anos, carro 2022"),
    ],
)
def test_redact_text(raw, expected):
    assert redact_text(raw) == expected


def test_redact_keeps_cep_when_asked():
    assert redact_text("cep 01310-100", mask_cep=False) == "cep 01310-100"


def test_emit_writes_json_line_with_masked_fields():
    buf = io.StringIO()
    Tracer(buf).emit("slots", "c1", "m1", slots={"cep": "01310-100", "idade": 35}, note="a@b.co")
    record = json.loads(buf.getvalue())
    assert record["slots"] == {"cep": "01310-***", "idade": 35}
    assert record["note"] == "[EMAIL]"
    assert {"ts", "event", "conversation_id", "message_id"} <= record.keys()
