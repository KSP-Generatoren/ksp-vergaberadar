"""SQLite-Persistenz. Bewusst klein gehalten.

tenant_id ist von Anfang an dabei: kostet heute nichts und ist die einzige
Weiche, die man spaeter nicht mehr ohne Schmerzen einzieht.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .config import DB_PATH
from .models import DocumentSnapshot, Notice

SCHEMA = """
CREATE TABLE IF NOT EXISTS notice (
    uid            TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'ksp',
    source         TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    title          TEXT,
    description    TEXT,
    buyer          TEXT,
    buyer_city     TEXT,
    nuts           TEXT,
    cpv            TEXT,
    procedure      TEXT,
    kind           TEXT,
    value_eur      REAL,
    published      TEXT,
    deadline       TEXT,
    notice_url     TEXT,
    documents_url  TEXT,
    score          INTEGER,
    score_reasons  TEXT,
    matched_product TEXT,
    kva            REAL,
    status         TEXT DEFAULT 'neu',
    first_seen     TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_notice_score    ON notice(tenant_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_notice_deadline ON notice(tenant_id, deadline);

CREATE TABLE IF NOT EXISTS snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_uid  TEXT NOT NULL REFERENCES notice(uid),
    fetched_at  TEXT NOT NULL,
    digest      TEXT NOT NULL,
    files       TEXT NOT NULL,
    text        TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshot_notice ON snapshot(notice_uid, fetched_at DESC);

CREATE TABLE IF NOT EXISTS change (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_uid  TEXT NOT NULL REFERENCES notice(uid),
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    kind        TEXT,
    filename    TEXT,
    severity    TEXT,
    diff        TEXT,
    acknowledged INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dossier (
    notice_uid  TEXT PRIMARY KEY REFERENCES notice(uid),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    payload     TEXT NOT NULL
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    p = Path(path or DB_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_notice(conn: sqlite3.Connection, n: Notice, tenant_id: str = "ksp") -> bool:
    """True, wenn der Datensatz neu war."""
    cur = conn.execute("SELECT uid FROM notice WHERE uid = ?", (n.uid,))
    is_new = cur.fetchone() is None
    conn.execute("""
        INSERT INTO notice (uid, tenant_id, source, source_id, title, description,
            buyer, buyer_city, nuts, cpv, procedure, kind, value_eur, published,
            deadline, notice_url, documents_url, score, score_reasons,
            matched_product, kva)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET
            title=excluded.title, description=excluded.description,
            deadline=excluded.deadline, score=excluded.score,
            score_reasons=excluded.score_reasons,
            documents_url=excluded.documents_url
    """, (
        n.uid, tenant_id, n.source, n.source_id, n.title, n.description,
        n.buyer, n.buyer_city, n.nuts, json.dumps(n.cpv), n.procedure, n.kind,
        n.value_eur, _iso(n.published), _iso(n.deadline), n.notice_url,
        n.documents_url, n.score, json.dumps(n.score_reasons, ensure_ascii=False),
        n.matched_product, n.kva,
    ))
    conn.commit()
    return is_new


def save_snapshot(conn: sqlite3.Connection, s: DocumentSnapshot) -> None:
    conn.execute(
        "INSERT INTO snapshot (notice_uid, fetched_at, digest, files, text) "
        "VALUES (?,?,?,?,?)",
        (s.notice_uid, s.fetched_at.isoformat(), s.digest,
         json.dumps(s.files), s.text),
    )
    conn.commit()


def latest_snapshot(conn: sqlite3.Connection, notice_uid: str) -> DocumentSnapshot | None:
    row = conn.execute(
        "SELECT * FROM snapshot WHERE notice_uid = ? ORDER BY fetched_at DESC LIMIT 1",
        (notice_uid,),
    ).fetchone()
    if not row:
        return None
    return DocumentSnapshot(
        notice_uid=row["notice_uid"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        files=json.loads(row["files"]),
        text=row["text"] or "",
    )


def _iso(v: date | datetime | None) -> str | None:
    return v.isoformat() if v else None
