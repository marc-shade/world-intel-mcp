"""SQLite TTL cache for world-intel-mcp.

Simple key-value cache with per-key TTL, WAL mode, and automatic eviction.
No external deps — just stdlib sqlite3.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("world-intel-mcp.cache")

_DEFAULT_DB = Path.home() / ".cache" / "world-intel-mcp" / "cache.db"


class Cache:
    """SQLite-backed TTL cache."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at)")
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if missing or expired."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if time.time() > expires_at:
            return None
        return json.loads(value)

    def get_stale(self, key: str) -> Any | None:
        """Get cached value even if expired (last-known-good fallback)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store a value with TTL in seconds."""
        conn = self._get_conn()
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value, default=str), now + ttl_seconds, now),
        )
        conn.commit()

    def delete(self, key: str) -> None:
        """Delete a specific key."""
        conn = self._get_conn()
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()

    def evict_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
        conn.commit()
        return cursor.rowcount

    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        conn = self._get_conn()
        now = time.time()
        total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM cache WHERE expires_at < ?", (now,)
        ).fetchone()[0]
        return {
            "total_entries": total,
            "active_entries": total - expired,
            "expired_entries": expired,
            "db_path": str(self.db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
