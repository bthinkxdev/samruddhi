"""Account-specific exceptions raised by services."""

from __future__ import annotations


class AccountsError(Exception):
    """Base exception for the accounts app."""


class OTPVerificationError(AccountsError):
    """Base class for OTP verification failures."""


class OTPExpiredError(OTPVerificationError):
    """Raised when the OTP has passed its expiry time."""


class OTPAlreadyUsedError(OTPVerificationError):
    """Raised when the OTP has already been consumed."""


class OTPMaxAttemptsError(OTPVerificationError):
    """Raised when the maximum verification attempts have been exceeded."""


class OTPMismatchError(OTPVerificationError):
    """Raised when the submitted OTP does not match the stored hash."""


class OTPRateLimitError(AccountsError):
    """Raised when too many OTP requests were made for a phone number."""


class GoogleAuthError(AccountsError):
    """Raised when Google ID token verification fails."""


class CorporateRegistrationError(AccountsError):
    """Raised when corporate account registration fails validation."""
