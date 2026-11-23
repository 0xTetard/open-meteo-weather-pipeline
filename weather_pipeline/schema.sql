CREATE TABLE IF NOT EXISTS raw_weather_payloads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_url TEXT NOT NULL,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_weather (
    observation_date DATE NOT NULL,
    latitude NUMERIC(8, 5) NOT NULL,
    longitude NUMERIC(8, 5) NOT NULL,
    timezone TEXT NOT NULL,
    temperature_max_c NUMERIC(6, 2) NOT NULL,
    temperature_min_c NUMERIC(6, 2) NOT NULL,
    precipitation_mm NUMERIC(8, 2) NOT NULL,
    wind_speed_max_kmh NUMERIC(7, 2) NOT NULL,
    source_payload_id BIGINT NOT NULL REFERENCES raw_weather_payloads(id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (latitude, longitude, observation_date),
    CHECK (temperature_min_c <= temperature_max_c),
    CHECK (precipitation_mm >= 0),
    CHECK (wind_speed_max_kmh >= 0)
);

CREATE INDEX IF NOT EXISTS idx_daily_weather_date ON daily_weather (observation_date);
