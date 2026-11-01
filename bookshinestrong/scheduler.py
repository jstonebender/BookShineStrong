import datetime

from .config import AppConfig


def get_target_date(config: AppConfig, reference_date: datetime.date = None) -> datetime.date:
    """Return the next date matching config.day_of_week, starting from today + days_in_advance."""
    if reference_date is None:
        now = datetime.datetime.now(tz=config.timezone)
        reference_date = now.date()

    # Start looking from (today + days_in_advance) forward
    candidate = reference_date + datetime.timedelta(days=config.days_in_advance)
    while candidate.weekday() != config.day_of_week:
        candidate += datetime.timedelta(days=1)
    return candidate


def get_class_datetime(config: AppConfig, target_date: datetime.date) -> datetime.datetime:
    """Return a timezone-aware datetime for the class start."""
    return datetime.datetime.combine(target_date, config.class_time, tzinfo=config.timezone)


def should_run_today(config: AppConfig) -> bool:
    """Return True if today is exactly days_in_advance days before the target class day."""
    now = datetime.datetime.now(tz=config.timezone)
    today = now.date()
    target = get_target_date(config, reference_date=today)
    return (target - today).days == config.days_in_advance
