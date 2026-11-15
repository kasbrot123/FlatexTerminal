"""Benutzer-Einstellungen, gespeichert in der Datenbank (bleiben auch im Docker-Volume erhalten).

Bearbeitbar in der Web-App unter „Einstellungen“. Umgebungsvariablen dienen als Vorgabe,
solange in der Web-App nichts gespeichert wurde:
  FLATEX_EIGENE_NAMEN   Namen/IBANs der eigenen Konten, durch Komma getrennt
  FLATEX_DEPOT_START    Depoteröffnung (JJJJ-MM-TT)
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field, replace
from datetime import date

from flatex import db
from flatex.config import Config

TYPEN_FARBEN = ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8")


@dataclass
class Einstellungen:
    depot_start: str | None = None                 # überschreibt config.toml
    eigene_namen: list[str] = field(default_factory=list)
    farben: dict[str, str] = field(default_factory=dict)   # Typ -> Paletten-Slot, z. B. {"ETF": "s3"}


def laden(con: sqlite3.Connection) -> Einstellungen:
    roh = db.meta_get(con, "einstellungen")
    e = Einstellungen(**json.loads(roh)) if roh else Einstellungen()
    if not e.eigene_namen and os.environ.get("FLATEX_EIGENE_NAMEN"):
        e.eigene_namen = [n.strip() for n in os.environ["FLATEX_EIGENE_NAMEN"].split(",") if n.strip()]
    return e


def speichern(con: sqlite3.Connection, e: Einstellungen) -> Einstellungen:
    if e.depot_start:
        date.fromisoformat(e.depot_start)          # wirft bei ungültigem Datum
    e.eigene_namen = [n.strip() for n in e.eigene_namen if n and n.strip()]
    e.farben = {t: s for t, s in e.farben.items() if s in TYPEN_FARBEN}
    db.meta_set(con, "einstellungen", json.dumps(asdict(e), ensure_ascii=False))
    con.commit()
    return e


def wirksame_config(cfg: Config, con: sqlite3.Connection) -> Config:
    """Konfiguration mit den in der Web-App gespeicherten Werten (z. B. Depotstart)."""
    e = laden(con)
    if e.depot_start:
        return replace(cfg, depot_start=date.fromisoformat(e.depot_start))
    return cfg
