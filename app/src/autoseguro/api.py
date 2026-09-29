"""API HTTP: o canal (WhatsApp/Twilio/Meta) chama POST /messages a cada mensagem do lead."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .agent import Agent
from .bootstrap import build_agent
from .config import Settings
from .models import Reply


class MessageIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    message_id: str | None = Field(default=None, max_length=128, description="Id de idempotência")


def create_app(agent: Agent | None = None) -> FastAPI:
    agent = agent or build_agent(Settings.from_env())
    app = FastAPI(title="AutoSeguro Agent", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/messages", response_model=Reply)
    def post_message(body: MessageIn) -> Reply:
        return agent.handle(body.conversation_id, body.text, body.message_id)

    return app
