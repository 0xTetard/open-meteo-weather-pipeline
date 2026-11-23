from dataclasses import replace

import pytest

from weather_pipeline.quality import QualityError, validate
from weather_pipeline.transform import TransformationError, transform


def test_transform_maps_api_fields_to_typed_rows(sample_payload):
    rows = transform(sample_payload)
    assert len(rows) == 2
    assert rows[0].observation_date.isoformat() == "2025-01-01"
    assert rows[0].temperature_min == 2.0
    assert rows[1].precipitation_mm == 1.2


def test_transform_rejects_misaligned_series(sample_payload):
    sample_payload["daily"]["precipitation_sum"].pop()
    with pytest.raises(TransformationError, match="longueurs différentes"):
        transform(sample_payload)


def test_transform_rejects_null_values(sample_payload):
    sample_payload["daily"]["temperature_2m_max"][0] = None
    with pytest.raises(TransformationError, match="invalide"):
        transform(sample_payload)


def test_quality_accepts_valid_rows(sample_payload):
    validate(transform(sample_payload))


def test_quality_rejects_impossible_temperature_range(sample_payload):
    row = transform(sample_payload)[0]
    with pytest.raises(QualityError, match="min supérieur au max"):
        validate([replace(row, temperature_min=10.0)])


def test_quality_rejects_empty_batch():
    with pytest.raises(QualityError, match="aucune observation"):
        validate([])
