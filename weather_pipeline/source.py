"""Small HTTP client for the Open-Meteo archive API."""

import json
import logging
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_FIELDS = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"
)


def fetch_weather(
    latitude: float,
    longitude: float,
    timezone: str,
    start_date: date,
    end_date: date,
    retries: int = 3,
) -> tuple[dict, str]:
    params = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": DAILY_FIELDS,
            "timezone": timezone,
        }
    )
    url = f"{BASE_URL}?{params}"
    request = Request(url, headers={"User-Agent": "local-weather-data-pipeline/1.0"})

    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, dict):
                raise ValueError("La réponse Open-Meteo doit être un objet JSON")
            if payload.get("error"):
                raise ValueError(f"Erreur Open-Meteo : {payload.get('reason', 'inconnue')}")
            return payload, url
        except HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt == retries:
                raise RuntimeError(f"Open-Meteo a répondu HTTP {exc.code}") from exc
            LOGGER.warning("HTTP %s, nouvel essai %s/%s", exc.code, attempt, retries)
        except (URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError("Impossible de joindre Open-Meteo") from exc
            LOGGER.warning("Erreur réseau, nouvel essai %s/%s : %s", attempt, retries, exc)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Open-Meteo a renvoyé un JSON invalide") from exc
        time.sleep(min(2 ** (attempt - 1), 8))

    raise RuntimeError("Échec inattendu de la récupération Open-Meteo")
