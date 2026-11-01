import datetime
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv

from .exceptions import ConfigError

_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


@dataclass
class AppConfig:
    studio_name: str
    studio_slug: str
    class_name: str
    day_of_week: int
    class_time: datetime.time
    timezone: ZoneInfo
    days_in_advance: int
    duration_minutes: int
    calendar_id: str
    arketa_email: str
    arketa_password: str


def load_config(config_path: str = "config.yaml") -> AppConfig:
    load_dotenv()

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Copy config.example.yaml to config.yaml and fill it in."
        )
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}")

    errors = []

    def require(section, key, label=None):
        label = label or f"{section}.{key}"
        try:
            val = raw[section][key]
            if val is None or val == "":
                errors.append(f"'{label}' must not be empty")
                return None
            return val
        except (KeyError, TypeError):
            errors.append(f"'{label}' is required but missing")
            return None

    studio_name = require("studio", "name")
    studio_slug = require("studio", "slug")
    class_name = require("booking", "class_name")
    day_str = require("booking", "day_of_week")
    time_str = require("booking", "time")
    tz_str = require("booking", "timezone")
    days_in_advance = require("booking", "days_in_advance")
    duration_minutes = require("booking", "duration_minutes")
    calendar_id = require("calendar", "calendar_id")

    arketa_email = os.environ.get("ARKETA_EMAIL", "")
    arketa_password = os.environ.get("ARKETA_PASSWORD", "")
    if not arketa_email:
        errors.append("ARKETA_EMAIL must be set in .env")
    if not arketa_password:
        errors.append("ARKETA_PASSWORD must be set in .env")

    if errors:
        raise ConfigError("Configuration errors:\n  - " + "\n  - ".join(errors))

    day_of_week = _DAY_NAMES.get(day_str.lower())
    if day_of_week is None:
        raise ConfigError(
            f"booking.day_of_week '{day_str}' is not valid. "
            "Use: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday"
        )

    try:
        class_time = datetime.time.fromisoformat(time_str)
    except ValueError:
        raise ConfigError(
            f"booking.time '{time_str}' is not a valid time. Use 24-hour HH:MM format, e.g. '07:00'."
        )

    try:
        timezone = ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        raise ConfigError(
            f"booking.timezone '{tz_str}' is not a valid IANA timezone. "
            "Examples: America/Chicago, America/New_York, America/Los_Angeles"
        )

    if not isinstance(days_in_advance, int) or days_in_advance < 0:
        raise ConfigError("booking.days_in_advance must be a non-negative integer")
    if not isinstance(duration_minutes, int) or duration_minutes <= 0:
        raise ConfigError("booking.duration_minutes must be a positive integer")

    return AppConfig(
        studio_name=studio_name,
        studio_slug=studio_slug,
        class_name=class_name,
        day_of_week=day_of_week,
        class_time=class_time,
        timezone=timezone,
        days_in_advance=days_in_advance,
        duration_minutes=duration_minutes,
        calendar_id=calendar_id,
        arketa_email=arketa_email,
        arketa_password=arketa_password,
    )
