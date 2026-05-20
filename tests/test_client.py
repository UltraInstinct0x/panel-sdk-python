import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx

from panel_sdk import AsyncPanelClient, PanelClient, PanelError, VerifyResult

BASE = "https://p.test"
SITE_KEY = "pk_test_sdk"
SITE_SECRET = "site-secret-abc"
SCRUBBER = "scrubber-secret-xyz"


def _expected_sig(body: str) -> str:
    return hmac.new(SITE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


@respx.mock
def test_ingest_unit_signs_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sig"] = request.headers.get("x-panel-ingest-sig")
        seen["key"] = request.headers.get("x-panel-site-key")
        seen["attest"] = request.headers.get("x-scrubber-attestation")
        return httpx.Response(200, json={"id": "u_1"})

    respx.post(f"{BASE}/api/units/ingest").mock(side_effect=handler)
    c = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    r = c.ingest_unit(type="step_validity", payload={"foo": 1})
    assert r == {"id": "u_1"}
    assert seen["key"] == SITE_KEY
    assert seen["attest"] is None  # no scrubber secret → no attestation
    assert seen["sig"] == _expected_sig(json.dumps({"type": "step_validity", "payload": {"foo": 1}}, separators=(",", ":")))


@respx.mock
def test_ingest_trace_attaches_attestation_when_scrubber_secret_set():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["attest"] = request.headers["x-scrubber-attestation"]
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"trace_id": "tr_1", "units_emitted": 5})

    respx.post(f"{BASE}/api/v1/traces").mock(side_effect=handler)
    c = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET, scrubber_secret=SCRUBBER)
    r = c.ingest_trace(trace_id="tr_1", source_agent="hermes", blob={"messages": []})
    assert r["units_emitted"] == 5
    parts = seen["attest"].split(".")
    assert len(parts) == 3
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    expected_output = hashlib.sha256(seen["body"].encode()).hexdigest()
    assert payload["output_hash"] == expected_output


@respx.mock
def test_verify_token_returns_parsed_result():
    respx.post(f"{BASE}/v1/verify").mock(
        return_value=httpx.Response(200, json={"ok": True, "trust": 0.9, "tier_used": "C1", "unit_ids": ["u_a"]})
    )
    c = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    v = c.verify_token("t.t.t")
    assert isinstance(v, VerifyResult)
    assert v.ok is True and v.tier_used == "C1" and v.trust == 0.9


@respx.mock
def test_raises_panel_error_on_non_2xx():
    respx.post(f"{BASE}/api/units/ingest").mock(
        return_value=httpx.Response(422, json={"error": "scrubber_attestation_required"})
    )
    c = PanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET)
    with pytest.raises(PanelError) as ei:
        c.ingest_unit(type="x", payload={})
    assert ei.value.status == 422
    assert ei.value.body == {"error": "scrubber_attestation_required"}


@respx.mock
async def test_async_client_parity():
    respx.post(f"{BASE}/v1/verify").mock(return_value=httpx.Response(200, json={"ok": True, "trust": 0.6, "tier_used": "C2"}))
    async with httpx.AsyncClient() as session:
        c = AsyncPanelClient(base_url=BASE, site_key=SITE_KEY, site_secret=SITE_SECRET, client=session)
        v = await c.verify_token("z.z.z")
        assert v.ok and v.tier_used == "C2"
