# panel-sdk (python)

Thin client for panel operator endpoints. Python 3.10+.

## Install

```bash
pip install panel-sdk
```

## Configure secrets with env vars

```bash
export PANEL_BASE_URL="https://panel.example.com"
export PANEL_SITE_KEY="pk_live_xxx"
export PANEL_SITE_SECRET="is_xxx"
export SCRUBBER_JWT_SECRET="scrubber-jwt-secret"
export SCRUBBER_URL="https://scrubber.example.com"
```

## Sync client

```python
import os

from panel_sdk import PanelClient

client = PanelClient(
    base_url=os.environ["PANEL_BASE_URL"],
    site_key=os.environ["PANEL_SITE_KEY"],
    site_secret=os.environ["PANEL_SITE_SECRET"],
    scrubber_secret=os.environ.get("SCRUBBER_JWT_SECRET"),
    scrubber_url=os.environ.get("SCRUBBER_URL"),
)

verify = client.verify_token("attestation-token")

unit = client.ingest_unit(
    "process_output_rating",
    {"source_agent": "scribe", "passage": "model output"},
    pool="public",
)

unit_with_scrub = client.ingest_unit(
    "process_output_rating",
    {"source_agent": "scribe", "passage": "sanitized output"},
    scrubber_text="raw potentially-sensitive text",
)

trace = client.ingest_trace(
    "scribe",
    {"messages": [{"role": "assistant", "content": "hello"}]},
)

trace_status = client.get_trace(trace["trace_id"])

judgment = client.submit_judgment(
    unit_id="u_123",
    rater_id="r_123",
    choice="yes",
    latency_ms=3000,
    confidence=0.9,
    behavioral={"focus": 0.8},
)
```

## Async client

```python
import os

from panel_sdk import AsyncPanelClient


async def main() -> None:
    async with AsyncPanelClient(
        base_url=os.environ["PANEL_BASE_URL"],
        site_key=os.environ["PANEL_SITE_KEY"],
        site_secret=os.environ["PANEL_SITE_SECRET"],
        scrubber_secret=os.environ.get("SCRUBBER_JWT_SECRET"),
        scrubber_url=os.environ.get("SCRUBBER_URL"),
    ) as client:
        await client.ingest_unit(
            "process_output_rating",
            {"source_agent": "scribe", "passage": "model output"},
        )

        trace = await client.ingest_trace(
            "scribe",
            {"messages": [{"role": "assistant", "content": "hello"}]},
        )

        await client.get_trace(trace["trace_id"])

        await client.submit_judgment(
            unit_id="u_123",
            rater_id="r_123",
            choice="yes",
            latency_ms=3000,
        )
```

## Errors

- `PanelError`
- `PanelRateLimitError`
- `PanelScrubberError`
