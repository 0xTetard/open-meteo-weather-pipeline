"""PostgreSQL schema setup and transactional batch persistence."""

import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .transform import DailyWeather

SCHEMA = Path(__file__).with_name("schema.sql")


def initialize(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(SCHEMA.read_text(encoding="utf-8"), prepare=False)


def store_batch(
    database_url: str,
    payload: dict,
    source_url: str,
    records: list[DailyWeather],
) -> None:
    """Store the raw response and upsert observations in one transaction."""
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO raw_weather_payloads (source_url, payload) VALUES (%s, %s) "
                "RETURNING id",
                (source_url, Jsonb(payload, dumps=lambda value: json.dumps(value))),
            )
            payload_id = cursor.fetchone()[0]
            cursor.executemany(
                """INSERT INTO daily_weather (
                       observation_date, latitude, longitude, timezone,
                       temperature_max_c, temperature_min_c,
                       precipitation_mm, wind_speed_max_kmh, source_payload_id
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (latitude, longitude, observation_date) DO UPDATE SET
                       timezone = EXCLUDED.timezone,
                       temperature_max_c = EXCLUDED.temperature_max_c,
                       temperature_min_c = EXCLUDED.temperature_min_c,
                       precipitation_mm = EXCLUDED.precipitation_mm,
                       wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
                       source_payload_id = EXCLUDED.source_payload_id,
                       loaded_at = now()""",
                [
                    (
                        row.observation_date,
                        row.latitude,
                        row.longitude,
                        row.timezone,
                        row.temperature_max,
                        row.temperature_min,
                        row.precipitation_mm,
                        row.wind_speed_max_kmh,
                        payload_id,
                    )
                    for row in records
                ],
            )
