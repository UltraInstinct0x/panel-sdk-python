"""HTTP retry helpers for rate-limit and server errors."""

from __future__ import annotations

import time
from typing import Any

from panel_sdk.errors import PanelError, PanelRateLimitError

SERVER_BACKOFF_S = (0.5, 1.5, 3.5)


def parse_error_response(status_code: int, data: Any, text: str) -> Any:
    """Raise typed errors for non-success responses."""
    if status_code == 429:
        scope = data.get("scope") if isinstance(data, dict) else None
        retry_after = data.get("retry_after_s") if isinstance(data, dict) else None
        if isinstance(retry_after, int):
            retry_after = float(retry_after)
        if retry_after is not None and not isinstance(retry_after, float):
            retry_after = None
        raise PanelRateLimitError(status=429, body=data, scope=scope, retry_after_s=retry_after)
    raise PanelError(status=status_code, body=data, message=f"panel {status_code}: {text[:300]}")


def should_retry(status_code: int, attempt: int, max_retries: int) -> bool:
    """Return whether a request should be retried for this status."""
    if attempt >= max_retries:
        return False
    return status_code == 429 or status_code >= 500


def retry_delay_seconds(status_code: int, attempt: int, retry_after_s: float | None) -> float:
    """Return capped sleep duration before next retry."""
    if status_code == 429:
        return min(30.0, retry_after_s or 1.0)
    idx = min(attempt, len(SERVER_BACKOFF_S) - 1)
    return SERVER_BACKOFF_S[idx]


def blocking_sleep(seconds: float) -> None:
    """Sleep helper for sync retries."""
    time.sleep(seconds)
