import pytest

from weather_pipeline.__main__ import build_parser


def test_cli_defaults():
    args = build_parser().parse_args([])
    assert args.latitude == 48.8566
    assert args.longitude == 2.3522
    assert args.timezone == "Europe/Paris"
    assert args.days == 7


@pytest.mark.parametrize(
    ("option", "value"),
    [("--latitude", "91"), ("--longitude", "181"), ("--days", "0"), ("--timezone", "Not/AZone")],
)
def test_cli_rejects_invalid_options(option, value):
    with pytest.raises(SystemExit):
        build_parser().parse_args([option, value])
