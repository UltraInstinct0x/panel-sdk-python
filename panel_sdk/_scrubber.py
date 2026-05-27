"""Scrubber attestation helpers for off/self-sign/proxy modes."""

from __future__ import annotations

import secrets
import time

import httpx

from panel_sdk._signing import jwt_hs256, sha256_hex
from panel_sdk.errors import PanelScrubberError


def build_scrubber_headers(
    *,
    mode: str,
    body: str,
    engine_version: str,
    scrubber_secret: str | None,
    scrubber_url: str | None,
    client: httpx.Client,
    timeout_seconds: float,
) -> tuple[str, dict[str, str]]:
    """Build scrubber attestation header and potentially scrubbed body."""
    if mode == "off":
        return body, {}
    if mode == "self-sign":
        if not scrubber_secret:
            raise PanelScrubberError(400, {"error": "missing_scrubber_secret"}, "scrubber_secret required")
        now = int(time.time())
        token = jwt_hs256(
            scrubber_secret,
            {
                "jti": secrets.token_hex(16),
                "iat": now,
                "exp": now + 300,
                "input_hash": "x",
                "output_hash": sha256_hex(body),
                "mode": "text",
                "engine_version": engine_version,
            },
        )
        return body, {"x-scrubber-attestation": token}
    if mode == "proxy":
        if not scrubber_url:
            raise PanelScrubberError(400, {"error": "missing_scrubber_url"}, "scrubber_url required")
        resp = client.post(
            f"{scrubber_url.rstrip('/')}/scrub",
            headers={"content-type": "application/json"},
            content=body,
            timeout=timeout_seconds,
        )
        if resp.status_code >= 400:
            raise PanelScrubberError(resp.status_code, {"raw": resp.text}, "scrubber proxy failed")
        token = resp.headers.get("x-scrubber-attestation")
        if not token:
            raise PanelScrubberError(502, {"error": "missing_attestation"}, "scrubber proxy did not return attestation")
        return resp.text, {"x-scrubber-attestation": token}
    raise PanelScrubberError(400, {"error": "invalid_scrubber_mode", "mode": mode}, "invalid scrubber_mode")


async def build_scrubber_headers_async(
    *,
    mode: str,
    body: str,
    engine_version: str,
    scrubber_secret: str | None,
    scrubber_url: str | None,
    client: httpx.AsyncClient,
    timeout_seconds: float,
) -> tuple[str, dict[str, str]]:
    """Async version of scrubber dispatch."""
    if mode == "off":
        return body, {}
    if mode == "self-sign":
        if not scrubber_secret:
            raise PanelScrubberError(400, {"error": "missing_scrubber_secret"}, "scrubber_secret required")
        now = int(time.time())
        token = jwt_hs256(
            scrubber_secret,
            {
                "jti": secrets.token_hex(16),
                "iat": now,
                "exp": now + 300,
                "input_hash": "x",
                "output_hash": sha256_hex(body),
                "mode": "text",
                "engine_version": engine_version,
            },
        )
        return body, {"x-scrubber-attestation": token}
    if mode == "proxy":
        if not scrubber_url:
            raise PanelScrubberError(400, {"error": "missing_scrubber_url"}, "scrubber_url required")
        resp = await client.post(
            f"{scrubber_url.rstrip('/')}/scrub",
            headers={"content-type": "application/json"},
            content=body,
            timeout=timeout_seconds,
        )
        if resp.status_code >= 400:
            raise PanelScrubberError(resp.status_code, {"raw": resp.text}, "scrubber proxy failed")
        token = resp.headers.get("x-scrubber-attestation")
        if not token:
            raise PanelScrubberError(502, {"error": "missing_attestation"}, "scrubber proxy did not return attestation")
        return resp.text, {"x-scrubber-attestation": token}
    raise PanelScrubberError(400, {"error": "invalid_scrubber_mode", "mode": mode}, "invalid scrubber_mode")
