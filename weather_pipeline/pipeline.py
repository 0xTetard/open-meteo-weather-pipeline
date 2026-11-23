"""Run the ingestion, transformation, validation, and loading steps once."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from .quality import validate
from .source import fetch_weather
from .transform import transform

LOGGER = logging.getLogger(__name__)


def run(
    database_url: str,
    latitude: float,
    longitude: float,
    timezone: str,
    days_to_load: int,
) -> int:
    # Leave a few days for the archive data to become available.
    end_date = datetime.now(ZoneInfo(timezone)).date() - timedelta(days=5)
    start_date = end_date - timedelta(days=days_to_load - 1)
    LOGGER.info(
        "Démarrage du pipeline pour %s, période %s–%s",
        timezone,
        start_date,
        end_date,
    )

    payload, source_url = fetch_weather(
        latitude,
        longitude,
        timezone,
        start_date,
        end_date,
    )
    records = transform(payload)
    validate(records)
    db.initialize(database_url)
    db.store_batch(database_url, payload, source_url, records)
    LOGGER.info("Pipeline terminé : %s observations chargées", len(records))
    return len(records)
