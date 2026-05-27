"""Rater clients for pool fetch and judgment submission."""

from __future__ import annotations

from typing import Any

import httpx

from panel_sdk._retry import parse_error_response


def _json_or_raw(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


class RaterClient:
    """Synchronous rater client using site-key auth only."""

    def __init__(self, *, base_url: str, site_key: str, timeout_seconds: float = 10.0, client: httpx.Client | None = None) -> None:
        """Initialize RaterClient."""
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def next_unit(self, pool: str, rater_id: str) -> dict[str, Any]:
        """Fetch next unit from rater pool."""
        response = self._client.get(
            f"{self.base_url}/api/rater/next",
            headers={"x-panel-site-key": self.site_key},
            params={"pool": pool, "rater_id": rater_id},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    def submit_judgment(self, unit_id: str, choice: str) -> dict[str, Any]:
        """Submit a rater judgment choice."""
        response = self._client.post(
            f"{self.base_url}/api/rater/judgment",
            headers={"x-panel-site-key": self.site_key, "content-type": "application/json"},
            json={"unit_id": unit_id, "choice": choice},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload


class AsyncRaterClient:
    """Asynchronous rater client using site-key auth only."""

    def __init__(self, *, base_url: str, site_key: str, timeout_seconds: float = 10.0, client: httpx.AsyncClient | None = None) -> None:
        """Initialize AsyncRaterClient."""
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def next_unit(self, pool: str, rater_id: str) -> dict[str, Any]:
        """Fetch next unit from rater pool."""
        response = await self._client.get(
            f"{self.base_url}/api/rater/next",
            headers={"x-panel-site-key": self.site_key},
            params={"pool": pool, "rater_id": rater_id},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    async def submit_judgment(self, unit_id: str, choice: str) -> dict[str, Any]:
        """Submit a rater judgment choice."""
        response = await self._client.post(
            f"{self.base_url}/api/rater/judgment",
            headers={"x-panel-site-key": self.site_key, "content-type": "application/json"},
            json={"unit_id": unit_id, "choice": choice},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload
