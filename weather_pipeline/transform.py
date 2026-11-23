"""Convert Open-Meteo JSON data into typed daily records."""

from dataclasses import dataclass
from datetime import date
import math


class TransformationError(ValueError):
    """Raised when the source payload cannot be transformed."""


@dataclass(frozen=True)
class DailyWeather:
    observation_date: date
    latitude: float
    longitude: float
    timezone: str
    temperature_max: float
    temperature_min: float
    precipitation_mm: float
    wind_speed_max_kmh: float


def transform(payload: dict) -> list[DailyWeather]:
    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
        timezone = str(payload["timezone"])
        daily = payload["daily"]
        columns = {
            "dates": daily["time"],
            "temperature_max": daily["temperature_2m_max"],
            "temperature_min": daily["temperature_2m_min"],
            "precipitation_mm": daily["precipitation_sum"],
            "wind_speed_max_kmh": daily["wind_speed_10m_max"],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise TransformationError(f"Champs Open-Meteo manquants ou invalides : {exc}") from exc

    lengths = {len(values) for values in columns.values() if isinstance(values, list)}
    if any(not isinstance(values, list) for values in columns.values()) or len(lengths) != 1:
        raise TransformationError("Les séries quotidiennes sont absentes ou de longueurs différentes")

    records = []
    for index, day in enumerate(columns["dates"]):
        try:
            values = {
                name: float(series[index])
                for name, series in columns.items()
                if name != "dates"
            }
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError("valeur non finie")
            records.append(
                DailyWeather(
                    observation_date=date.fromisoformat(day),
                    latitude=latitude,
                    longitude=longitude,
                    timezone=timezone,
                    **values,
                )
            )
        except (TypeError, ValueError) as exc:
            raise TransformationError(f"Donnée quotidienne invalide pour {day!r}: {exc}") from exc
    return records
