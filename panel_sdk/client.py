"""Panel operator clients (sync + async)."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping

import httpx

from panel_sdk._retry import blocking_sleep, parse_error_response, retry_delay_seconds, should_retry
from panel_sdk._scrubber import build_scrubber_headers, build_scrubber_headers_async
from panel_sdk._signing import canonical_json, canonical_score_string, hmac_sha256_hex
from panel_sdk.errors import PanelRateLimitError
from panel_sdk.types import TraceResult, VerifyResult


def _json_or_raw(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text}


class PanelClient:
    """Synchronous operator client for panel API."""

    def __init__(
        self,
        *,
        base_url: str,
        site_key: str,
        site_secret: str,
        site_secret_source: str = "env",
        scrubber_mode: str = "off",
        scrubber_secret: str | None = None,
        scrubber_url: str | None = None,
        engine_version: str = "0.2.0",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        """Initialize PanelClient with server-sync options."""
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.site_secret_source = site_secret_source
        self.scrubber_mode = scrubber_mode
        self.scrubber_secret = scrubber_secret
        self.scrubber_url = scrubber_url
        self.engine_version = engine_version
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def _signed_request(self, method: str, path: str, *, data: Any | None = None, params: dict[str, str] | None = None) -> Any:
        body_obj = data if data is not None else {}
        body = canonical_json(body_obj)
        body, scrubber_headers = build_scrubber_headers(
            mode=self.scrubber_mode,
            body=body,
            engine_version=self.engine_version,
            scrubber_secret=self.scrubber_secret,
            scrubber_url=self.scrubber_url,
            client=self._client,
            timeout_seconds=self.timeout_seconds,
        )

        signature = hmac_sha256_hex(self.site_secret, body)
        if method.upper() == "GET" and path == "/api/units/score":
            signature = hmac_sha256_hex(
                self.site_secret,
                canonical_score_string(self.site_key, ref=params.get("ref") if params else None, unit_id=params.get("id") if params else None),
            )

        headers: dict[str, str] = {
            "content-type": "application/json",
            "x-panel-site-key": self.site_key,
            "x-panel-ingest-sig": signature,
            **scrubber_headers,
        }
        if self.site_secret_source == "raw":
            headers["x-panel-ingest-secret"] = self.site_secret

        attempt = 0
        while True:
            response = self._client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                content=body if method.upper() != "GET" else None,
                params=params,
            )
            payload = _json_or_raw(response)
            if 200 <= response.status_code < 300:
                return payload
            retry_after_s: float | None = None
            if response.status_code == 429:
                ra = response.headers.get("Retry-After")
                if ra:
                    try:
                        retry_after_s = float(ra)
                    except ValueError:
                        retry_after_s = None
                if isinstance(payload, dict) and payload.get("retry_after_s") is not None:
                    retry_after_s = float(payload["retry_after_s"])
            if should_retry(response.status_code, attempt, self.max_retries):
                delay = retry_delay_seconds(response.status_code, attempt, retry_after_s)
                blocking_sleep(delay)
                attempt += 1
                continue
            parse_error_response(response.status_code, payload, response.text)

    def ingest_trace(self, *, source_agent: str, blob: Mapping[str, Any], trace_id: str | None = None) -> TraceResult:
        """Ingest a trace payload and return done/pending typed result."""
        body: dict[str, Any] = {"source_agent": source_agent, "blob": blob}
        if trace_id:
            body["trace_id"] = trace_id
        data = self._signed_request("POST", "/api/v1/traces", data=body)
        return TraceResult.from_json(data, self.base_url)

    def ingest_trace_and_wait(self, *, source_agent: str, blob: Mapping[str, Any], trace_id: str | None = None, max_wait_seconds: float = 60.0, poll_interval_seconds: float = 1.5) -> dict[str, Any]:
        """Ingest a trace and poll until completed or timeout."""
        result = self.ingest_trace(source_agent=source_agent, blob=blob, trace_id=trace_id)
        if result.status != "pending":
            return {"status": result.status, "trace_id": result.trace_id, "unit_ids": result.unit_ids}
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            polled = self.fetch_trace(result.trace_id)
            status = str(polled.get("status", ""))
            if status and status != "pending":
                return polled
            blocking_sleep(poll_interval_seconds)
        raise TimeoutError("trace polling timed out")

    def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        """Fetch trace status by trace ID."""
        response = self._client.get(f"{self.base_url}/api/v1/traces/{trace_id}")
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    def ingest_units(self, units: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """Ingest one or many units using /api/units/ingest."""
        return self._signed_request("POST", "/api/units/ingest", data={"units": units} if isinstance(units, list) else units)

    def score_unit(self, *, ref: str | None = None, unit_id: str | None = None) -> dict[str, Any]:
        """Lookup aggregate score by external ref or unit ID."""
        params: dict[str, str] = {}
        if ref is not None:
            params["ref"] = ref
        if unit_id is not None:
            params["id"] = unit_id
        return self._signed_request("GET", "/api/units/score", params=params)

    def skill_review(
        self,
        *,
        skill_name: str,
        diff: str,
        external_ref: str | None = None,
        context: str | None = None,
        source_agent: str | None = None,
        yes_label: str | None = None,
        no_label: str | None = None,
        trusted_pool_only: bool | None = None,
    ) -> dict[str, Any]:
        """Call skill review convenience endpoint."""
        payload: dict[str, Any] = {"skill_name": skill_name, "diff": diff}
        for key, value in {
            "external_ref": external_ref,
            "context": context,
            "source_agent": source_agent,
            "yes_label": yes_label,
            "no_label": no_label,
            "trusted_pool_only": trusted_pool_only,
        }.items():
            if value is not None:
                payload[key] = value
        return self._signed_request("POST", "/api/v1/skill-review", data=payload)

    def verify_token(self, token: str) -> VerifyResult:
        """Verify a widget token. Public API signature intentionally unchanged."""
        response = self._client.post(
            f"{self.base_url}/v1/verify",
            headers={"content-type": "application/json"},
            json={"token": token, "site_key": self.site_key},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return VerifyResult.from_json(payload)


class AsyncPanelClient:
    """Asynchronous operator client for panel API."""

    def __init__(
        self,
        *,
        base_url: str,
        site_key: str,
        site_secret: str,
        site_secret_source: str = "env",
        scrubber_mode: str = "off",
        scrubber_secret: str | None = None,
        scrubber_url: str | None = None,
        engine_version: str = "0.2.0",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize AsyncPanelClient with server-sync options."""
        self.base_url = base_url.rstrip("/")
        self.site_key = site_key
        self.site_secret = site_secret
        self.site_secret_source = site_secret_source
        self.scrubber_mode = scrubber_mode
        self.scrubber_secret = scrubber_secret
        self.scrubber_url = scrubber_url
        self.engine_version = engine_version
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def _signed_request(self, method: str, path: str, *, data: Any | None = None, params: dict[str, str] | None = None) -> Any:
        body_obj = data if data is not None else {}
        body = canonical_json(body_obj)
        body, scrubber_headers = await build_scrubber_headers_async(
            mode=self.scrubber_mode,
            body=body,
            engine_version=self.engine_version,
            scrubber_secret=self.scrubber_secret,
            scrubber_url=self.scrubber_url,
            client=self._client,
            timeout_seconds=self.timeout_seconds,
        )

        signature = hmac_sha256_hex(self.site_secret, body)
        if method.upper() == "GET" and path == "/api/units/score":
            signature = hmac_sha256_hex(
                self.site_secret,
                canonical_score_string(self.site_key, ref=params.get("ref") if params else None, unit_id=params.get("id") if params else None),
            )

        headers: dict[str, str] = {
            "content-type": "application/json",
            "x-panel-site-key": self.site_key,
            "x-panel-ingest-sig": signature,
            **scrubber_headers,
        }
        if self.site_secret_source == "raw":
            headers["x-panel-ingest-secret"] = self.site_secret

        attempt = 0
        while True:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                content=body if method.upper() != "GET" else None,
                params=params,
            )
            payload = _json_or_raw(response)
            if 200 <= response.status_code < 300:
                return payload
            retry_after_s: float | None = None
            if response.status_code == 429:
                ra = response.headers.get("Retry-After")
                if ra:
                    try:
                        retry_after_s = float(ra)
                    except ValueError:
                        retry_after_s = None
                if isinstance(payload, dict) and payload.get("retry_after_s") is not None:
                    retry_after_s = float(payload["retry_after_s"])
            if should_retry(response.status_code, attempt, self.max_retries):
                await asyncio.sleep(retry_delay_seconds(response.status_code, attempt, retry_after_s))
                attempt += 1
                continue
            parse_error_response(response.status_code, payload, response.text)

    async def ingest_trace(self, *, source_agent: str, blob: Mapping[str, Any], trace_id: str | None = None) -> TraceResult:
        """Ingest a trace payload and return done/pending typed result."""
        body: dict[str, Any] = {"source_agent": source_agent, "blob": blob}
        if trace_id:
            body["trace_id"] = trace_id
        data = await self._signed_request("POST", "/api/v1/traces", data=body)
        return TraceResult.from_json(data, self.base_url)

    async def ingest_trace_and_wait(self, *, source_agent: str, blob: Mapping[str, Any], trace_id: str | None = None, max_wait_seconds: float = 60.0, poll_interval_seconds: float = 1.5) -> dict[str, Any]:
        """Ingest a trace and poll until completed or timeout."""
        result = await self.ingest_trace(source_agent=source_agent, blob=blob, trace_id=trace_id)
        if result.status != "pending":
            return {"status": result.status, "trace_id": result.trace_id, "unit_ids": result.unit_ids}
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            polled = await self.fetch_trace(result.trace_id)
            status = str(polled.get("status", ""))
            if status and status != "pending":
                return polled
            await asyncio.sleep(poll_interval_seconds)
        raise TimeoutError("trace polling timed out")

    async def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        """Fetch trace status by trace ID."""
        response = await self._client.get(f"{self.base_url}/api/v1/traces/{trace_id}")
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return payload

    async def ingest_units(self, units: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """Ingest one or many units using /api/units/ingest."""
        return await self._signed_request("POST", "/api/units/ingest", data={"units": units} if isinstance(units, list) else units)

    async def score_unit(self, *, ref: str | None = None, unit_id: str | None = None) -> dict[str, Any]:
        """Lookup aggregate score by external ref or unit ID."""
        params: dict[str, str] = {}
        if ref is not None:
            params["ref"] = ref
        if unit_id is not None:
            params["id"] = unit_id
        return await self._signed_request("GET", "/api/units/score", params=params)

    async def skill_review(
        self,
        *,
        skill_name: str,
        diff: str,
        external_ref: str | None = None,
        context: str | None = None,
        source_agent: str | None = None,
        yes_label: str | None = None,
        no_label: str | None = None,
        trusted_pool_only: bool | None = None,
    ) -> dict[str, Any]:
        """Call skill review convenience endpoint."""
        payload: dict[str, Any] = {"skill_name": skill_name, "diff": diff}
        for key, value in {
            "external_ref": external_ref,
            "context": context,
            "source_agent": source_agent,
            "yes_label": yes_label,
            "no_label": no_label,
            "trusted_pool_only": trusted_pool_only,
        }.items():
            if value is not None:
                payload[key] = value
        return await self._signed_request("POST", "/api/v1/skill-review", data=payload)

    async def verify_token(self, token: str) -> VerifyResult:
        """Verify a widget token. Public API signature intentionally unchanged."""
        response = await self._client.post(
            f"{self.base_url}/v1/verify",
            headers={"content-type": "application/json"},
            json={"token": token, "site_key": self.site_key},
        )
        payload = _json_or_raw(response)
        if not (200 <= response.status_code < 300):
            parse_error_response(response.status_code, payload, response.text)
        return VerifyResult.from_json(payload)
