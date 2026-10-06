"""Offset pagination helper with a bounded page size (prevents unbounded responses)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

MAX_LIMIT = 100


def paginate(items: Sequence[Any], limit: int, offset: int) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    page = list(items[offset : offset + limit])
    nxt = offset + limit
    return {
        "items": page,
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "next_offset": nxt if nxt < len(items) else None,
    }
