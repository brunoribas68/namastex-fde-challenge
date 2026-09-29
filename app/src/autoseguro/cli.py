"""CLI: chat interativo ou `--demo` (conversa roteirizada para gerar o log de execução)."""

from __future__ import annotations

import argparse
import uuid
from datetime import date, timedelta

from .bootstrap import build_agent
from .config import Settings


def demo_script(today: date) -> list[str]:
    start = (today + timedelta(days=7)).strftime("%d/%m/%Y")
    return [
        "Oi, quero cotar o seguro do meu carro",
        "Tenho 35 anos, o carro é 2022 e meu CEP é 01310-100",
        f"Quero o plano completo, começando em {start}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Conversa com o agente AutoSeguro")
    parser.add_argument("--demo", action="store_true", help="roda uma conversa roteirizada")
    args = parser.parse_args()

    agent = build_agent(Settings.from_env())
    conversation_id = f"cli-{uuid.uuid4().hex[:8]}"

    def turn(text: str) -> None:
        reply = agent.handle(conversation_id, text)
        print(f"Lead   > {text}\nAgente > {reply.text}\n[stage={reply.stage}]\n")

    if args.demo:
        for text in demo_script(date.today()):
            turn(text)
        return
    print("Digite suas mensagens (Ctrl+D para sair).\n")
    try:
        while True:
            turn(input("Lead   > "))
    except EOFError:
        pass


if __name__ == "__main__":
    main()
