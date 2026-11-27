from __future__ import annotations

from datetime import datetime, time

import pytest

from utils.validators import (
    InputValidationError,
    parse_hours_range,
    parse_local_datetime,
    parse_minutes_range,
    parse_time,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("9:05", time(9, 5)), ("09.30", time(9, 30)), (" 23:59 ", time(23, 59)), ("0:00", time(0))],
)
def test_parse_time(raw: str, expected: time) -> None:
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw", ["24:00", "9", "12:60", "ab:cd", ""])
def test_parse_time_rejects(raw: str) -> None:
    with pytest.raises(InputValidationError):
        parse_time(raw)


def test_parse_local_datetime() -> None:
    assert parse_local_datetime("28.11.2026 09:30") == datetime(2026, 11, 28, 9, 30)  # noqa: DTZ001
    assert parse_local_datetime("1/2/2027 7:05") == datetime(2027, 2, 1, 7, 5)  # noqa: DTZ001
    for bad in ("31.02.2026 10:00", "2026-11-28 09:30", "28.11.2026"):
        with pytest.raises(InputValidationError):
            parse_local_datetime(bad)


def test_parse_minutes_range() -> None:
    assert parse_minutes_range("30-90") == (1800, 5400)
    assert parse_minutes_range(" 60 ") == (3600, 3600)
    assert parse_minutes_range("10 – 20") == (600, 1200)
    for bad in ("0-5", "90-30", "abc", "1-20000"):
        with pytest.raises(InputValidationError):
            parse_minutes_range(bad)


def test_parse_hours_range() -> None:
    assert parse_hours_range("09:00-22:00") == (time(9), time(22))
    assert parse_hours_range("20:00 - 02:00") == (time(20), time(2))
    assert parse_hours_range("0") == (None, None)
    assert parse_hours_range("10:00-10:00") == (None, None)
    with pytest.raises(InputValidationError):
        parse_hours_range("09:00")
