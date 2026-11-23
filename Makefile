.PHONY: test run up down

test:
	python -m pytest -q

run:
	docker compose up -d db
	docker compose --profile run run --build --rm pipeline

up:
	docker compose up -d db

down:
	docker compose down
