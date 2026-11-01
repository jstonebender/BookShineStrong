#!/usr/bin/env python3
import argparse
import logging
import sys

from bookshinestrong.arketa import ArketaBooker
from bookshinestrong.calendar_client import add_to_calendar
from bookshinestrong.config import load_config
from bookshinestrong.exceptions import (
    AlreadyBookedError,
    BookShineStrongError,
    CalendarError,
)
from bookshinestrong.scheduler import get_target_date, should_run_today

EXIT_SUCCESS = 0
EXIT_SKIPPED = 1
EXIT_ERROR = 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automate Arketa gym class booking and Google Calendar event creation."
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--force", action="store_true", help="Ignore the 'should run today' gate and always attempt booking")
    parser.add_argument("--no-calendar", action="store_true", help="Skip adding the event to Google Calendar")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and find the class, but do not book")
    parser.add_argument("--visible", action="store_true", help="Run Playwright with a visible browser window (useful for debugging)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("main")

    try:
        config = load_config(args.config)
    except BookShineStrongError as exc:
        log.error("%s", exc)
        return EXIT_ERROR

    target_date = get_target_date(config)

    if not args.force and not args.dry_run:
        if not should_run_today(config):
            log.info(
                "Today is not the booking day for '%s' (need to be %d day(s) before %s). "
                "Use --force to override.",
                config.class_name,
                config.days_in_advance,
                target_date,
            )
            return EXIT_SKIPPED

    log.info(
        "Targeting '%s' on %s at %s (%s)",
        config.class_name,
        target_date,
        config.class_time.strftime("%H:%M"),
        config.studio_name,
    )

    booking_result = None
    try:
        with ArketaBooker(
            config,
            headless=not args.visible,
            dry_run=args.dry_run,
        ) as booker:
            booking_result = booker.run(target_date=target_date)

    except AlreadyBookedError as exc:
        log.warning("Already booked for this class: %s", exc)
        if exc.screenshot_path:
            log.debug("Screenshot: %s", exc.screenshot_path)
        return EXIT_SKIPPED

    except BookShineStrongError as exc:
        log.error("Booking failed: %s", exc)
        if hasattr(exc, "screenshot_path") and exc.screenshot_path:
            log.info("Screenshot saved to: %s", exc.screenshot_path)
        return EXIT_ERROR

    if args.dry_run:
        log.info("Dry run complete — class found, no booking made.")
        return EXIT_SUCCESS

    if not args.no_calendar:
        try:
            event_url = add_to_calendar(booking_result, config)
            log.info("Calendar event added: %s", event_url)
        except CalendarError as exc:
            log.warning(
                "Booking succeeded but failed to add Google Calendar event: %s. "
                "Run again with --force --no-calendar to skip, or fix calendar credentials.",
                exc,
            )
            # Don't fail the run — the booking already happened

    return EXIT_SUCCESS


def entry_point():
    sys.exit(main())


if __name__ == "__main__":
    entry_point()
