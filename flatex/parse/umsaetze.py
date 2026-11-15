"""Konto-/Depotumsätze aus flatex CSV/XLSX in einheitliche Zeilen.

Die Spaltennamen werden über Aliase erkannt. Unbekannte Spalten gehen nicht
verloren, sondern landen in `raw`. Sobald echte Beispielexporte vorliegen,
werden die Aliase daran geschärft.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ALIASES: dict[str, tuple[str, ...]] = {
    "buchtag": ("buchtag", "buchungstag", "buchungsdatum", "datum", "buchung"),
    "valuta": ("valuta", "valutadatum", "wertstellung", "valutatag"),
    "betrag": ("betrag", "umsatz", "betrag in eur", "betrag (eur)", "betrag eur", "kurswert"),
    "waehrung": ("währung", "waehrung", "whg", "whg."),
    "text": ("buchungsinformation", "buchungsinformationen", "buchungstext", "verwendungszweck",
             "text", "buchungsinfo", "beschreibung"),
    "empfaenger": ("empfänger", "auftraggeber/empfänger", "empfänger/auftraggeber"),
    "ta_nr": ("ta.nr.", "ta-nr.", "ta.-nr.", "ta.nr", "ta nr", "transaktionsnummer"),
    "devisenkurs": ("devisenkurs",),
    "saldo": ("saldo", "kontostand", "saldo in eur"),
    "isin": ("isin",),
    "bezeichnung": ("bezeichnung", "wertpapier", "wertpapierbezeichnung", "titel"),
    "stueck": ("nominal", "nominal (stk.)", "stück", "stueck", "anzahl", "menge", "stk."),
    "kurs": ("kurs", "preis", "ausführungskurs"),
}
_LOOKUP = {a: k for k, al in ALIASES.items() for a in al}

# flatex-Exporte haben Spalten ohne Überschrift direkt hinter Wertspalten:
#   Konto: Betrag;<Währung>      Depot: Nominal (Stk.);<Einheit>;Betrag;<Währung>;Kurs;<Kurswährung>
UNNAMED_AFTER = {"betrag": ("waehrung", "Währung"), "stueck": (None, "Einheit"), "kurs": ("kurs_waehrung", "Kurswährung")}


@dataclass
class Row:
    art: str                  # "konto" | "depot"
    buchtag: date
    valuta: date | None = None
    betrag_cent: int | None = None
    waehrung: str | None = None
    text: str | None = None
    saldo_cent: int | None = None
    isin: str | None = None
    bezeichnung: str | None = None
    stueck: float | None = None
    kurs: float | None = None
    kurs_waehrung: str | None = None
    devisenkurs: float | None = None
    ta_nr: str | None = None
    empfaenger: str | None = None
    raw: dict = field(default_factory=dict)
    row_hash: str = ""


def parse_number(v) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip().replace("\xa0", "").replace(" ", "")
    s = re.sub(r"(EUR|USD|CHF|GBP|€|%)$", "", s, flags=re.I)
    if not s or s in ("-", "--"):
        return None
    if "," in s:  # deutsches Format: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _cent(d: Decimal | None) -> int | None:
    return None if d is None else int((d * 100).quantize(Decimal("1")))


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def _table_from_bytes(raw: bytes, ext: str) -> list[list]:
    if ext == "xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";"
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim)]


def _norm(h) -> str:
    return re.sub(r"\s+", " ", str(h or "")).strip().lower()


def _find_header(table: list[list]) -> int:
    for i, r in enumerate(table[:30]):
        hits = sum(1 for c in r if _norm(c) in _LOOKUP)
        if hits >= 2 and any(_LOOKUP.get(_norm(c)) == "buchtag" for c in r):
            return i
    raise ValueError("Keine Kopfzeile mit Buchungsdatum gefunden – unbekanntes Exportformat.")


def parse_bytes(raw: bytes, ext: str, art: str | None = None) -> list[Row]:
    if not raw.strip():
        return []  # leerer Monat (flatex liefert dann keine Datei; wir speichern eine leere)
    table = _table_from_bytes(raw, ext.lower().lstrip("."))
    hi = _find_header(table)
    header = [str(c).strip() if c not in (None, "") else f"spalte{j}" for j, c in enumerate(table[hi])]
    keys = [_LOOKUP.get(_norm(h)) for h in header]
    for j in range(1, len(keys)):
        prev = keys[j - 1]
        if keys[j] is None and header[j].startswith("spalte") and prev in UNNAMED_AFTER:
            key, name = UNNAMED_AFTER[prev]
            if key and key in keys:
                continue
            keys[j] = key
            header[j] = name
    if art is None:
        art = "depot" if ("isin" in keys or "stueck" in keys) else "konto"

    rows: list[Row] = []
    for r in table[hi + 1:]:
        if not r or all(c in (None, "") for c in r):
            continue
        rec = {header[j]: (r[j] if j < len(r) else None) for j in range(len(header))}
        val = {keys[j]: (r[j] if j < len(r) else None) for j in range(len(header)) if keys[j]}
        bt = parse_date(val.get("buchtag"))
        if bt is None:
            continue  # Summen-/Fußzeilen
        stk = parse_number(val.get("stueck"))
        kurs = parse_number(val.get("kurs"))
        rows.append(Row(
            art=art,
            buchtag=bt,
            valuta=parse_date(val.get("valuta")),
            betrag_cent=_cent(parse_number(val.get("betrag"))),
            waehrung=(str(val["waehrung"]).strip() or None) if val.get("waehrung") else None,
            text=(str(val["text"]).strip() or None) if val.get("text") else None,
            saldo_cent=_cent(parse_number(val.get("saldo"))),
            isin=(str(val["isin"]).strip().upper() or None) if val.get("isin") else None,
            bezeichnung=(str(val["bezeichnung"]).strip() or None) if val.get("bezeichnung") else None,
            stueck=float(stk) if stk is not None else None,
            kurs=float(kurs) if kurs is not None else None,
            kurs_waehrung=_s(val.get("kurs_waehrung")),
            devisenkurs=_f(parse_number(val.get("devisenkurs"))),
            ta_nr=_s(val.get("ta_nr")),
            empfaenger=_s(val.get("empfaenger")),
            raw={k: _jsonable(v) for k, v in rec.items()},
        ))
    _assign_hashes(rows)
    return rows


def parse_file(path: Path, art: str | None = None) -> list[Row]:
    return parse_bytes(path.read_bytes(), path.suffix, art)


def _f(d: Decimal | None) -> float | None:
    return float(d) if d is not None else None


def _s(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # XLSX liefert Nummern als float
    return str(v).strip() or None


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def _assign_hashes(rows: list[Row]) -> None:
    """Stabile Zeilen-ID. Identische Zeilen (z. B. zwei gleiche Sparplan-Käufe am selben Tag)
    bekommen eine laufende Nummer, damit sie nicht zusammenfallen."""
    seen: dict[str, int] = {}
    for r in rows:
        core = json.dumps(
            [r.art, r.buchtag.isoformat(), r.valuta and r.valuta.isoformat(), r.betrag_cent,
             r.text, r.isin, r.stueck, r.ta_nr],
            ensure_ascii=False,
        )
        n = seen.get(core, 0)
        seen[core] = n + 1
        r.row_hash = hashlib.sha256(f"{core}#{n}".encode()).hexdigest()[:32]
