import datetime
import os
import textwrap
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bookshinestrong.config import load_config
from bookshinestrong.exceptions import ConfigError


VALID_YAML = textwrap.dedent("""\
    studio:
      name: "Test Studio"
      slug: "test-studio"
    booking:
      class_name: "Yoga Flow"
      day_of_week: "Monday"
      time: "09:00"
      timezone: "America/New_York"
      days_in_advance: 2
      duration_minutes: 60
    calendar:
      calendar_id: "primary"
""")


@pytest.fixture()
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    monkeypatch.setenv("ARKETA_EMAIL", "test@example.com")
    monkeypatch.setenv("ARKETA_PASSWORD", "secret")
    return str(path)


def test_load_valid_config(config_file):
    cfg = load_config(config_file)
    assert cfg.studio_name == "Test Studio"
    assert cfg.studio_slug == "test-studio"
    assert cfg.class_name == "Yoga Flow"
    assert cfg.day_of_week == 0  # Monday
    assert cfg.class_time == datetime.time(9, 0)
    assert cfg.timezone == ZoneInfo("America/New_York")
    assert cfg.days_in_advance == 2
    assert cfg.duration_minutes == 60
    assert cfg.calendar_id == "primary"
    assert cfg.arketa_email == "test@example.com"
    assert cfg.arketa_password == "secret"


def test_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("nonexistent.yaml")


def test_missing_env_credentials(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(VALID_YAML)
    monkeypatch.delenv("ARKETA_EMAIL", raising=False)
    monkeypatch.delenv("ARKETA_PASSWORD", raising=False)
    with pytest.raises(ConfigError, match="ARKETA_EMAIL"):
        load_config(str(path))


def test_invalid_day_of_week(tmp_path, monkeypatch):
    bad_yaml = VALID_YAML.replace("Monday", "Funday")
    path = tmp_path / "config.yaml"
    path.write_text(bad_yaml)
    monkeypatch.setenv("ARKETA_EMAIL", "x@x.com")
    monkeypatch.setenv("ARKETA_PASSWORD", "pw")
    with pytest.raises(ConfigError, match="Funday"):
        load_config(str(path))


def test_invalid_time_format(tmp_path, monkeypatch):
    bad_yaml = VALID_YAML.replace('"09:00"', '"9am"')
    path = tmp_path / "config.yaml"
    path.write_text(bad_yaml)
    monkeypatch.setenv("ARKETA_EMAIL", "x@x.com")
    monkeypatch.setenv("ARKETA_PASSWORD", "pw")
    with pytest.raises(ConfigError, match="9am"):
        load_config(str(path))


def test_invalid_timezone(tmp_path, monkeypatch):
    bad_yaml = VALID_YAML.replace("America/New_York", "Nowhere/Fake")
    path = tmp_path / "config.yaml"
    path.write_text(bad_yaml)
    monkeypatch.setenv("ARKETA_EMAIL", "x@x.com")
    monkeypatch.setenv("ARKETA_PASSWORD", "pw")
    with pytest.raises(ConfigError, match="Nowhere/Fake"):
        load_config(str(path))
