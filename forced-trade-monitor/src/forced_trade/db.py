"""SQLite facts. Conflicts revise; they do not silently overwrite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "sql" / "schema.sql"


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    return conn


def payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def upsert_fact(
    conn: sqlite3.Connection,
    table: str,
    pk_cols: list[str],
    row: dict,
    payload: dict,
    event_ts_col: str | None = None,
    *,
    track_ingested: bool = True,
) -> str:
    """Insert a raw fact. Same hash is a no-op. A new hash appends a revision.

    track_ingested=False for tables without an ingested_at column
    (funding_info_snapshot); the hash contract is unchanged.
    """
    digest = payload_hash(payload)
    now = int(time.time() * 1000)
    stored = {**row, "payload_hash": digest}
    if track_ingested:
        stored["ingested_at"] = now
    where = " AND ".join(f"{col}=?" for col in pk_cols)
    keys = [row[col] for col in pk_cols]
    existing = conn.execute(
        f"SELECT * FROM {table} WHERE {where}", keys
    ).fetchone()
    if existing is None:
        cols = list(stored)
        conn.execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [stored[c] for c in cols],
        )
        return "inserted"
    if existing["payload_hash"] == digest:
        return "noop"
    conn.execute(
        """
        INSERT INTO raw_revisions (
          table_name, symbol, bar_open_ts, event_ts, old_hash, new_hash,
          old_payload, new_payload, revised_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            table,
            row.get("symbol"),
            row.get("bar_open_ts"),
            row.get(event_ts_col) if event_ts_col else None,
            existing["payload_hash"],
            digest,
            json.dumps(dict(existing), default=str),
            json.dumps(payload, sort_keys=True, default=str),
            now,
        ),
    )
    sets = [c for c in stored if c not in pk_cols]
    conn.execute(
        f"UPDATE {table} SET {', '.join(f'{c}=?' for c in sets)} WHERE {where}",
        [stored[c] for c in sets] + keys,
    )
    return "revised"
