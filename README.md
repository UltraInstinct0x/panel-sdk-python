# panel-sdk (python)

Thin client for [panel](https://github.com/UltraInstinct0x/panel). Python 3.10+.

## Install

```bash
pip install panel-sdk
```

## v0.2.0 options

```python
from panel_sdk import PanelClient

panel = PanelClient(
    base_url="https://panel.example.com",
    site_key="pk_live_xxx",
    site_secret="secret",
    site_secret_source="env",  # or "raw" for dual-secret mode
    scrubber_mode="off",  # off | self-sign | proxy
    scrubber_secret=None,  # required when scrubber_mode="self-sign"
    scrubber_url=None,  # required when scrubber_mode="proxy"
    engine_version="0.2.0",
    timeout_seconds=10.0,
    max_retries=3,
)
```

## PanelClient methods

- `ingest_trace(source_agent, blob, trace_id=None) -> TraceResult`
- `ingest_trace_and_wait(source_agent, blob, trace_id=None, max_wait_seconds=60, poll_interval_seconds=1.5) -> dict`
- `fetch_trace(trace_id) -> dict`
- `ingest_units(units) -> dict`
- `score_unit(ref=None, unit_id=None) -> dict`
- `skill_review(skill_name, diff, ...) -> dict`
- `verify_token(token) -> VerifyResult`

`verify_token(token)` signature remains unchanged.

## Rater clients

- `RaterClient.next_unit(pool, rater_id)`
- `RaterClient.submit_judgment(unit_id, choice)`
- Async parity via `AsyncRaterClient`

## Errors

- `PanelError`
- `PanelRateLimitError` (includes `scope`, `retry_after_s`)
- `PanelScrubberError`
