.PHONY: install lint test eval security run docker-build docker-up docker-seed clean

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests eval

test:
	pytest --cov --cov-report=term-missing

eval:
	python -m eval.run_eval

security:
	bandit -q -r src -ll
	pip-audit

run:
	RAG_ALLOW_ANONYMOUS=true uvicorn api.asgi:app --reload --app-dir src

docker-build:
	docker build -t company-knowledge-assistant:local .

docker-up:
	docker compose up --build -d

docker-seed:
	docker compose --profile seed run --rm seed

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov chroma_db
