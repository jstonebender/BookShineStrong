import datetime
import json
import logging
import os
import stat

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import AppConfig
from .exceptions import CalendarError

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def get_credentials() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as exc:
            log.warning("Could not load token.json: %s — re-authenticating", exc)
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            log.debug("Google credentials refreshed")
        except Exception as exc:
            log.warning("Token refresh failed: %s — re-authenticating", exc)
            creds = None

    if not creds:
        if not os.path.exists(CREDENTIALS_FILE):
            raise CalendarError(
                f"Google credentials file not found: {CREDENTIALS_FILE}. "
                "Download it from the Google Cloud Console (OAuth 2.0 Client ID) "
                "and place it in the project root."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        log.info("Google OAuth2 authentication completed")

    # Save token for future runs
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        os.chmod(TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
        log.debug("Token saved to %s", TOKEN_FILE)
    except Exception as exc:
        log.warning("Could not save token.json: %s", exc)

    return creds


def _build_event_body(booking_result: dict, config: AppConfig) -> dict:
    class_start: datetime.datetime = booking_result["class_datetime"]
    class_end = class_start + datetime.timedelta(minutes=config.duration_minutes)
    tz_str = str(config.timezone)

    return {
        "summary": booking_result["class_name"],
        "location": config.studio_name,
        "description": f"Booked via BookShineStrong. Studio: {config.studio_name}",
        "start": {
            "dateTime": class_start.isoformat(),
            "timeZone": tz_str,
        },
        "end": {
            "dateTime": class_end.isoformat(),
            "timeZone": tz_str,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }


def add_to_calendar(booking_result: dict, config: AppConfig) -> str:
    """Insert a Google Calendar event for the booked class. Returns the event HTML link."""
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        event_body = _build_event_body(booking_result, config)
        log.debug("Creating calendar event: %s", event_body["summary"])
        created = service.events().insert(
            calendarId=config.calendar_id,
            body=event_body,
        ).execute()
        link = created.get("htmlLink", "")
        log.info("Calendar event created: %s", link)
        return link
    except HttpError as exc:
        raise CalendarError(f"Google Calendar API error: {exc}") from exc
    except CalendarError:
        raise
    except Exception as exc:
        raise CalendarError(f"Unexpected error creating calendar event: {exc}") from exc
