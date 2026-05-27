"""Typed exceptions for panel-sdk clients."""

from __future__ import annotations

from typing import Any


class PanelError(Exception):
    """Base exception for panel server errors."""

    def __init__(self, status: int, body: Any, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class PanelRateLimitError(PanelError):
    """Exception raised when panel returns HTTP 429 rate limit responses."""

    def __init__(self, status: int, body: Any, scope: str | None, retry_after_s: float | None) -> None:
        super().__init__(status=status, body=body, message="panel rate limited")
        self.scope = scope
        self.retry_after_s = retry_after_s


class PanelScrubberError(PanelError):
    """Exception raised when scrubber proxying or attestation fails."""
