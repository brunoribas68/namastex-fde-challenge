.PHONY: install test lint fmt run demo docker
install: ; uv sync
test:    ; uv run pytest --cov --cov-fail-under=85
lint:    ; uv run ruff check . && uv run ruff format --check .
fmt:     ; uv run ruff check --fix . && uv run ruff format .
run:     ; uv run uvicorn autoseguro.api:create_app --factory --port 8080 --reload
demo:    ; uv run python -m autoseguro.cli --demo
docker:  ; docker compose up --build
