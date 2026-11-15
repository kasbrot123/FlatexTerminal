"""PDF-Auswertung über flatex-pdf-cli (Go-Binary, offline) und Einrichtung des Binaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

import httpx

from flatex.config import Config

PDF_CLI_VERSION = "v0.8.2"
_RELEASE = f"https://github.com/welworx/flatex-pdf-cli/releases/download/{PDF_CLI_VERSION}"
_ASSET = "flatex-pdf-cli_windows_amd64.exe"


def install_pdf_cli(cfg: Config, log=print) -> Path:
    """Lädt das Windows-Binary und prüft es gegen SHA256SUMS.txt der Release."""
    target = cfg.pdf_cli
    if target.exists():
        log(f"flatex-pdf-cli vorhanden: {target}")
        return target
    with httpx.Client(follow_redirects=True, timeout=120) as h:
        sums = h.get(f"{_RELEASE}/SHA256SUMS.txt").raise_for_status().text
        expected = next((ln.split()[0] for ln in sums.splitlines() if ln.strip().endswith(_ASSET)), None)
        if not expected:
            raise RuntimeError("Prüfsumme für das Windows-Binary nicht gefunden")
        data = h.get(f"{_RELEASE}/{_ASSET}").raise_for_status().content
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError(f"Prüfsumme stimmt nicht ({actual} != {expected}) – Binary verworfen")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    log(f"flatex-pdf-cli {PDF_CLI_VERSION} installiert (SHA256 ok): {target}")
    return target


def parse_pdf(cfg: Config, pdf: Path) -> list[dict] | None:
    """JSON-Transaktionen eines PDFs, oder None, wenn der Dokumenttyp nicht unterstützt wird."""
    proc = subprocess.run(
        [str(cfg.pdf_cli), "-format", "json", "-quiet", str(pdf)],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    data = json.loads(proc.stdout)
    return data if isinstance(data, list) else data.get("transactions", [])


def _costs_total(tx: dict) -> float | None:
    c = tx.get("costs")
    return c.get("total") if isinstance(c, dict) else None


def ingest_pdf(con: sqlite3.Connection, cfg: Config, pdf: Path) -> int:
    rel = str(pdf.relative_to(cfg.data_dir)) if pdf.is_relative_to(cfg.data_dir) else str(pdf)
    txs = parse_pdf(cfg, pdf)
    con.execute("DELETE FROM pdf_transaktionen WHERE pfad = ?", (rel,))
    for i, tx in enumerate(txs or []):
        con.execute(
            "INSERT INTO pdf_transaktionen (pfad, pos, document_type, isin, trade_date, booking_date, "
            "value_date, quantity, net_amount, net_currency, costs_total, json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rel, i, tx.get("document_type"), tx.get("isin"), tx.get("trade_date"), tx.get("booking_date"),
             tx.get("value_date"), tx.get("quantity"), tx.get("net_amount"), tx.get("net_currency"),
             _costs_total(tx), json.dumps(tx, ensure_ascii=False)),
        )
    con.execute("UPDATE dokumente SET geparst = 1 WHERE pfad = ?", (rel,))
    return len(txs or [])


def entfernte_bereinigen(con: sqlite3.Connection, cfg: Config, log=print) -> int:
    """PDFs, die der Nutzer gelöscht hat: ausgelesene Daten entfernen. Der Eintrag in
    `dokumente` bleibt, damit das Dokument nicht erneut heruntergeladen wird."""
    weg = [p for (p,) in con.execute("SELECT pfad FROM dokumente WHERE pfad IS NOT NULL")
           if not (cfg.data_dir / p).exists()]
    for p in weg:
        con.execute("DELETE FROM pdf_transaktionen WHERE pfad = ?", (p,))
        con.execute("UPDATE dokumente SET geparst = 1, sha256 = NULL WHERE pfad = ?", (p,))
    if weg:
        con.commit()
        log(f"{len(weg)} gelöschte PDF(s): ausgelesene Daten entfernt, werden nicht erneut geladen")
    return len(weg)


def ingest_pending(con: sqlite3.Connection, cfg: Config, log=print) -> int:
    entfernte_bereinigen(con, cfg, log)
    rows = con.execute("SELECT pfad FROM dokumente WHERE geparst = 0 AND pfad IS NOT NULL").fetchall()
    total = 0
    for r in rows:
        n = ingest_pdf(con, cfg, cfg.data_dir / r["pfad"])
        total += n
    con.commit()
    log(f"PDFs ausgewertet: {len(rows)} Datei(en), {total} Transaktion(en)")
    return total
