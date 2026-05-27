import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx

from panel_sdk import AsyncPanelClient, PanelClient

BASE = "https://p.test"
SITE_KEY = "pk_test_sdk"
SITE_SECRET = "site-secret-abc"
SCRUBBER_SECRET = "scrubber-secret-xyz"


@respx.mock
def test_ingest_unit_hmac_uses_exact_body_bytes() -> None:
    seen: dict[str, str | bytes | None] = {}

    def ingest_handler(request: httpx.Request) -> httpx.Response:
        seen["sig"] = request.headers.get("x-panel-ingest-sig")
        seen["body"] = request.content
        expected = hmac.new(SITE_SECRET.encode("utf-8"), request.content, hashlib.sha256).hexdigest()
        assert seen["sig"] == expected
        return httpx.Response(200, json={"id": "u_1"})

    respx.post(f"{BASE}/api/units/ingest").mock(side_effect=ingest_handler)
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    out = client.ingest_unit("process_output_rating", {"passage": "hello"})
    assert out["id"] == "u_1"
    assert seen["body"] == b'{"type":"process_output_rating","pool":"public","payload":{"passage":"hello"}}'


@respx.mock
def test_ingest_unit_scrubber_text_adds_attestation() -> None:
    seen: dict[str, str | bytes | None] = {}

    respx.post("https://s.test/v1/scrub").mock(return_value=httpx.Response(200, json={"scrubbed": "clean text"}))

    def ingest_handler(request: httpx.Request) -> httpx.Response:
        seen["att"] = request.headers.get("x-scrubber-attestation")
        seen["body"] = request.content
        return httpx.Response(200, json={"id": "u_2", "unit_ids": ["u_2"]})

    respx.post(f"{BASE}/api/units/ingest").mock(side_effect=ingest_handler)
    client = PanelClient(
        base_url=BASE,
        site_key=SITE_KEY,
        site_secret=SITE_SECRET,
        scrubber_secret=SCRUBBER_SECRET,
        scrubber_url="https://s.test",
    )
    out = client.ingest_unit("process_output_rating", {"passage": "x"}, scrubber_text="secret")
    assert out["id"] == "u_2"
    assert isinstance(seen["att"], str)
    body_raw = seen["body"]
    body_bytes = body_raw if isinstance(body_raw, bytes) else str(body_raw or "{}").encode("utf-8")
    body_obj = json.loads(body_bytes.decode("utf-8"))
    assert body_obj["payload"]["scrubber_text"] == "clean text"


@respx.mock
def test_ingest_trace_and_get_trace() -> None:
    respx.post(f"{BASE}/api/v1/traces").mock(return_value=httpx.Response(202, json={"trace_id": "tr_1", "status": "pending"}))
    respx.get(f"{BASE}/api/v1/traces/tr_1").mock(return_value=httpx.Response(200, json={"trace_id": "tr_1", "status": "done", "unit_ids": ["u1"]}))
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    ingest = client.ingest_trace("agent-a", {"messages": []}, trace_id="tr_1")
    assert ingest["trace_id"] == "tr_1"
    status = client.get_trace("tr_1")
    assert status["status"] == "done"


@respx.mock
def test_submit_judgment_posts_expected_shape() -> None:
    seen: dict[str, str] = {}

    def judgment_handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True, "token": "tkn"})

    respx.post(f"{BASE}/api/judgments").mock(side_effect=judgment_handler)
    client = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    out = client.submit_judgment(unit_id="u_1", rater_id="r_1", choice="yes", latency_ms=3000, confidence=0.8)
    assert out["ok"] is True
    body = json.loads(seen["body"])
    assert body["unit_id"] == "u_1"
    assert body["rater_id"] == "r_1"
    assert body["choice"] == "yes"
    assert body["latency_ms"] == 3000
    assert body["confidence"] == 0.8




@respx.mock
def test_ingest_unit_without_scrubber_text_has_no_attestation() -> None:
    seen: dict[str, str | None] = {}

    def ingest_handler(request: httpx.Request) -> httpx.Response:
        seen["att"] = request.headers.get("x-scrubber-attestation")
        return httpx.Response(200, json={"id": "u_3"})

    respx.post(f"{BASE}/api/units/ingest").mock(side_effect=ingest_handler)
    client = PanelClient(
        base_url=BASE,
        site_key=SITE_KEY,
        site_secret=SITE_SECRET,
        scrubber_secret=SCRUBBER_SECRET,
        scrubber_url="https://s.test",
    )
    out = client.ingest_unit("process_output_rating", {"passage": "x"})
    assert out["id"] == "u_3"
    assert seen["att"] is None
@respx.mock
@pytest.mark.asyncio
async def test_async_methods_parity() -> None:
    respx.post(f"{BASE}/api/units/ingest").mock(return_value=httpx.Response(200, json={"id": "u_9"}))
    respx.post(f"{BASE}/api/v1/traces").mock(return_value=httpx.Response(200, json={"trace_id": "tr_9", "unit_ids": []}))
    respx.get(f"{BASE}/api/v1/traces/tr_9").mock(return_value=httpx.Response(200, json={"trace_id": "tr_9", "status": "done"}))
    respx.post(f"{BASE}/api/judgments").mock(return_value=httpx.Response(200, json={"ok": True}))

    async with httpx.AsyncClient() as session:
        client = AsyncPanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET, client=session)
        unit = await client.ingest_unit("process_output_rating", {"passage": "hello"})
        trace = await client.ingest_trace("agent", {"messages": []}, trace_id="tr_9")
        status = await client.get_trace("tr_9")
        judgment = await client.submit_judgment(unit_id="u_9", rater_id="r_9", choice="yes", latency_ms=3000)

    assert unit["id"] == "u_9"
    assert trace["trace_id"] == "tr_9"
    assert status["status"] == "done"
    assert judgment["ok"] is True


def test_scrubber_attestation_jwt_shape() -> None:
    client = PanelClient(
        base_url=BASE,
        site_key=SITE_KEY,
        site_secret=SITE_SECRET,
        scrubber_secret=SCRUBBER_SECRET,
    )
    token = client._scrubber_attestation("ab" * 32)
    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
    assert payload["output_hash"] == "ab" * 32
    assert payload["exp"] - payload["iat"] == 60
    assert payload["jti"]
