.PHONY: setup models dev simulate test

setup:
	pip install -e ".[dev]"

models:
	python3 scripts/download_models.py

dev:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

simulate:
	python3 scripts/simulate_stream.py

test:
	pytest -v
