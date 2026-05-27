from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, cast

import httpx

from panel_sdk._retry import parse_error_response
from panel_sdk._signing import jwt_hs256
from panel_sdk.types import IngestTraceInput, IngestUnitInput, TraceStatus, VerifyResult


def _json_or_raw(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


class PanelClient:
    def __init__(
        self,
        *,
        base_url: str,
        site_key: str,
        site_secret: str,
        scrubber_secret: str | None = None,
        scrubber_url: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.scrubber_secret = scrubber_secret
        self.scrubber_url = scrubber_url
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def _sign_hmac(self, raw_body: bytes) -> str:
        return hmac.new(self.site_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    def _scrubber_attestation(self, output_hash_hex: str) -> str | None:
        if not self.scrubber_secret:
            return None
        now = int(time.time())
        payload = {
            "output_hash": output_hash_hex,
            "iat": now,
            "exp": now + 60,
            "jti": secrets.token_hex(16),
        }
        return jwt_hs256(self.scrubber_secret, payload)

    def _operator_post(self, path: str, body: dict[str, Any], *, attestation: str | None = None) -> dict[str, Any]:
        raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Panel-Site-Key": self.site_key,
            "X-Panel-Ingest-Sig": self._sign_hmac(raw_body),
        }
        if attestation:
            headers["X-Scrubber-Attestation"] = attestation
        response = self._client.post(f"{self.base_url}{path}", headers=headers, content=raw_body)
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    def ingest_unit(
        self,
        type: str,
        payload: dict[str, Any],
        *,
        pool: str = "public",
        scrubber_text: str | None = None,
    ) -> dict[str, Any]:
        body: IngestUnitInput = {"type": type, "pool": pool, "payload": dict(payload)}
        if scrubber_text is not None and self.scrubber_secret:
            scrubber_base = (self.scrubber_url or "").rstrip("/")
            if not scrubber_base:
                raise ValueError("scrubber_url is required when scrubber_text is provided with scrubber_secret")
            scrub = self._client.post(
                f"{scrubber_base}/v1/scrub",
                headers={"Content-Type": "application/json"},
                content=json.dumps({"text": scrubber_text}, separators=(",", ":")).encode("utf-8"),
            )
            scrub_payload = _json_or_raw(scrub)
            if not (200 <= scrub.status_code < 300):
                parse_error_response(scrub.status_code, scrub_payload, scrub.text)
            scrubbed = scrub_payload.get("scrubbed") if isinstance(scrub_payload, dict) else None
            if isinstance(scrubbed, str):
                body["payload"]["scrubber_text"] = scrubbed

        raw_for_att = json.dumps(body, separators=(",", ":")).encode("utf-8")
        att = self._scrubber_attestation(hashlib.sha256(raw_for_att).hexdigest())
        return self._operator_post("/api/units/ingest", cast(dict[str, Any], body), attestation=att)

    def ingest_trace(self, source_agent: str, blob: dict[str, Any], *, trace_id: str | None = None) -> dict[str, Any]:
        body: IngestTraceInput = {"source_agent": source_agent, "blob": blob}
        if trace_id:
            body["trace_id"] = trace_id
        raw_for_att = json.dumps(body, separators=(",", ":")).encode("utf-8")
        att = self._scrubber_attestation(hashlib.sha256(raw_for_att).hexdigest())
        return self._operator_post("/api/v1/traces", cast(dict[str, Any], body), attestation=att)

    def get_trace(self, trace_id: str) -> TraceStatus:
        response = self._client.get(f"{self.base_url}/api/v1/traces/{trace_id}")
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    def submit_judgment(
        self,
        *,
        unit_id: str,
        rater_id: str,
        choice: str,
        latency_ms: int,
        confidence: float | None = None,
        behavioral: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "unit_id": unit_id,
            "rater_id": rater_id,
            "choice": choice,
            "latency_ms": latency_ms,
        }
        if confidence is not None:
            body["confidence"] = confidence
        if behavioral is not None:
            body["behavioral"] = behavioral
        return self._operator_post("/api/judgments", body)

    def verify_token(self, token: str) -> VerifyResult:
        response = self._client.post(
            f"{self.base_url}/api/verify",
            headers={"content-type": "application/json"},
            json={"token": token},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return VerifyResult.from_json(payload)


class AsyncPanelClient:
    def __init__(
        self,
        *,
        base_url: str,
        site_key: str,
        site_secret: str,
        scrubber_secret: str | None = None,
        scrubber_url: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.scrubber_secret = scrubber_secret
        self.scrubber_url = scrubber_url
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    def _sign_hmac(self, raw_body: bytes) -> str:
        return hmac.new(self.site_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    def _scrubber_attestation(self, output_hash_hex: str) -> str | None:
        if not self.scrubber_secret:
            return None
        now = int(time.time())
        payload = {
            "output_hash": output_hash_hex,
            "iat": now,
            "exp": now + 60,
            "jti": secrets.token_hex(16),
        }
        return jwt_hs256(self.scrubber_secret, payload)

    async def _operator_post(self, path: str, body: dict[str, Any], *, attestation: str | None = None) -> dict[str, Any]:
        raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Panel-Site-Key": self.site_key,
            "X-Panel-Ingest-Sig": self._sign_hmac(raw_body),
        }
        if attestation:
            headers["X-Scrubber-Attestation"] = attestation
        response = await self._client.post(f"{self.base_url}{path}", headers=headers, content=raw_body)
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    async def ingest_unit(
        self,
        type: str,
        payload: dict[str, Any],
        *,
        pool: str = "public",
        scrubber_text: str | None = None,
    ) -> dict[str, Any]:
        body: IngestUnitInput = {"type": type, "pool": pool, "payload": dict(payload)}
        if scrubber_text is not None and self.scrubber_secret:
            scrubber_base = (self.scrubber_url or "").rstrip("/")
            if not scrubber_base:
                raise ValueError("scrubber_url is required when scrubber_text is provided with scrubber_secret")
            scrub = await self._client.post(
                f"{scrubber_base}/v1/scrub",
                headers={"Content-Type": "application/json"},
                content=json.dumps({"text": scrubber_text}, separators=(",", ":")).encode("utf-8"),
            )
            scrub_payload = _json_or_raw(scrub)
            if not (200 <= scrub.status_code < 300):
                parse_error_response(scrub.status_code, scrub_payload, scrub.text)
            scrubbed = scrub_payload.get("scrubbed") if isinstance(scrub_payload, dict) else None
            if isinstance(scrubbed, str):
                body["payload"]["scrubber_text"] = scrubbed

        raw_for_att = json.dumps(body, separators=(",", ":")).encode("utf-8")
        att = self._scrubber_attestation(hashlib.sha256(raw_for_att).hexdigest())
        return await self._operator_post("/api/units/ingest", cast(dict[str, Any], body), attestation=att)

    async def ingest_trace(self, source_agent: str, blob: dict[str, Any], *, trace_id: str | None = None) -> dict[str, Any]:
        body: IngestTraceInput = {"source_agent": source_agent, "blob": blob}
        if trace_id:
            body["trace_id"] = trace_id
        raw_for_att = json.dumps(body, separators=(",", ":")).encode("utf-8")
        att = self._scrubber_attestation(hashlib.sha256(raw_for_att).hexdigest())
        return await self._operator_post("/api/v1/traces", cast(dict[str, Any], body), attestation=att)

    async def get_trace(self, trace_id: str) -> TraceStatus:
        response = await self._client.get(f"{self.base_url}/api/v1/traces/{trace_id}")
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    async def submit_judgment(
        self,
        *,
        unit_id: str,
        rater_id: str,
        choice: str,
        latency_ms: int,
        confidence: float | None = None,
        behavioral: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "unit_id": unit_id,
            "rater_id": rater_id,
            "choice": choice,
            "latency_ms": latency_ms,
        }
        if confidence is not None:
            body["confidence"] = confidence
        if behavioral is not None:
            body["behavioral"] = behavioral
        return await self._operator_post("/api/judgments", body)

    async def verify_token(self, token: str) -> VerifyResult:
        response = await self._client.post(
            f"{self.base_url}/api/verify",
            headers={"content-type": "application/json"},
            json={"token": token},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return VerifyResult.from_json(payload)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncPanelClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()
