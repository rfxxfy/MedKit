.PHONY: dev test check build demo

dev:
	bash scripts/dev.sh

test:
	.venv/bin/pytest

check:
	.venv/bin/ruff check backend
	.venv/bin/mypy backend/app
	npm run check --prefix frontend

build:
	npm run build --prefix frontend

demo:
	PYTHONPATH=backend .venv/bin/python -m app.cli seed-demo
