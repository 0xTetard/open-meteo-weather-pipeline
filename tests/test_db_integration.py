import os
from datetime import date
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from weather_pipeline.db import initialize, store_batch
from weather_pipeline.transform import DailyWeather

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="définir TEST_DATABASE_URL pour PostgreSQL")


def test_schema_and_idempotent_upsert():
    initialize(DATABASE_URL)
    source_url = f"https://example.test/integration/{uuid4()}"
    row = DailyWeather(
        observation_date=date(2000, 1, 1),
        latitude=0.12345,
        longitude=0.54321,
        timezone="UTC",
        temperature_max=20.0,
        temperature_min=10.0,
        precipitation_mm=0.0,
        wind_speed_max_kmh=5.0,
    )
    try:
        store_batch(DATABASE_URL, {"test": True}, source_url, [row])
        updated = replace(row, temperature_max=21.0)
        store_batch(DATABASE_URL, {"test": True}, source_url, [updated])

        with psycopg.connect(DATABASE_URL) as connection:
            count, maximum = connection.execute(
                "SELECT count(*), max(temperature_max_c) FROM daily_weather "
                "WHERE latitude = %s AND longitude = %s AND observation_date = %s",
                (row.latitude, row.longitude, row.observation_date),
            ).fetchone()
        assert count == 1
        assert float(maximum) == 21.0
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM daily_weather WHERE latitude = %s AND longitude = %s "
                "AND observation_date = %s",
                (row.latitude, row.longitude, row.observation_date),
            )
            connection.execute("DELETE FROM raw_weather_payloads WHERE source_url = %s", (source_url,))
