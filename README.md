# Weather Data Pipeline — Open-Meteo to PostgreSQL

This is a small personal project I built to practise the basics of a data pipeline: fetching public weather data, transforming and checking it, then storing it in PostgreSQL.

It is an early, local-only version. The pipeline runs **only when started manually**; there is no daily schedule, cloud deployment, or orchestration tool.

## What it does

1. Fetches daily archive data from the public [Open-Meteo Archive API](https://open-meteo.com/en/docs/historical-weather-api). The request ends five days in the past to reduce the chance of receiving incomplete recent data.
2. Converts the JSON response into typed daily records for maximum and minimum temperature, precipitation, and maximum wind speed.
3. Checks that values are present, dates are unique, measurements are within broad ranges, and minimum temperature does not exceed maximum temperature.
4. Stores the original response in `raw_weather_payloads` and the cleaned records in `daily_weather`.

The daily table uses a location-and-date key, so rerunning the same date range updates existing records instead of duplicating them. Each run still adds a raw response for traceability. Database writes for one batch are transactional.

For a longer explanation of the files and design choices, see the [PDF guide](docs/GUIDE_COMPLET_PIPELINE_METEO.pdf) or its [Markdown source](docs/GUIDE_COMPLET.md). The guide is currently in French.

## Run with Docker Compose

Requirements: Docker Engine and the Docker Compose plugin.

The PostgreSQL port is bound to `127.0.0.1`. The username and password in `compose.yaml` are for local development only; do not reuse them for a database exposed to the internet.

```bash
# Start PostgreSQL, then run the pipeline once
docker compose up -d db
docker compose --profile run run --build --rm pipeline
```

By default, this loads seven available archive days for Paris. The database remains available on `localhost:5432` in the `postgres_data` volume. To inspect the latest rows:

```bash
docker compose exec db psql -U weather -d weather \
  -c 'SELECT * FROM daily_weather ORDER BY observation_date DESC LIMIT 10;'
```

`docker compose down` stops the services and keeps the database volume. `docker compose down -v` also deletes that volume and its data.

## Run directly with Python

Requirements: Python 3.12 or newer and a reachable PostgreSQL instance.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m weather_pipeline --help
python -m weather_pipeline
```

The defaults are Paris, the `Europe/Paris` timezone, seven days, and PostgreSQL at `localhost:5432`. Options can be passed directly; no `.env` file is used:

```bash
python -m weather_pipeline \
  --latitude 45.7640 --longitude 4.8357 --timezone Europe/Paris \
  --days 14 \
  --database-url postgresql://weather:weather@localhost:5432/weather
```

`--days` accepts values from 1 to 90. Each manual run calculates a rolling date range; run it again when you want to refresh the data. It will not run by itself.

## Tests

Unit tests do not need network access or PostgreSQL:

```bash
python -m pytest -q
```

The Docker Compose test profile also runs a PostgreSQL integration test. It writes a temporary observation, checks the upsert, then removes the test data:

```bash
docker compose --profile test run --build --rm tests
```

It is still a good idea to use a test database rather than a database containing important data.

## Main files

| File | Purpose |
|---|---|
| `weather_pipeline/__main__.py` | Command-line options and manual entry point |
| `weather_pipeline/pipeline.py` | Runs the pipeline steps once |
| `weather_pipeline/source.py` | Open-Meteo HTTP request and network retries |
| `weather_pipeline/transform.py` | Converts JSON into typed records |
| `weather_pipeline/quality.py` | Data quality checks |
| `weather_pipeline/db.py` | PostgreSQL schema setup and transactional writes |
| `weather_pipeline/schema.sql` | Tables, keys, constraints, and index |
| `compose.yaml` | PostgreSQL, one-shot pipeline, and test services |
| `Dockerfile`, `Dockerfile.test` | Application and test images |
| `docs/` | Longer project guide in Markdown and PDF |

## What I practised and what I would improve

This project gave me practice with Python HTTP requests, PostgreSQL tables and transactions, basic tests, and running services locally with Docker Compose. It is still a learning project. I would next improve schema migrations and error tracking, and only consider scheduling or cloud deployment if the local pipeline proves reliable and there is a real need for them.

## License

No license is included yet. The code is visible, but reuse is not explicitly permitted.
