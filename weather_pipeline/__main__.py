import argparse
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .pipeline import run


def _latitude(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("doit être un nombre") from exc
    if not -90 <= result <= 90:
        raise argparse.ArgumentTypeError("doit être comprise entre -90 et 90")
    return result


def _longitude(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("doit être un nombre") from exc
    if not -180 <= result <= 180:
        raise argparse.ArgumentTypeError("doit être comprise entre -180 et 180")
    return result


def _days(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("doit être un entier") from exc
    if not 1 <= result <= 90:
        raise argparse.ArgumentTypeError("doit être compris entre 1 et 90")
    return result


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"fuseau horaire inconnu : {value}") from exc
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline météo local vers PostgreSQL")
    parser.add_argument(
        "--database-url",
        default="postgresql://weather:weather@localhost:5432/weather",
        help="URL de connexion PostgreSQL",
    )
    parser.add_argument("--latitude", type=_latitude, default=48.8566)
    parser.add_argument("--longitude", type=_longitude, default=2.3522)
    parser.add_argument("--timezone", type=_timezone, default="Europe/Paris")
    parser.add_argument("--days", type=_days, default=7, help="Nombre de jours à charger (1 à 90)")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    run(
        database_url=args.database_url,
        latitude=args.latitude,
        longitude=args.longitude,
        timezone=args.timezone,
        days_to_load=args.days,
    )


if __name__ == "__main__":
    main()
