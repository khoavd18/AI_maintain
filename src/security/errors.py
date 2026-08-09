"""Stable security exception types shared by the application boundary."""


class AuthenticationError(ValueError):
    """Generic authentication failure that does not disclose account state."""


class CsrfValidationError(ValueError):
    """Raised when a refresh-cookie mutation lacks its bound CSRF token."""
