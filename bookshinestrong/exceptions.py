class BookShineStrongError(Exception):
    pass


class ConfigError(BookShineStrongError):
    pass


class ArketaError(BookShineStrongError):
    def __init__(self, message: str, screenshot_path: str = None):
        super().__init__(message)
        self.screenshot_path = screenshot_path


class LoginError(ArketaError):
    pass


class ClassNotFoundError(ArketaError):
    pass


class AlreadyBookedError(ArketaError):
    pass


class BookingError(ArketaError):
    pass


class CalendarError(BookShineStrongError):
    pass
