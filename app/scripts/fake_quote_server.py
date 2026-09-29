"""Stub INSTÁVEL da quote-service, só para desenvolvimento local. Use a API oficial no desafio.

uv run python scripts/fake_quote_server.py   # :8000, ~35% de falhas (503/lentidão)
"""

import random
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
PLANS = [{"id": "basico", "nome": "Básico"}, {"id": "completo", "nome": "Completo"}]


class Req(BaseModel):
    plano_id: str
    idade: int
    veiculo_ano: int
    cep: str
    data_inicio: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/planos")
def planos():
    return {"planos": PLANS}


@app.post("/quote")
def quote(req: Req):
    roll = random.random()
    if roll < 0.2:
        raise HTTPException(503, "indisponível")
    if roll < 0.35:
        time.sleep(4)  # excede o timeout do cliente
    if req.veiculo_ano < 2000:
        raise HTTPException(422, "veiculo_ano fora da faixa aceita")
    base = 900 if req.plano_id == "basico" else 1500
    return {"preco": round(base * (1.4 if req.idade < 25 else 1.0), 2)}


if __name__ == "__main__":
    uvicorn.run(app, port=8000)
