class PrinterError(Exception):
    """Base class for all ohbrother errors."""


class EditorLiteModeError(PrinterError):
    """Printer is in Editor Lite / storage mode (PID 0x209e).

    Hold the Editor Lite button until the green LED turns off, then reconnect.
    The printer re-enumerates as 0x209b.
    """


class TapeMismatchError(PrinterError):
    """Configured label type does not match the installed tape.

    DK-22251 (black+red) tape requires PrintOptions(label='62red', red=True)
    even for black-only prints. Single-color mode returns a generic error with
    no error bits set — this exception makes that explicit.
    """


class StatusError(PrinterError):
    """Printer status packet reported one or more errors."""

    def __init__(self, errors: list[str], status: dict) -> None:
        self.errors = errors
        self.status = status
        super().__init__(f"Printer error: {', '.join(errors)}")
