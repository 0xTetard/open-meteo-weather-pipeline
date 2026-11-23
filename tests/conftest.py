import pytest


@pytest.fixture
def sample_payload():
    return {
        "latitude": 48.86,
        "longitude": 2.35,
        "timezone": "Europe/Paris",
        "daily": {
            "time": ["2025-01-01", "2025-01-02"],
            "temperature_2m_max": [8.1, 7.0],
            "temperature_2m_min": [2.0, 1.5],
            "precipitation_sum": [0.0, 1.2],
            "wind_speed_10m_max": [15.0, 22.0],
        },
    }
