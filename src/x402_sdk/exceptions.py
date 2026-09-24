"""SDK exceptions."""

from __future__ import annotations

__all__ = ["AmountError", "ConfigError", "FacilitatorError", "PaymentError", "X402Error"]


class X402Error(Exception):
    """Base class for all SDK errors."""


class ConfigError(X402Error):
    """Invalid or incomplete SDK configuration."""


class AmountError(X402Error):
    """A monetary price could not be converted to a token atomic amount."""


class PaymentError(X402Error):
    """A client payment (payload/header) is malformed or invalid."""


class FacilitatorError(X402Error):
    """Calling the AneePay facilitator failed."""
