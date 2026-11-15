"""Inkrementeller, schonender Download.

Kernideen:
- Zeitraum in Monate (Umsätze) bzw. Quartale (Postfach) teilen.
- Abgeschlossene Fenster nie wieder laden, offene (laufender/letzter Monat) auffrischen.
- Abgeschnittene Antworten erkennen, ohne das Limit des Portals zu kennen:
  verdächtige Fenster halbieren und vergleichen, ob die Hälften mehr Zeilen liefern.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator

from flatex import db, store
from flatex.config import Config
from flatex.portal.exports import ExportResult
from flatex.portal.session import ActionBudgetExhausted

Fetch = Callable[[date, date], ExportResult]


# --- Fensterplanung ----------------------------------------------------------

def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def windows(start: date, today: date, months: int = 1) -> Iterator[tuple[date, date]]:
    """Kalenderfenster von `start` bis `today`, jeweils `months` Monate lang.
    Fenster sind an Kalendergrenzen ausgerichtet (Quartale bei months=3), damit
    unterschiedliche Startdaten dieselben Fenster ergeben."""
    aligned_month = (start.month - 1) // months * months + 1
    cur = date(start.year, aligned_month, 1)
    while cur <= today:
        m = cur.month - 1 + months
        nxt = date(cur.year + m // 12, m % 12 + 1, 1)
        yield cur, min(nxt - timedelta(days=1), today)
        cur = nxt


def is_closed(bis_nominal: date, geladen_am: date, closed_after_days: int) -> bool:
    return geladen_am >= bis_nominal + timedelta(days=closed_after_days)


def pending_windows(con: sqlite3.Connection, quelle: str, start: date, today: date,
                    months: int = 1) -> list[tuple[date, date]]:
    """Fenster, die (noch) geladen werden müssen – neueste zuerst."""
    done = {
        (r["von"], r["bis"])
        for r in con.execute(
            "SELECT von, bis FROM sync_fenster WHERE quelle = ? AND status = 'abgeschlossen'", (quelle,)
        )
    }
    out = []
    for von, bis in windows(start, today, months):
        nominal_bis = _nominal_end(von, months)
        if (von.isoformat(), nominal_bis.isoformat()) not in done:
            out.append((von, bis))
    return list(reversed(out))


def _nominal_end(von: date, months: int) -> date:
    m = von.month - 1 + months
    return date(von.year + m // 12, m % 12 + 1, 1) - timedelta(days=1)


# --- Erkennung abgeschnittener Listen ----------------------------------------

# Typische Seiten-/Listenlimits. Ein Fenster mit genau so vielen Zeilen wird vorsichtshalber geprüft.
ROUND_LIMITS = frozenset({20, 25, 30, 40, 50, 75, 100, 150, 200, 250, 300, 500, 1000})


@dataclass
class Checks:
    suspect_min_rows: int = 20
    edge_gap_days: int = 3
    known_caps: set[int] | None = None
    # Bewiesen sicher: Antworten mit weniger Zeilen können nicht abgeschnitten sein
    # (die Kalibrierung hat eine größere Antwort als vollständig nachgewiesen).
    sicher_bis: int = 0


def suspicious(res: ExportResult, von: date, bis: date, chk: Checks) -> str | None:
    n = len(res.rows)
    if res.truncated_hint:
        return "Portal meldet Kürzung"
    if chk.known_caps:
        # Limit bekannt: nur Antworten, die es erreichen, können gekürzt sein.
        return f"Zeilenzahl {n} erreicht ein bekanntes Limit" if n >= min(chk.known_caps) else None
    if chk.sicher_bis and n < chk.sicher_bis:
        return None
    if n in ROUND_LIMITS:
        return f"Zeilenzahl {n} ist ein typisches Listenlimit"
    if n >= chk.suspect_min_rows and von < bis:
        days = [r.buchtag for r in res.rows]
        gap = max((min(days) - von).days, (bis - max(days)).days)
        if gap > max(chk.edge_gap_days, (bis - von).days // 10):
            return f"{n} Zeilen, aber {gap} Tage ohne Buchung am Fensterrand"
    return None


@dataclass
class Piece:
    von: date
    bis: date
    res: ExportResult


def fetch_complete(fetch: Fetch, von: date, bis: date, chk: Checks, log=print,
                   on_cap: Callable[[int], None] | None = None,
                   _res: ExportResult | None = None) -> list[Piece]:
    """Lädt [von, bis] vollständig; halbiert rekursiv, solange eine Antwort verdächtig ist."""
    if chk.known_caps is None:
        chk.known_caps = set()
    res = _res or fetch(von, bis)
    why = suspicious(res, von, bis, chk)
    if not why:
        return [Piece(von, bis, res)]
    if von >= bis:
        log(f"  WARNUNG {von}: {why}, kleiner geht nicht – übernehme {len(res.rows)} Zeilen")
        return [Piece(von, bis, res)]
    log(f"  {von}..{bis}: {why} → halbiere")
    mid = von + timedelta(days=max(1, (bis - von).days // 2))
    left = fetch_complete(fetch, von, mid - timedelta(days=1), chk, log, on_cap)
    right = fetch_complete(fetch, mid, bis, chk, log, on_cap)
    total = sum(len(p.res.rows) for p in left + right)
    if total > len(res.rows):
        cap = len(res.rows)
        log(f"  {von}..{bis}: war abgeschnitten ({cap} statt {total}) – Limit {cap} gemerkt")
        chk.known_caps.add(cap)
        if on_cap:
            on_cap(cap)
        # Teilstücke, die vor dem Erkennen des Limits als "ok" galten, mit dem neuen Wissen nachprüfen.
        out: list[Piece] = []
        for p in left + right:
            if len(p.res.rows) >= cap and p.von < p.bis:
                out.extend(fetch_complete(fetch, p.von, p.bis, chk, log, on_cap, _res=p.res))
            else:
                out.append(p)
        return out
    if total < len(res.rows):
        log(f"  WARNUNG {von}..{bis}: Hälften liefern weniger ({total} < {len(res.rows)}) – nehme Ganzes")
    return [Piece(von, bis, res)]


def calibrate(fetch: Fetch, start: date, today: date, chk: Checks, log=print) -> int | None:
    """Einmalig: findet ein Zeilenlimit des Portals.

    Gesamtzeitraum einmal abfragen, dann Jahre (bzw. Quartale bei jungem Depot) einzeln.
    Liefern die Teile zusammen mehr als das Ganze, wurde das Ganze abgeschnitten,
    und seine Zeilenzahl ist das Limit. Danach wird jedes Fenster, das diese
    Zeilenzahl erreicht, sicher halbiert – egal wie "krumm" das Limit ist.
    """
    if chk.known_caps is None:
        chk.known_caps = set()
    span = (today - start).days
    months = 12 if span > 2 * 365 else 3 if span > 180 else 1
    part_windows = [(max(v, start), b) for v, b in windows(start, today, months)]
    if len(part_windows) < 2:
        log("Kalibrierung übersprungen: Zeitraum zu kurz (weniger als 2 Teile)")
        return None
    whole = fetch(start, today)
    parts = [fetch(v, b) for v, b in part_windows]
    total = sum(len(p.rows) for p in parts)
    n = len(whole.rows)
    log(f"Kalibrierung: Gesamtzeitraum {n} Zeilen, Teile zusammen {total}")
    if total > n:
        chk.known_caps.add(n)
        log(f"  → Portal begrenzt auf {n} Zeilen pro Abfrage")
        return n
    # Das Ganze war vollständig: jede Antwort mit weniger als n Zeilen ist sicher ungekürzt.
    chk.sicher_bis = max(chk.sicher_bis, n + 1)
    log(f"  → kein Zeilenlimit: Antworten bis {n} Zeilen sind nachweislich vollständig")
    return None


# --- Umsatz-Sync ----------------------------------------------------------------

def _load_caps(con: sqlite3.Connection, quelle: str) -> set[int]:
    return set(json.loads(db.meta_get(con, f"caps_{quelle}", "[]")))


def _save_cap(con: sqlite3.Connection, quelle: str, n: int) -> None:
    caps = _load_caps(con, quelle) | {n}
    db.meta_set(con, f"caps_{quelle}", json.dumps(sorted(caps)))


def start_for_months(today: date, monate: int | None, depot_start: date) -> date:
    """--monate N: laufender Monat plus N-1 Vormonate (nie vor dem Depotstart)."""
    if not monate:
        return depot_start
    m = today.month - (monate - 1)
    y = today.year
    while m < 1:
        m += 12
        y -= 1
    return max(date(y, m, 1), depot_start)


def clamp_end(ende: date | None, today: date) -> date | None:
    """--bis wird auf das Monatsende aufgerundet (nur ganze Monate), None = bis heute."""
    if ende is None:
        return None
    e = month_end(ende)
    return None if e >= today else e


def _calibration_covers(con: sqlite3.Connection, quelle: str, start: date, ende: date | None) -> bool:
    """Deckt eine frühere Kalibrierung den Zeitraum [start, ende] ab? ende=None heißt 'bis heute'."""
    kal = db.meta_get(con, f"kalibrierung_{quelle}")
    if not kal:
        return False
    k = json.loads(kal)
    if start < date.fromisoformat(k["ab"]):
        return False
    if k["bis"] is None:          # lief bis "heute" – deckt alles danach mit ab
        return True
    return ende is not None and ende <= date.fromisoformat(k["bis"])


def sync_umsaetze(con: sqlite3.Connection, cfg: Config, quelle: str, fetch: Fetch,
                  today: date | None = None, dry_run: bool = False, log=print,
                  start: date | None = None, ende: date | None = None) -> int:
    """Lädt alle fehlenden/offenen Monate einer Quelle ('konto' | 'depot') im Zeitraum
    [start, ende] (Standard: Depotstart bis heute). Gibt die Zahl geladener Monate zurück."""
    today = today or date.today()
    start = start or cfg.depot_start
    ende = clamp_end(ende, today)
    todo = pending_windows(con, quelle, start, ende or today)
    log(f"{quelle}: {len(todo)} Monat(e) zu laden")
    if dry_run:
        for von, bis in todo:
            log(f"  geplant {von}..{bis}")
        return 0
    chk = Checks(cfg.suspect_min_rows, cfg.edge_gap_days, _load_caps(con, quelle),
                 int(db.meta_get(con, f"sicher_bis_{quelle}", "0")))
    # Die Kalibrierung gilt für den Zeitraum, über den sie lief. Wird später ein größerer
    # Zeitraum geladen (z. B. nach Tests mit --monate oder --bis), wird darüber neu kalibriert.
    if todo and not _calibration_covers(con, quelle, start, ende):
        try:
            cap = calibrate(fetch, start, ende or today, chk, log)
        except ActionBudgetExhausted:
            log("Aktionslimit während der Kalibrierung – weiter beim nächsten Lauf.")
            return 0
        if cap:
            _save_cap(con, quelle, cap)
        db.meta_set(con, f"sicher_bis_{quelle}", str(chk.sicher_bis))
        db.meta_set(con, f"kalibrierung_{quelle}", json.dumps(
            {"ab": start.isoformat(), "bis": ende.isoformat() if ende else None}))
        con.execute("DELETE FROM meta WHERE key = ?", (f"kalibriert_ab_{quelle}",))  # altes Format
        con.commit()
    raw_dir = cfg.raw_dir / quelle
    raw_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    # Aufeinanderfolgende offene Monate in einem Export holen (Block bis block_monate);
    # die Prüfungen in fetch_complete halbieren, falls ein Block doch gekürzt ist.
    for block in bloecke(todo, cfg.block_monate):
        bvon, bbis = block[0][0], block[-1][1]
        try:
            pieces = fetch_complete(fetch, bvon, bbis, chk, log, on_cap=lambda n: _save_cap(con, quelle, n))
        except ActionBudgetExhausted:
            log(f"Aktionslimit erreicht – weiter beim nächsten Lauf ({quelle} ab {bvon}).")
            break
        dateien = []
        for p in pieces:
            path = raw_dir / f"{_datei_stamm(p.von, p.bis)}.{p.res.ext}"
            _alte_rohdateien_entfernen(raw_dir, p.von, p.bis, behalten=path.name)
            path.write_bytes(p.res.raw)
            dateien.append(path)
            store.replace_range(con, quelle, p.von, p.bis, p.res.rows, str(path.relative_to(cfg.data_dir)))
        alle = [r for p in pieces for r in p.res.rows]
        for von, bis in block:
            zeilen = sum(1 for r in alle if von <= r.buchtag <= bis)
            nominal_bis = _nominal_end(von, 1)
            status = "abgeschlossen" if is_closed(nominal_bis, today, cfg.closed_after_days) else "offen"
            con.execute(
                "INSERT OR REPLACE INTO sync_fenster VALUES (?,?,?,?,?,?,?,?)",
                (quelle, von.isoformat(), nominal_bis.isoformat(), status, datetime.now().isoformat(timespec="seconds"),
                 zeilen, ", ".join(p.name for p in dateien),
                 hashlib.sha256(b"".join(p.read_bytes() for p in dateien)).hexdigest()),
            )
            done += 1
        con.commit()
        log(f"  {quelle} {bvon:%m/%Y}–{bbis:%m/%Y}: {len(alle)} Zeilen in {len(block)} Monat(en), "
            f"{len(pieces)} Export(e)")
    return done


def bloecke(todo: list[tuple[date, date]], max_monate: int) -> list[list[tuple[date, date]]]:
    """Gruppiert offene Monate zu Blöcken aufeinanderfolgender Monate (neueste Blöcke zuerst)."""
    monate = sorted(todo)
    out: list[list[tuple[date, date]]] = []
    for von, bis in monate:
        if out and len(out[-1]) < max_monate and out[-1][-1][1] + timedelta(days=1) == von:
            out[-1].append((von, bis))
        else:
            out.append([(von, bis)])
    return list(reversed(out))


def _datei_stamm(von: date, bis: date) -> str:
    if von.day == 1 and bis == month_end(von):
        return f"{von:%Y-%m}"
    return f"{von:%Y-%m-%d}_{bis:%Y-%m-%d}"


def rohdatei_bereich(stem: str) -> tuple[date, date] | None:
    """Zeitraum einer Rohdatei aus ihrem Namen: '2024-03', '2024-03_01-15' (alt) oder '2024-01-01_2024-12-31'."""
    import re

    if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", stem):
        return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
    if m := re.fullmatch(r"(\d{4})-(\d{2})(?:_(\d{2})-(\d{2}))?", stem):
        y, mo = int(m.group(1)), int(m.group(2))
        von = date(y, mo, int(m.group(3) or 1))
        return von, (date(y, mo, int(m.group(4))) if m.group(4) else month_end(von))
    return None


def _alte_rohdateien_entfernen(raw_dir: Path, von: date, bis: date, behalten: str) -> None:
    """Ältere Rohdateien, deren Zeitraum vollständig im neuen Export liegt, sind überholt."""
    for f in raw_dir.iterdir():
        r = rohdatei_bereich(f.stem)
        if f.name != behalten and r and von <= r[0] and r[1] <= bis:
            f.unlink()


# --- Postfach-Sync --------------------------------------------------------------

def _doc_path(cfg: Config, datum: date, name: str, nr: int, portal_name: str) -> Path:
    stem = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in name).strip() or Path(portal_name).stem
    stem = stem[:80]
    suffix = f"_{nr}" if nr > 1 else ""
    return cfg.raw_dir / "pdfs" / f"{datum:%Y}" / f"{datum:%Y-%m-%d}_{stem}{suffix}.pdf"


def sync_postfach(con: sqlite3.Connection, cfg: Config, postfach, throttle,
                  today: date | None = None, dry_run: bool = False, log=print,
                  start: date | None = None, ende: date | None = None) -> int:
    """Listet Postfach-Fenster und lädt nur Dokumente, die noch nicht in `dokumente` stehen."""
    today = today or date.today()
    months = cfg.postfach_window_months
    ende = clamp_end(ende, today)
    todo = pending_windows(con, "postfach", start or cfg.depot_start, ende or today, months)
    log(f"postfach: {len(todo)} Fenster zu prüfen")
    if dry_run:
        for von, bis in todo:
            log(f"  geplant {von}..{bis}")
        return 0
    neu = 0
    for von, bis in todo:
        try:
            throttle.action()
            docs = postfach.list(von, bis)
            counter: dict[tuple, int] = {}
            missing = []
            for d in docs:
                datum = d.datum or von
                key = (datum.isoformat(), d.name)
                counter[key] = counter.get(key, 0) + 1
                nr = counter[key]
                if not con.execute("SELECT 1 FROM dokumente WHERE datum=? AND name=? AND nr=?",
                                   (key[0], d.name, nr)).fetchone():
                    missing.append((d, datum, nr))
            log(f"  postfach {von}..{bis}: {len(docs)} Dokument(e), {len(missing)} neu")
            for i, (d, datum, nr) in enumerate(missing, 1):
                throttle.action()
                # Die Liste dieses Fensters ist gerade offen -> direkt anklicken (Fallback eingebaut)
                portal_name, content = postfach.download(von, bis, d.index, direkt=True)
                log(f"    [{i}/{len(missing)}] {datum:%d.%m.%Y} {d.name}")
                path = _doc_path(cfg, datum, d.name, nr, portal_name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                con.execute(
                    "INSERT INTO dokumente(datum, name, nr, pfad, sha256, geladen_am) VALUES (?,?,?,?,?,?)",
                    (datum.isoformat(), d.name, nr, str(path.relative_to(cfg.data_dir)),
                     hashlib.sha256(content).hexdigest(), datetime.now().isoformat(timespec="seconds")),
                )
                con.commit()
                neu += 1
        except ActionBudgetExhausted:
            log(f"Aktionslimit erreicht – weiter beim nächsten Lauf (postfach ab {von}).")
            break
        nominal_bis = _nominal_end(von, months)
        complete = bis == nominal_bis  # durch --bis abgeschnittene Fenster bleiben offen
        status = "abgeschlossen" if complete and is_closed(nominal_bis, today, cfg.closed_after_days) else "offen"
        con.execute(
            "INSERT OR REPLACE INTO sync_fenster VALUES (?,?,?,?,?,?,?,?)",
            ("postfach", von.isoformat(), nominal_bis.isoformat(), status,
             datetime.now().isoformat(timespec="seconds"), len(docs), None, None),
        )
        con.commit()
    return neu
