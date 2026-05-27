import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx

from panel_sdk import PanelClient, PanelRateLimitError, TraceResult

BASE = "https://p.test"
SITE_KEY = "pk_test_sdk"
SITE_SECRET = "site-secret-abc"
SCRUBBER_SECRET = "scrubber-secret-xyz"


def test_hmac_signature_for_ingest_body() -> None:
    seen: dict[str, str | None] = {}

    @respx.mock
    def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            seen["sig"] = request.headers.get("x-panel-ingest-sig")
            body = request.content.decode("utf-8")
            expected = hmac.new(SITE_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
            assert seen["sig"] == expected
            return httpx.Response(200, json={"ok": True})

        respx.post(f"{BASE}/api/units/ingest").mock(side_effect=handler)
        client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
        client.ingest_units({"type": "process_output_rating", "passage": "hello"})

    run()


@respx.mock
def test_hmac_signature_for_score_canonical_query() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sig"] = request.headers.get("x-panel-ingest-sig")
        return httpx.Response(200, json={"counts": {"yes": 1}, "trust_weighted_score": 0.8})

    respx.get(f"{BASE}/api/units/score").mock(side_effect=handler)
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    client.score_unit(ref="ext_123")
    canonical = f"GET\n/api/units/score\nref=ext_123\nid=\nsite={SITE_KEY}"
    expected = hmac.new(SITE_SECRET.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    assert seen["sig"] == expected


@respx.mock
def test_scrubber_self_sign_jwt_structure() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers["x-scrubber-attestation"]
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"trace_id": "tr_1", "unit_ids": [], "structural_count": 1, "llm_count": 0, "skipped_count": 0})

    respx.post(f"{BASE}/api/v1/traces").mock(side_effect=handler)
    client = PanelClient(
        base_url=BASE,
        site_key=SITE_KEY,
        site_secret=SITE_SECRET,
        scrubber_mode="self-sign",
        scrubber_secret=SCRUBBER_SECRET,
    )
    client.ingest_trace(source_agent="agent", blob={"messages": []}, trace_id="tr_1")
    parts = seen["token"].split(".")
    assert len(parts) == 3
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
    assert payload["engine_version"] == "0.2.0"
    assert payload["mode"] == "text"
    assert payload["output_hash"] == hashlib.sha256(seen["body"].encode("utf-8")).hexdigest()


@respx.mock
def test_ingest_trace_and_wait_completes() -> None:
    respx.post(f"{BASE}/api/v1/traces").mock(
        return_value=httpx.Response(202, json={"trace_id": "tr_2", "status": "pending", "poll": "/v1/traces/tr_2"})
    )
    route = respx.get(f"{BASE}/api/v1/traces/tr_2").mock(
        side_effect=[
            httpx.Response(202, json={"trace_id": "tr_2", "status": "pending"}),
            httpx.Response(200, json={"trace_id": "tr_2", "status": "done", "unit_ids": ["u1"]}),
        ]
    )
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    result = client.ingest_trace_and_wait(source_agent="agent", blob={"messages": []}, trace_id="tr_2", max_wait_seconds=2, poll_interval_seconds=0)
    assert result["status"] == "done"
    assert route.call_count == 2


@respx.mock
def test_429_retry_after_and_then_raises() -> None:
    route = respx.post(f"{BASE}/api/units/ingest").mock(
        side_effect=[
            httpx.Response(429, json={"error": "rate_limited", "scope": "ingest", "retry_after_s": 0}, headers={"Retry-After": "0"}),
            httpx.Response(429, json={"error": "rate_limited", "scope": "ingest", "retry_after_s": 0}, headers={"Retry-After": "0"}),
        ]
    )
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET, max_retries=1)
    with pytest.raises(PanelRateLimitError) as exc:
        client.ingest_units({"type": "process_output_rating", "passage": "x"})
    assert exc.value.scope == "ingest"
    assert exc.value.retry_after_s == 0.0
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_async_ingest_trace_returns_typed_result() -> None:
    from panel_sdk import AsyncPanelClient

    respx.post(f"{BASE}/api/v1/traces").mock(
        return_value=httpx.Response(200, json={"trace_id": "tr_9", "unit_ids": ["u9"], "structural_count": 1, "llm_count": 1, "skipped_count": 0})
    )
    async with httpx.AsyncClient() as session:
        client = AsyncPanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET, client=session)
        result = await client.ingest_trace(source_agent="agent", blob={"messages": []}, trace_id="tr_9")
    assert isinstance(result, TraceResult)
    assert result.status == "done"
