"""SQLite-Schema und kleine Helfer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Ein Eintrag pro erfolgreich geladenem Download-Fenster.
CREATE TABLE IF NOT EXISTS sync_fenster (
    quelle     TEXT NOT NULL,          -- konto | depot
    von        TEXT NOT NULL,          -- ISO-Datum, inklusive
    bis        TEXT NOT NULL,          -- ISO-Datum, inklusive
    status     TEXT NOT NULL,          -- abgeschlossen | offen
    geladen_am TEXT NOT NULL,
    zeilen     INTEGER NOT NULL,
    datei      TEXT,
    sha256     TEXT,
    PRIMARY KEY (quelle, von, bis)
);

CREATE TABLE IF NOT EXISTS konto_umsaetze (
    id          INTEGER PRIMARY KEY,
    row_hash    TEXT NOT NULL UNIQUE,
    buchtag     TEXT NOT NULL,
    valuta      TEXT,
    betrag_cent INTEGER NOT NULL,
    waehrung    TEXT,
    text        TEXT,
    saldo_cent  INTEGER,
    quelle_datei TEXT,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_konto_buchtag ON konto_umsaetze(buchtag);

CREATE TABLE IF NOT EXISTS depot_umsaetze (
    id          INTEGER PRIMARY KEY,
    row_hash    TEXT NOT NULL UNIQUE,
    buchtag     TEXT NOT NULL,
    valuta      TEXT,
    isin        TEXT,
    bezeichnung TEXT,
    stueck      REAL,
    kurs        REAL,
    betrag_cent INTEGER,
    waehrung    TEXT,
    text        TEXT,
    quelle_datei TEXT,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_depot_buchtag ON depot_umsaetze(buchtag);
CREATE INDEX IF NOT EXISTS ix_depot_isin ON depot_umsaetze(isin);

-- Postfach-Dokumente. (datum, name, nr) identifiziert ein Dokument ohne Portal-Anfrage.
CREATE TABLE IF NOT EXISTS dokumente (
    id         INTEGER PRIMARY KEY,
    datum      TEXT NOT NULL,
    name       TEXT NOT NULL,
    nr         INTEGER NOT NULL,       -- laufende Nummer bei gleichem Datum+Name
    pfad       TEXT,
    sha256     TEXT,
    geladen_am TEXT,
    geparst    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (datum, name, nr)
);

CREATE TABLE IF NOT EXISTS pdf_transaktionen (
    id            INTEGER PRIMARY KEY,
    pfad          TEXT NOT NULL,
    pos           INTEGER NOT NULL,
    document_type TEXT,
    isin          TEXT,
    trade_date    TEXT,
    booking_date  TEXT,
    value_date    TEXT,
    quantity      REAL,
    net_amount    REAL,
    net_currency  TEXT,
    costs_total   REAL,
    json          TEXT NOT NULL,
    UNIQUE (pfad, pos)
);
"""


MIGRATIONS = {
    "konto_umsaetze": {"ta_nr": "TEXT", "empfaenger": "TEXT"},
    "depot_umsaetze": {"ta_nr": "TEXT", "kurs_waehrung": "TEXT", "devisenkurs": "REAL"},
}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # timeout + WAL: die Web-App liest, während im Hintergrund ein Sync schreibt
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    for table, cols in MIGRATIONS.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    return con


def meta_get(con: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
