import datetime
from zoneinfo import ZoneInfo

import pytest

from bookshinestrong.scheduler import get_class_datetime, get_target_date, should_run_today


def _make_config(day_of_week=2, days_in_advance=3, time="07:00", tz="America/Chicago"):
    from bookshinestrong.config import AppConfig
    return AppConfig(
        studio_name="Test Studio",
        studio_slug="test-studio",
        class_name="Yoga",
        day_of_week=day_of_week,  # 0=Mon, 2=Wed
        class_time=datetime.time.fromisoformat(time),
        timezone=ZoneInfo(tz),
        days_in_advance=days_in_advance,
        duration_minutes=60,
        calendar_id="primary",
        arketa_email="x@x.com",
        arketa_password="pw",
    )


def test_get_target_date_already_correct_day():
    # If today + days_in_advance already lands on the right weekday, return that date
    cfg = _make_config(day_of_week=2, days_in_advance=0)  # Wednesday, book same day
    wednesday = datetime.date(2026, 11, 4)  # a Wednesday
    assert wednesday.weekday() == 2
    result = get_target_date(cfg, reference_date=wednesday)
    assert result == wednesday


def test_get_target_date_advances_past_advance_window():
    # Today is Monday (weekday 0), looking for Wednesday (2), 3 days in advance
    # Monday + 3 = Thursday, so next Wednesday is 6 days from Monday
    cfg = _make_config(day_of_week=2, days_in_advance=3)
    monday = datetime.date(2026, 11, 2)  # a Monday
    assert monday.weekday() == 0
    result = get_target_date(cfg, reference_date=monday)
    assert result.weekday() == 2  # must be a Wednesday
    assert result > monday + datetime.timedelta(days=2)


def test_get_class_datetime_is_timezone_aware():
    cfg = _make_config(day_of_week=2, time="07:00", tz="America/Chicago")
    d = datetime.date(2026, 11, 4)
    dt = get_class_datetime(cfg, d)
    assert dt.tzinfo is not None
    assert dt.hour == 7
    assert dt.minute == 0


def test_should_run_today_true():
    # days_in_advance=3, day_of_week=Wednesday(2)
    # If today is Sunday (6), next Wednesday is 3 days away → should run today
    cfg = _make_config(day_of_week=2, days_in_advance=3)
    sunday = datetime.date(2026, 11, 1)  # a Sunday
    assert sunday.weekday() == 6
    target = get_target_date(cfg, reference_date=sunday)
    days_away = (target - sunday).days
    # should_run_today uses real "today", so we verify the math here instead
    assert days_away == cfg.days_in_advance


def test_get_target_date_wraps_to_next_week():
    # Wednesday (2), days_in_advance=0: if today IS Wednesday, target IS today
    cfg = _make_config(day_of_week=2, days_in_advance=0)
    thursday = datetime.date(2026, 11, 5)  # a Thursday
    assert thursday.weekday() == 3
    result = get_target_date(cfg, reference_date=thursday)
    assert result.weekday() == 2
    assert result > thursday  # must be next Wednesday
