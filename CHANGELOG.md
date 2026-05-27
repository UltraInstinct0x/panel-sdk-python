# Changelog

## v0.2.0 — panel server sync

- Added operator ingest methods on sync + async clients:
  - `ingest_unit(type, payload, *, pool="public", scrubber_text=None)`
  - `ingest_trace(source_agent, blob, *, trace_id=None)`
  - `get_trace(trace_id)`
  - `submit_judgment(...)`
- Aligned verify path to `POST /api/verify`.
- Implemented exact-byte HMAC signing (`X-Panel-Ingest-Sig`) for operator posts.
- Added optional scrubber proxy call (`POST /v1/scrub`) and HS256 self-signed `X-Scrubber-Attestation` when scrubber text is explicitly provided.
- Added typed inputs/status exports: `IngestUnitInput`, `IngestTraceInput`, `TraceStatus`.
- Updated README with full sync + async usage examples.
- Updated pytest coverage for HMAC exact-byte signing, scrubber attestation flow, trace ingest/poll, judgments, and async parity.
