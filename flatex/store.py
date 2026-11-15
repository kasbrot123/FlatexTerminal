"""Umsatzzeilen in die Datenbank schreiben."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from flatex.parse.umsaetze import Row

_KONTO_COLS = ("row_hash, buchtag, valuta, betrag_cent, waehrung, text, saldo_cent, ta_nr, empfaenger, "
               "quelle_datei, raw_json")
_DEPOT_COLS = ("row_hash, buchtag, valuta, isin, bezeichnung, stueck, kurs, kurs_waehrung, devisenkurs, "
               "betrag_cent, waehrung, text, ta_nr, quelle_datei, raw_json")


def _values(r: Row, datei: str | None) -> tuple:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    raw = json.dumps(r.raw, ensure_ascii=False, default=str)
    if r.art == "konto":
        return (r.row_hash, iso(r.buchtag), iso(r.valuta), r.betrag_cent or 0, r.waehrung, r.text,
                r.saldo_cent, r.ta_nr, r.empfaenger, datei, raw)
    return (r.row_hash, iso(r.buchtag), iso(r.valuta), r.isin, r.bezeichnung, r.stueck, r.kurs,
            r.kurs_waehrung, r.devisenkurs, r.betrag_cent, r.waehrung, r.text, r.ta_nr, datei, raw)


def _table(art: str) -> tuple[str, str]:
    return ("konto_umsaetze", _KONTO_COLS) if art == "konto" else ("depot_umsaetze", _DEPOT_COLS)


def upsert(con: sqlite3.Connection, rows: list[Row], datei: str | None) -> int:
    """Fügt nur neue Zeilen ein (für manuelle Importe mit beliebigem Zeitraum)."""
    neu = 0
    for r in rows:
        table, cols = _table(r.art)
        ph = ",".join("?" * len(cols.split(",")))
        cur = con.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({ph})", _values(r, datei))
        neu += cur.rowcount
    return neu


def replace_range(con: sqlite3.Connection, art: str, von: date, bis: date, rows: list[Row],
                  datei: str | None) -> int:
    """Ersetzt alle Zeilen im Fenster [von, bis] – für vollständige Fenster-Exporte.
    So verschwinden auch vorläufige Buchungen, die flatex später geändert hat."""
    table, cols = _table(art)
    con.execute(f"DELETE FROM {table} WHERE buchtag BETWEEN ? AND ?", (von.isoformat(), bis.isoformat()))
    ph = ",".join("?" * len(cols.split(",")))
    n = 0
    for r in rows:
        if von <= r.buchtag <= bis:
            con.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({ph})", _values(r, datei))
            n += 1
    return n
