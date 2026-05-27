"""Signing and canonicalization helpers for panel auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Mapping


def canonical_json(value: Any) -> str:
    """Return compact canonical JSON string."""
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def hmac_sha256_hex(secret: str, text: str) -> str:
    """Return lowercase hex HMAC SHA-256 signature."""
    return hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def sha256_hex(text: str) -> str:
    """Return lowercase SHA-256 hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jwt_hs256(secret: str, payload: Mapping[str, Any]) -> str:
    """Create a JWT with HS256 signature."""
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64u(canonical_json(header).encode('utf-8'))}."
        f"{_b64u(canonical_json(payload).encode('utf-8'))}"
    )
    signature = _b64u(hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"


def canonical_score_string(site_key: str, ref: str | None = None, unit_id: str | None = None) -> str:
    """Build canonical query signature string for score endpoint."""
    return f"GET\n/api/units/score\nref={ref or ''}\nid={unit_id or ''}\nsite={site_key}"
