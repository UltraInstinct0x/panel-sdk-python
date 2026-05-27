"""Dataclass result types for panel-sdk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypedDict


class IngestUnitInput(TypedDict, total=False):
    type: str
    pool: str
    payload: dict[str, Any]


class IngestTraceInput(TypedDict, total=False):
    trace_id: str
    source_agent: str
    blob: dict[str, Any]


class TraceStatus(TypedDict, total=False):
    trace_id: str
    status: Literal["pending", "done", "error"] | str
    unit_ids: list[str]
    structural_count: int
    llm_count: int
    skipped_count: int
    result_json: dict[str, Any] | str | None


@dataclass
class VerifyResult:
    """Parsed response for POST /v1/verify."""

    ok: bool
    trust: float | None = None
    tier_used: str | None = None
    unit_ids: list[str] | None = None
    reason: str | None = None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "VerifyResult":
        """Construct VerifyResult from panel JSON response."""
        return cls(
            ok=bool(payload.get("ok")),
            trust=payload.get("trust"),
            tier_used=payload.get("tier_used"),
            unit_ids=payload.get("unit_ids"),
            reason=payload.get("reason"),
        )


@dataclass
class TraceResult:
    """Typed result for trace ingest sync/async behavior."""

    status: str
    trace_id: str
    unit_ids: list[str] | None = None
    structural_count: int | None = None
    llm_count: int | None = None
    skipped_count: int | None = None
    poll_url: str | None = None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any], base_url: str) -> "TraceResult":
        """Construct TraceResult from panel JSON response."""
        status = str(payload.get("status") or "done")
        poll = payload.get("poll")
        poll_url = None
        if isinstance(poll, str):
            poll_url = f"{base_url.rstrip('/')}{poll}"
        return cls(
            status=status,
            trace_id=str(payload.get("trace_id", "")),
            unit_ids=payload.get("unit_ids"),
            structural_count=payload.get("structural_count"),
            llm_count=payload.get("llm_count"),
            skipped_count=payload.get("skipped_count"),
            poll_url=poll_url,
        )
