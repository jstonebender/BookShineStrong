import datetime
import logging
import os
from pathlib import Path

from playwright.sync_api import Page, Playwright, sync_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AppConfig
from .exceptions import AlreadyBookedError, BookingError, ClassNotFoundError, LoginError

log = logging.getLogger(__name__)

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class ArketaBooker:
    def __init__(
        self,
        config: AppConfig,
        headless: bool = True,
        screenshot_dir: str = "screenshots",
        dry_run: bool = False,
    ):
        self.config = config
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir)
        self.dry_run = dry_run
        self._playwright: Playwright = None
        self._browser = None
        self._page: Page = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=_CHROME_UA,
        )
        self._page = context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def run(self, target_date: datetime.date = None) -> dict:
        """Log in, find the class, book it, and return booking details."""
        from .scheduler import get_class_datetime, get_target_date

        if target_date is None:
            target_date = get_target_date(self.config)

        log.info("Starting Arketa booking for %s on %s", self.config.class_name, target_date)

        try:
            self._login()
            self._navigate_to_schedule()
            card = self._find_class_card(target_date)

            if self.dry_run:
                log.info("Dry run: found class card, skipping booking click.")
                return {
                    "success": True,
                    "dry_run": True,
                    "class_name": self.config.class_name,
                    "class_datetime": get_class_datetime(self.config, target_date),
                    "studio_name": self.config.studio_name,
                }

            self._book_class(card)

        except (LoginError, ClassNotFoundError, AlreadyBookedError, BookingError):
            raise
        except Exception as exc:
            path = self._save_screenshot("unexpected_error")
            raise BookingError(f"Unexpected error during booking: {exc}", screenshot_path=path) from exc

        class_dt = get_class_datetime(self.config, target_date)
        log.info("Successfully booked %s at %s", self.config.class_name, class_dt)
        return {
            "success": True,
            "class_name": self.config.class_name,
            "class_datetime": class_dt,
            "studio_name": self.config.studio_name,
        }

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _login(self) -> None:
        page = self._page
        log.debug("Navigating to Arketa login page")
        page.goto("https://app.arketa.co/login", wait_until="networkidle")

        try:
            page.locator('input[type="email"]').fill(self.config.arketa_email)
            page.locator('input[type="password"]').fill(self.config.arketa_password)
            page.locator('button[type="submit"]').click()
            page.wait_for_url("**/app.arketa.co/**", timeout=20000)
        except Exception as exc:
            path = self._save_screenshot("login_failed")
            raise LoginError(
                f"Login failed — check ARKETA_EMAIL / ARKETA_PASSWORD. Detail: {exc}",
                screenshot_path=path,
            ) from exc

        if "/login" in page.url:
            path = self._save_screenshot("login_rejected")
            error_text = ""
            try:
                alert = page.locator('[role="alert"]')
                if alert.is_visible():
                    error_text = alert.inner_text()
            except Exception:
                pass
            raise LoginError(
                f"Login rejected by Arketa. {error_text}".strip(),
                screenshot_path=path,
            )

        log.debug("Login successful, current URL: %s", page.url)

    def _navigate_to_schedule(self) -> None:
        page = self._page
        url = f"https://app.arketa.co/{self.config.studio_slug}"
        log.debug("Navigating to studio schedule: %s", url)
        page.goto(url, wait_until="networkidle")

        try:
            page.wait_for_selector(
                '.class-card, [class*="ClassCard"], [data-testid*="class"], [class*="schedule"]',
                timeout=15000,
            )
        except Exception:
            path = self._save_screenshot("schedule_not_found")
            raise BookingError(
                f"Could not find the class schedule at {url}. "
                "Check that studio.slug is correct.",
                screenshot_path=path,
            )
        log.debug("Schedule page loaded")

    def _find_class_card(self, target_date: datetime.date):
        """Locate the class card for the target date and class name/time."""
        page = self._page
        config = self.config

        # Format time for display matching (e.g. "7:00 AM" or "07:00")
        formatted_time_12h = config.class_time.strftime("%-I:%M %p").upper()
        formatted_time_24h = config.class_time.strftime("%H:%M")
        date_iso = target_date.isoformat()

        log.debug(
            "Looking for class '%s' at %s / %s on %s",
            config.class_name, formatted_time_12h, formatted_time_24h, date_iso,
        )

        # Advance the week view if the target date is not yet visible
        self._advance_to_week(target_date)

        # Strategy 1: data-date column attribute
        day_col = page.locator(f'[data-date="{date_iso}"]')
        if not day_col.is_visible():
            # Strategy 2: column heading text matching short date, e.g. "Wed 4" or "Nov 4"
            short_day = target_date.strftime("%a %-d")
            day_col = page.locator(f':has-text("{short_day}")').first

        # Within the day column find the card matching class name + time
        try:
            card = (
                day_col
                .locator(f':has-text("{config.class_name}")')
                .filter(has_text=formatted_time_12h)
                .first
            )
            if not card.is_visible(timeout=3000):
                raise Exception("not visible")
        except Exception:
            try:
                card = (
                    day_col
                    .locator(f':has-text("{config.class_name}")')
                    .filter(has_text=formatted_time_24h)
                    .first
                )
                card.wait_for(state="visible", timeout=3000)
            except Exception:
                path = self._save_screenshot("class_not_found")
                raise ClassNotFoundError(
                    f"Class '{config.class_name}' at {formatted_time_12h} not found on {target_date}.",
                    screenshot_path=path,
                )

        log.debug("Found class card: %s", card.inner_text()[:80])
        return card

    def _advance_to_week(self, target_date: datetime.date) -> None:
        """Click the next-week button until the target date's column is visible."""
        page = self._page
        date_iso = target_date.isoformat()
        for _ in range(8):  # max 8 weeks forward
            col = page.locator(f'[data-date="{date_iso}"]')
            if col.count() > 0 and col.first.is_visible():
                return
            # Try to click the next-week navigation button
            next_btn = page.locator(
                '[aria-label="Next week"], button:has-text("›"), button:has-text(">")'
                ', [data-testid="next-week"]'
            ).first
            if next_btn.is_visible():
                next_btn.click()
                page.wait_for_load_state("networkidle")
            else:
                break

    def _book_class(self, card) -> None:
        """Click Book on the card, confirm the modal, and wait for success."""
        page = self._page
        card_text = card.inner_text().lower()

        if "full" in card_text:
            raise BookingError("Class is full — cannot book.", screenshot_path=self._save_screenshot("class_full"))
        if "booked" in card_text or "reserved" in card_text:
            raise AlreadyBookedError("Already booked for this class.")

        # Click the Book / Reserve button
        try:
            book_btn = card.locator('button:has-text("Book"), button:has-text("Reserve")').first
            book_btn.click()
        except Exception as exc:
            path = self._save_screenshot("book_click_failed")
            raise BookingError(f"Could not click Book button: {exc}", screenshot_path=path) from exc

        # Handle confirmation dialog
        try:
            page.wait_for_selector('[role="dialog"]', timeout=8000)
            confirm_btn = page.locator(
                '[role="dialog"] button:has-text("Confirm"),'
                '[role="dialog"] button:has-text("Yes"),'
                '[role="dialog"] button:has-text("Book")'
            ).first
            confirm_btn.click()
        except Exception:
            # No modal — some studios go straight to confirmation
            log.debug("No confirmation dialog found; checking for success indicator")

        # Wait for success
        try:
            page.wait_for_selector(
                ':has-text("You\'re booked"), :has-text("Booking confirmed"),'
                ' :has-text("confirmed"), :has-text("Success")',
                timeout=12000,
            )
        except Exception as exc:
            path = self._save_screenshot("booking_confirmation_missing")
            raise BookingError(
                f"Booking click succeeded but no confirmation appeared: {exc}",
                screenshot_path=path,
            ) from exc

        log.info("Booking confirmed on page")

    def _save_screenshot(self, name: str) -> str:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"{ts}_{name}.png"
        try:
            self._page.screenshot(path=str(path))
            log.debug("Screenshot saved: %s", path)
        except Exception:
            pass
        return str(path)
