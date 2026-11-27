from __future__ import annotations

import random
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from utils.time_utils import (
    ensure_utc,
    format_local,
    is_within_active_hours,
    local_to_utc,
    mask_to_weekdays,
    next_daily_run,
    next_random_run,
    next_weekly_run,
    to_local,
    weekdays_to_mask,
)

TASHKENT = ZoneInfo("Asia/Tashkent")  # UTC+5, DST yo'q
NEW_YORK = ZoneInfo("America/New_York")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


class TestConversions:
    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValueError):
            ensure_utc(datetime(2026, 1, 1))  # noqa: DTZ001

    def test_to_local_tashkent_is_utc_plus_5(self) -> None:
        local = to_local(utc(2026, 1, 1, 0, 0), TASHKENT)
        assert (local.hour, local.utcoffset()) == (5, timedelta(hours=5))

    def test_local_to_utc_roundtrip(self) -> None:
        result = local_to_utc(datetime(2026, 3, 10, 9, 30), TASHKENT)  # noqa: DTZ001
        assert result == utc(2026, 3, 10, 4, 30)
        assert result.tzinfo is UTC

    def test_local_to_utc_rejects_aware(self) -> None:
        with pytest.raises(ValueError):
            local_to_utc(utc(2026, 1, 1), TASHKENT)

    def test_format_local(self) -> None:
        assert format_local(utc(2026, 11, 27, 15, 48), TASHKENT) == "27.11.2026 20:48"


class TestWeekdays:
    def test_mask_roundtrip(self) -> None:
        assert mask_to_weekdays(weekdays_to_mask([0, 2, 4])) == [0, 2, 4]

    def test_empty_and_invalid(self) -> None:
        with pytest.raises(ValueError):
            weekdays_to_mask([])
        with pytest.raises(ValueError):
            weekdays_to_mask([7])
        with pytest.raises(ValueError):
            mask_to_weekdays(0)
        with pytest.raises(ValueError):
            mask_to_weekdays(128)


class TestDailyWeekly:
    def test_daily_later_today(self) -> None:
        # 08:00 Toshkent = 03:00 UTC; 09:00 Toshkent hali kelmagan
        result = next_daily_run(utc(2026, 5, 1, 3, 0), time(9, 0), TASHKENT)
        assert result == utc(2026, 5, 1, 4, 0)

    def test_daily_rolls_to_tomorrow_when_passed(self) -> None:
        result = next_daily_run(utc(2026, 5, 1, 5, 0), time(9, 0), TASHKENT)
        assert result == utc(2026, 5, 2, 4, 0)

    def test_daily_is_strictly_after(self) -> None:
        exact = utc(2026, 5, 1, 4, 0)
        assert next_daily_run(exact, time(9, 0), TASHKENT) == utc(2026, 5, 2, 4, 0)

    def test_daily_across_local_midnight(self) -> None:
        # 2026-05-01 20:00 UTC = 2026-05-02 01:00 Toshkent; 00:30 o'tib ketgan
        result = next_daily_run(utc(2026, 5, 1, 20, 0), time(0, 30), TASHKENT)
        assert result == utc(2026, 5, 2, 19, 30)

    def test_weekly_picks_next_allowed_day(self) -> None:
        # 2026-11-27 juma. Faqat dushanba (0) -> 2026-11-30 10:00 Toshkent
        result = next_weekly_run(
            utc(2026, 11, 27, 12, 0), time(10, 0), weekdays_to_mask([0]), TASHKENT
        )
        assert result == utc(2026, 11, 30, 5, 0)

    def test_weekly_same_day_if_time_not_passed(self) -> None:
        friday_morning = utc(2026, 11, 27, 2, 0)  # 07:00 Toshkent
        result = next_weekly_run(friday_morning, time(10, 0), weekdays_to_mask([4]), TASHKENT)
        assert result == utc(2026, 11, 27, 5, 0)

    def test_weekly_wraps_full_week(self) -> None:
        friday_evening = utc(2026, 11, 27, 18, 0)
        result = next_weekly_run(friday_evening, time(10, 0), weekdays_to_mask([4]), TASHKENT)
        assert result == utc(2026, 12, 4, 5, 0)

    def test_daily_handles_dst_gap(self) -> None:
        # 2026-03-08 02:30 New York'da mavjud emas (soat 02:00 -> 03:00)
        result = next_daily_run(utc(2026, 3, 8, 5, 0), time(2, 30), NEW_YORK)
        assert result > utc(2026, 3, 8, 5, 0)
        assert result < utc(2026, 3, 8, 9, 0)


class TestActiveHours:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [(time(8, 59), False), (time(9, 0), True), (time(17, 59), True), (time(18, 0), False)],
    )
    def test_daytime_window(self, moment: time, expected: bool) -> None:
        assert is_within_active_hours(moment, time(9, 0), time(18, 0)) is expected

    @pytest.mark.parametrize(
        ("moment", "expected"),
        [(time(21, 0), False), (time(22, 0), True), (time(1, 0), True), (time(6, 0), False)],
    )
    def test_overnight_window(self, moment: time, expected: bool) -> None:
        assert is_within_active_hours(moment, time(22, 0), time(6, 0)) is expected

    def test_no_window_means_always(self) -> None:
        assert is_within_active_hours(time(3, 0), None, None)
        assert is_within_active_hours(time(3, 0), time(9, 0), time(9, 0))


class TestRandomRun:
    def test_within_bounds(self) -> None:
        rng = random.Random(42)
        start = utc(2026, 6, 1, 6, 0)  # 11:00 Toshkent
        for _ in range(200):
            result = next_random_run(start, 600, 1200, TASHKENT, rng=rng)
            assert timedelta(seconds=600) <= result - start <= timedelta(seconds=1200)

    def test_outside_active_hours_moves_to_window_start(self) -> None:
        # 17:50 Toshkent + 30..40 daqiqa -> 18:00 dan keyin -> ertaga 09:00
        start = utc(2026, 6, 1, 12, 50)
        result = next_random_run(
            start, 1800, 2400, TASHKENT, time(9, 0), time(18, 0), rng=random.Random(1)
        )
        assert result == utc(2026, 6, 2, 4, 0)

    def test_invalid_interval(self) -> None:
        with pytest.raises(ValueError):
            next_random_run(utc(2026, 1, 1), 100, 50, TASHKENT)
        with pytest.raises(ValueError):
            next_random_run(utc(2026, 1, 1), 0, 50, TASHKENT)
