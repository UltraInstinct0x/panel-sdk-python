"""panel_sdk — thin client for the panel HTTP api.

usage:
    from panel_sdk import PanelClient
    c = PanelClient(base_url="https://panel.example.com",
                    site_key="pk_live_xxx", site_secret="...",
                    scrubber_secret="...")  # omit for first-party keys
    c.verify_token(token)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

import httpx

__version__ = "0.1.0"
__all__ = ["PanelClient", "AsyncPanelClient", "PanelError", "VerifyResult"]


class PanelError(Exception):
    def __init__(self, status: int, body: Any, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class VerifyResult:
    ok: bool
    trust: float | None = None
    tier_used: str | None = None
    unit_ids: list[str] | None = None
    reason: str | None = None

    @classmethod
    def from_json(cls, j: Mapping[str, Any]) -> "VerifyResult":
        return cls(
            ok=bool(j.get("ok")),
            trust=j.get("trust"),
            tier_used=j.get("tier_used"),
            unit_ids=j.get("unit_ids"),
            reason=j.get("reason"),
        )


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _hmac_hex(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _jwt_hs256(secret: str, payload: Mapping[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    si = f"{_b64u(json.dumps(header, separators=(',', ':')).encode())}.{_b64u(json.dumps(payload, separators=(',', ':')).encode())}"
    sig = _b64u(hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest())
    return f"{si}.{sig}"


def _attest(scrubber_secret: str, body: str, engine_version: str) -> str:
    now = int(time.time())
    return _jwt_hs256(scrubber_secret, {
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + 300,
        "input_hash": "x",
        "output_hash": _sha256_hex(body),
        "mode": "text",
        "engine_version": engine_version,
    })


def _check(resp: httpx.Response) -> Any:
    try:
        j = resp.json()
    except Exception:
        j = {"raw": resp.text}
    if not (200 <= resp.status_code < 300):
        raise PanelError(resp.status_code, j, f"panel {resp.status_code}: {resp.text[:300]}")
    return j


def _ingest_headers(site_key: str, site_secret: str, body: str,
                    scrubber_secret: str | None, engine_version: str) -> MutableMapping[str, str]:
    h: MutableMapping[str, str] = {
        "content-type": "application/json",
        "x-panel-site-key": site_key,
        "x-panel-ingest-sig": _hmac_hex(site_secret, body),
    }
    if scrubber_secret:
        h["x-scrubber-attestation"] = _attest(scrubber_secret, body, engine_version)
    return h


class PanelClient:
    def __init__(self, base_url: str, site_key: str, site_secret: str,
                 scrubber_secret: str | None = None, engine_version: str = "0.2.0",
                 client: httpx.Client | None = None, timeout: float = 10.0) -> None:
        self.base = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.scrubber_secret = scrubber_secret
        self.engine_version = engine_version
        self._client = client or httpx.Client(timeout=timeout)

    def ingest_unit(self, *, type: str, payload: dict, pool: str | None = None) -> dict:
        d: dict[str, Any] = {"type": type, "payload": payload}
        if pool is not None: d["pool"] = pool
        body = json.dumps(d, separators=(",", ":"))
        r = self._client.post(self.base + "/api/units/ingest",
                              headers=_ingest_headers(self.site_key, self.site_secret, body,
                                                      self.scrubber_secret, self.engine_version),
                              content=body)
        return _check(r)

    def ingest_trace(self, *, trace_id: str, source_agent: str, blob: dict) -> dict:
        body = json.dumps({"trace_id": trace_id, "source_agent": source_agent, "blob": blob}, separators=(",", ":"))
        r = self._client.post(self.base + "/api/v1/traces",
                              headers=_ingest_headers(self.site_key, self.site_secret, body,
                                                      self.scrubber_secret, self.engine_version),
                              content=body)
        return _check(r)

    def verify_token(self, token: str) -> VerifyResult:
        r = self._client.post(self.base + "/v1/verify",
                              headers={"content-type": "application/json"},
                              json={"token": token, "site_key": self.site_key})
        return VerifyResult.from_json(_check(r))

    def fetch_unit(self, unit_id: str) -> dict:
        r = self._client.get(f"{self.base}/api/units/{unit_id}")
        return _check(r)

    def fetch_trace(self, trace_id: str) -> dict:
        r = self._client.get(f"{self.base}/api/v1/traces/{trace_id}")
        return _check(r)


class AsyncPanelClient:
    def __init__(self, base_url: str, site_key: str, site_secret: str,
                 scrubber_secret: str | None = None, engine_version: str = "0.2.0",
                 client: httpx.AsyncClient | None = None, timeout: float = 10.0) -> None:
        self.base = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.scrubber_secret = scrubber_secret
        self.engine_version = engine_version
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def ingest_unit(self, *, type: str, payload: dict, pool: str | None = None) -> dict:
        d: dict[str, Any] = {"type": type, "payload": payload}
        if pool is not None: d["pool"] = pool
        body = json.dumps(d, separators=(",", ":"))
        r = await self._client.post(self.base + "/api/units/ingest",
                                    headers=_ingest_headers(self.site_key, self.site_secret, body,
                                                            self.scrubber_secret, self.engine_version),
                                    content=body)
        return _check(r)

    async def ingest_trace(self, *, trace_id: str, source_agent: str, blob: dict) -> dict:
        body = json.dumps({"trace_id": trace_id, "source_agent": source_agent, "blob": blob}, separators=(",", ":"))
        r = await self._client.post(self.base + "/api/v1/traces",
                                    headers=_ingest_headers(self.site_key, self.site_secret, body,
                                                            self.scrubber_secret, self.engine_version),
                                    content=body)
        return _check(r)

    async def verify_token(self, token: str) -> VerifyResult:
        r = await self._client.post(self.base + "/v1/verify",
                                    headers={"content-type": "application/json"},
                                    json={"token": token, "site_key": self.site_key})
        return VerifyResult.from_json(_check(r))

    async def fetch_unit(self, unit_id: str) -> dict:
        r = await self._client.get(f"{self.base}/api/units/{unit_id}")
        return _check(r)

    async def fetch_trace(self, trace_id: str) -> dict:
        r = await self._client.get(f"{self.base}/api/v1/traces/{trace_id}")
        return _check(r)
