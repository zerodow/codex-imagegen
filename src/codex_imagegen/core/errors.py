"""Typed errors with user-facing messages and stable process exit codes.

Each error carries an `exit_code` so the CLI can map a failure to a specific
shell status without string-matching messages.
"""


class ImagegenError(Exception):
    """Base error. Subclasses set a specific `exit_code`."""

    exit_code = 1

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class InputError(ImagegenError):
    """Bad user input (empty prompt, unknown size, unwritable output path)."""

    exit_code = 2


class AuthError(ImagegenError):
    """Missing/invalid ChatGPT OAuth credentials in ~/.codex/auth.json."""

    exit_code = 3


class GatewayError(ImagegenError):
    """Upstream HTTP/stream failure. Carries the HTTP status when known."""

    exit_code = 4

    def __init__(self, message: str, *, status: int | None = None, exit_code: int | None = None) -> None:
        super().__init__(message, exit_code=exit_code)
        self.status = status
