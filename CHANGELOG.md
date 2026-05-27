# Changelog

## v0.2.0 — server sync

- Refactored package into modular files:
  - `panel_sdk/client.py`
  - `panel_sdk/rater.py`
  - `panel_sdk/_signing.py`
  - `panel_sdk/_scrubber.py`
  - `panel_sdk/_retry.py`
  - `panel_sdk/errors.py`
  - `panel_sdk/types.py`
- Added operator-side methods: `ingest_units`, `score_unit`, `skill_review`, `ingest_trace_and_wait`
- Added typed trace ingest results (`TraceResult`) for sync/pending responses
- Added dual-secret support with `site_secret_source="raw"` and `x-panel-ingest-secret`
- Added scrubber dispatch modes: `off`, `self-sign`, `proxy`
- Added typed errors: `PanelRateLimitError`, `PanelScrubberError`
- Added rater clients: `RaterClient`, `AsyncRaterClient`
- Added 429/5xx retry and backoff behavior
- Added unit tests covering HMAC signing, scrubber JWT, async trace polling, and 429 retry
- Kept `verify_token(token)` public signature unchanged
