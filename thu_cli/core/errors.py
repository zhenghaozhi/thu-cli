"""Exception hierarchy shared by all layers."""
from __future__ import annotations

from enum import Enum


class ThuCliError(Exception):
    """Root exception for thu-cli business failures."""


class AuthError(ThuCliError):
    """Base class for authentication and protocol failures."""


class BadCredentials(AuthError):
    """Username or password is incorrect; callers may prompt again."""


class TwoFactorFailed(AuthError):
    """2FA code is wrong or expired; callers may prompt for another code."""


class CaptchaRequired(AuthError):
    """Captcha image is required and no ``on_captcha`` callback was supplied."""

    def __init__(self, msg: str = "captcha required", *, image_bytes: bytes = b""):
        super().__init__(msg)
        self.image_bytes = image_bytes


class SessionExpired(AuthError):
    """Saved cookies are no longer accepted by the remote service."""


class TwoFactorPending(AuthError):
    """2FA code has been sent; callers can persist and resume this state."""

    def __init__(
        self,
        *,
        choice: str,
        cookies: list[dict],
        step_idx: int,
        debug_dir: str | None,
        realm_id: str = "learn",
    ) -> None:
        super().__init__(f"2FA pending: choice={choice}")
        self.choice = choice
        self.cookies = cookies
        self.step_idx = step_idx
        self.debug_dir = debug_dir
        self.realm_id = realm_id

    def to_dict(self) -> dict:
        return {
            "choice": self.choice,
            "cookies": self.cookies,
            "step_idx": self.step_idx,
            "debug_dir": self.debug_dir,
            "realm_id": self.realm_id,
        }


class LearnFailReason(str, Enum):
    INVALID_RESPONSE = "invalid_response"
    OPERATION_FAILED = "operation_failed"


class LearnError(ThuCliError):
    """Web Learning domain error with optional raw payload for debugging."""

    def __init__(
        self,
        reason: LearnFailReason,
        message: str | None = None,
        *,
        payload: object | None = None,
    ):
        self.reason = reason
        self.payload = payload
        super().__init__(message or reason.value)


__all__ = [
    "AuthError",
    "BadCredentials",
    "CaptchaRequired",
    "LearnError",
    "LearnFailReason",
    "SessionExpired",
    "ThuCliError",
    "TwoFactorFailed",
    "TwoFactorPending",
]
