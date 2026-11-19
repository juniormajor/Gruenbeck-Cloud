"""Exceptions raised by the Grünbeck cloud API layer."""

from __future__ import annotations


class GruenbeckError(Exception):
    """Base class for all errors of the API layer."""


class GruenbeckAuthError(GruenbeckError):
    """Credentials were rejected or the session cannot be renewed."""


class GruenbeckConnectionError(GruenbeckError):
    """The cloud could not be reached (network, DNS, TLS, timeout)."""


class GruenbeckServerError(GruenbeckError):
    """The cloud answered with a server error (5xx)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Store the HTTP status code next to the message."""
        super().__init__(message)
        self.status = status


class GruenbeckRateLimitError(GruenbeckServerError):
    """The cloud asked us to slow down (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Store the server provided retry delay in seconds."""
        super().__init__(message, 429)
        self.retry_after = retry_after


class GruenbeckResponseError(GruenbeckError):
    """The cloud answered with something we cannot interpret."""


class GruenbeckParameterError(GruenbeckError):
    """The cloud rejected a parameter change."""
