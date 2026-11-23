"""Basic data quality checks applied before writing to the database."""

from .transform import DailyWeather


class QualityError(ValueError):
    """Raised when one or more data quality checks fail."""


def validate(records: list[DailyWeather]) -> None:
    errors = []
    if not records:
        errors.append("aucune observation reçue")
    dates = [record.observation_date for record in records]
    if len(dates) != len(set(dates)):
        errors.append("dates dupliquées")

    for row in records:
        label = row.observation_date.isoformat()
        if not -90 <= row.temperature_min <= 60:
            errors.append(f"température minimale hors plage le {label}")
        if not -90 <= row.temperature_max <= 60:
            errors.append(f"température maximale hors plage le {label}")
        if row.temperature_min > row.temperature_max:
            errors.append(f"min supérieur au max le {label}")
        if not 0 <= row.precipitation_mm <= 2000:
            errors.append(f"précipitations hors plage le {label}")
        if not 0 <= row.wind_speed_max_kmh <= 400:
            errors.append(f"vitesse du vent hors plage le {label}")
    if errors:
        raise QualityError("; ".join(errors))
