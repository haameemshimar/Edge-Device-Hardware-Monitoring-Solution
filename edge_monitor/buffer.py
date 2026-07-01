"""
Local store-and-forward buffer.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time


class LocalBuffer:
    def __init__(self, db_path: str, max_age_hours: int = 24, max_rows: int = 20000):
        self.max_age_seconds = max_age_hours * 3600
        self.max_rows = max_rows
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def push(self, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics (payload, created_at) VALUES (?, ?)",
                (json.dumps(payload), time.time()),
            )
            self._conn.commit()
            self._prune()    # ← add this line
            
    def _prune(self) -> None:
        cutoff = time.time() - self.max_age_seconds
        self._conn.execute(
            "DELETE FROM metrics WHERE created_at < ?",
            (cutoff,)
        )
        (count,) = self._conn.execute("SELECT COUNT(*) FROM metrics").fetchone()
        if count > self.max_rows:
            overflow = count - self.max_rows
            self._conn.execute(
                """
                DELETE FROM metrics WHERE id IN (
                    SELECT id FROM metrics ORDER BY created_at ASC LIMIT ?
                )
                """,
                (overflow,)
            )
        self._conn.commit()

    def pop_batch(self, limit: int = 50) -> list[tuple[int, dict]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, payload FROM metrics ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row_id, json.loads(payload)) for row_id, payload in rows]

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            placeholders = ",".join("?" for _ in ids)
            self._conn.execute(f"DELETE FROM metrics WHERE id IN ({placeholders})", ids)
            self._conn.commit()

    def size(self) -> int:
        with self._lock:
            (count,) = self._conn.execute("SELECT COUNT(*) FROM metrics").fetchone()
        return count

    def close(self) -> None:
        self._conn.close()