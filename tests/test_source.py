import json
from datetime import date
from unittest.mock import patch

from weather_pipeline.source import fetch_weather


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps({"latitude": 48.8, "timezone": "Europe/Paris"}).encode()


def test_fetch_builds_archive_request():
    with patch("weather_pipeline.source.urlopen", return_value=FakeResponse()) as urlopen:
        payload, url = fetch_weather(
            48.8, 2.3, "Europe/Paris", date(2025, 1, 1), date(2025, 1, 7)
        )
    assert payload["timezone"] == "Europe/Paris"
    assert "archive-api.open-meteo.com" in url
    assert "start_date=2025-01-01" in url
    urlopen.assert_called_once()
