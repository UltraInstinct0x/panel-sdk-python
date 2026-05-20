# panel-sdk (python)

thin client for [panel](https://github.com/UltraInstinct0x/panel). python 3.10+.

```
pip install panel-sdk
```

```python
from panel_sdk import PanelClient

panel = PanelClient(
    base_url="https://panel.example.com",
    site_key=os.environ["PANEL_SITE_KEY"],
    site_secret=os.environ["PANEL_SITE_SECRET"],
    scrubber_secret=os.environ.get("SCRUBBER_JWT_SECRET"),  # omit for first-party keys
)

v = panel.verify_token(request.json["panel_token"])
if not v.ok or (v.trust or 0) < 0.5:
    abort(403)

panel.ingest_trace(trace_id=f"tr_{uuid4()}", source_agent="myapp",
                   blob={"messages": [...]})
```

methods (sync + async via `AsyncPanelClient`): `ingest_unit`, `ingest_trace`, `verify_token`, `fetch_unit`, `fetch_trace`.
auth: HMAC-SHA256 (`x-panel-ingest-sig`) + optional scrubber JWT.
