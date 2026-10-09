"""SQLite TTL cache. Prices 6h, FX 12h. Rules are never cached."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

PRICE_TTL = 6 * 3600
FX_TTL = 12 * 3600


class Cache:
    def __init__(self, path: Path | str = "cache.sqlite") -> None:
        self._db = sqlite3.connect(str(path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL, exp REAL NOT NULL)"
        )

    def get(self, key: str) -> Any | None:
        row = self._db.execute("SELECT v, exp FROM kv WHERE k = ?", (key,)).fetchone()
        if row is None or row[1] < time.time():
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO kv (k, v, exp) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
