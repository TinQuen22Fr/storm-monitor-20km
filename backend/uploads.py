"""Local file-based storage for uploaded storm records."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = asyncio.Lock()


def _file_path() -> Path:
    return Path(os.environ.get("STORM_DATA_FILE", "/app/backend/storm_data.json"))


async def _read_all() -> List[Dict[str, Any]]:
    p = _file_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


async def _write_all(items: List[Dict[str, Any]]) -> None:
    p = _file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


async def append(
    distance: float,
    energy: float,
    timestamp: Optional[str] = None,
    kind: str = "lightning",
    device_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a storm record. Returns the stored record."""
    async with _LOCK:
        items = await _read_all()
        record = {
            "id": str(uuid.uuid4()),
            "distance": float(distance),
            "energy": float(energy),
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "device_id": device_id,
        }
        items.append(record)
        await _write_all(items)
        return record


async def list_all(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    async with _LOCK:
        items = await _read_all()
    # Sort by timestamp descending (newest first)
    items.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    if limit is not None:
        return items[: max(0, int(limit))]
    return items


async def clear_all() -> int:
    async with _LOCK:
        items = await _read_all()
        count = len(items)
        await _write_all([])
    return count
