"""Befehlszeile: python -m flatex <befehl>"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from flatex import config, db, store


def cmd_setup(cfg, args) -> int:
    from flatex.pdfs import install_pdf_cli

    install_pdf_cli(cfg)
    db.connect(cfg.db_path).close()
    print(f"Datenbank: {cfg.db_path}")
    return 0


def cmd_login(cfg, args) -> int:
    from flatex import credentials

    credentials.store_interactive()
    return 0


def cmd_import(cfg, args) -> int:
    from flatex.parse.umsaetze import parse_file

    con = db.connect(cfg.db_path)
    files = [p for p in Path(args.pfad).rglob("*") if p.suffix.lower() in (".csv", ".xlsx")] \
        if Path(args.pfad).is_dir() else [Path(args.pfad)]
    for f in sorted(files):
        try:
            rows = parse_file(f, args.art)
        except ValueError as e:
            print(f"übersprungen {f.name}: {e}")
            continue
        neu = store.upsert(con, rows, str(f))
        art = rows[0].art if rows else "?"
        print(f"{f.name}: {len(rows)} Zeilen ({art}), {neu} neu")
    con.commit()
    return 0


def cmd_sync(cfg, args) -> int:
    from flatex import sync

    con = db.connect(cfg.db_path)
    # Postfach-PDFs enthalten sensible Dokumente -> nur auf ausdrücklichen Wunsch
    quellen = args.nur or (["konto", "depot", "postfach"] if cfg.postfach_automatisch else ["konto", "depot"])
    start = sync.start_for_months(date.today(), args.monate, cfg.depot_start)
    if args.von:
        start = max(date.fromisoformat(args.von), cfg.depot_start)
    ende = date.fromisoformat(args.bis) if args.bis else None
    if args.monate or args.von or args.bis:
        e = sync.clamp_end(ende, date.today())
        print(f"Zeitraum: {start} bis {e or 'heute'}")
    if args.dry_run:
        for q in quellen:
            if q == "postfach":
                sync.sync_postfach(con, cfg, None, None, dry_run=True, start=start, ende=ende)
            else:
                sync.sync_umsaetze(con, cfg, q, None, dry_run=True, start=start, ende=ende)
        return 0

    from flatex.runner import run_sync

    erg = run_sync(cfg, quellen, start, ende, max_aktionen=args.max, debug=args.debug,
                   postfach_neu_pruefen=args.postfach_neu, geloeschte_neu_laden=args.geloeschte_neu_laden)
    if erg.status == "keine_zugangsdaten":
        print("Keine Login-Daten gespeichert. Bitte zuerst: python -m flatex login")
        return 1
    if erg.status == "blockiert":
        print(f"ABBRUCH: {erg.nachricht}")
        return 2
    if erg.status == "fehler":
        print(f"Fehler: {erg.nachricht}")
        if not args.debug:
            print("Tipp: mit --debug erneut starten, dann werden die Server-Antworten gespeichert.")
        return 1
    return 0


def cmd_probe(cfg, args) -> int:
    """Ein einzelner Test-Export mit Debug-Ablage – schreibt nichts in die Datenbank."""
    from datetime import datetime

    from flatex import credentials
    from flatex.portal.exports import UmsatzExporter
    from flatex.portal.session import PortalBlocked, PortalError, Session, Throttle

    von = date.fromisoformat(args.von)
    bis = date.fromisoformat(args.bis)
    debug_dir = cfg.data_dir / "erkunden" / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    throttle = Throttle(cfg.request_delay, cfg.action_pause, max_actions=2)
    user, pw = credentials.load()
    try:
        with Session(cfg.domain, throttle, debug_dir=debug_dir) as s:
            s.login(user, pw)
            throttle.action()
            res = UmsatzExporter(s).export(args.quelle, von, bis)
    except PortalBlocked as e:
        print(f"ABBRUCH: {e}")
        return 2
    except (PortalError, ValueError) as e:
        print(f"Fehler: {e}")
        print(f"Server-Antworten zum Nachsehen: {debug_dir}")
        return 1
    out = debug_dir / f"export_{args.quelle}_{von}_{bis}.{res.ext}"
    out.write_bytes(res.raw)
    print(f"Export ok: {len(res.rows)} Zeilen ({res.ext}), Datei: {out}")
    for r in res.rows[:3]:
        print(f"  {r.buchtag} {r.betrag_cent} {r.isin or ''} {r.text or ''}")
    if res.rows:
        print(f"  Spalten: {', '.join(res.rows[0].raw.keys())}")
    print(f"Server-Antworten: {debug_dir}")
    return 0


def cmd_startdatum(cfg, args) -> int:
    """Ältestes Postfach-Dokument = Kontoeröffnung. Fragt nur den Zeitraum bis --bis ab."""
    import re

    from flatex import config as config_mod
    from flatex import credentials
    from flatex.portal.postfach import Postfach
    from flatex.portal.session import PortalBlocked, PortalError, Session, Throttle

    from datetime import datetime

    bis = date.fromisoformat(args.bis) if args.bis else date.today()
    von = date.fromisoformat(args.von)
    debug_dir = cfg.data_dir / "erkunden" / datetime.now().strftime("%Y-%m-%d_%H%M%S_startdatum")
    throttle = Throttle(cfg.request_delay, cfg.action_pause, max_actions=1)
    user, pw = credentials.load()
    print(f"Suche Postfach {von}..{bis}; Server-Antworten: {debug_dir}")
    try:
        with Session(cfg.domain, throttle, debug_dir=debug_dir) as s:
            s.login(user, pw)
            throttle.action()
            docs = Postfach(s).list(von, bis)
    except PortalBlocked as e:
        print(f"ABBRUCH: {e}")
        return 2
    except PortalError as e:
        print(f"Fehler: {e}")
        return 1
    dated = sorted((d for d in docs if d.datum), key=lambda d: d.datum)
    if not dated:
        print(f"Keine Dokumente bis {bis} gefunden – --bis später setzen.")
        return 1
    first = dated[0]
    print(f"{len(dated)} Dokument(e) bis {bis}. Ältestes: {first.datum} – {first.name}")
    for d in dated[1:4]:
        print(f"  danach: {d.datum} – {d.name}")
    path = config_mod.ROOT / "config.toml"
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'^depot_start\s*=.*$', f'depot_start = "{first.datum.isoformat()}"', text, count=1, flags=re.M)
    path.write_text(new, encoding="utf-8")
    print(f"config.toml: depot_start = {first.datum}")
    return 0


def cmd_neu_einlesen(cfg, args) -> int:
    """Liest alle Rohdateien in data/raw/{konto,depot} neu ein – ohne Portal-Anfrage."""
    from flatex.parse.umsaetze import parse_file
    from flatex.sync import rohdatei_bereich

    con = db.connect(cfg.db_path)
    for quelle in ("konto", "depot"):
        total = 0
        # älteste zuerst, damit neuere Exporte desselben Zeitraums gewinnen
        for f in sorted((cfg.raw_dir / quelle).glob("*.*"), key=lambda p: p.stat().st_mtime):
            r = rohdatei_bereich(f.stem)
            if not r:
                continue
            von, bis = r
            rows = parse_file(f, quelle)
            total += store.replace_range(con, quelle, von, bis, rows, str(f.relative_to(cfg.data_dir)))
        print(f"{quelle}: {total} Zeilen neu eingelesen")
    con.commit()
    return 0


def cmd_kurse(cfg, args) -> int:
    """Tageskurse von Yahoo Finance laden (nur fehlende Tage) und gegen flatex-Kurse prüfen."""
    from flatex import kurse

    con = db.connect(cfg.db_path)
    kurse.connect_schema(con)
    if args.nur_pruefen:
        kurse.pruefen(con)
        return 0
    print("Lade Kurse (Yahoo Finance) …")
    kurse.update(con, kurse.load_overrides(cfg.securities))
    kurse.klassifizieren(con, kurse.load_typ_overrides(cfg.securities))
    kurse.dividenden_laden(con)
    rows = con.execute(
        "SELECT w.isin, w.bezeichnung, w.ticker, w.waehrung, w.quelle, w.abweichung, "
        "(SELECT MAX(datum) FROM kurse k WHERE k.isin = w.isin) FROM wertpapiere w ORDER BY w.bezeichnung"
    ).fetchall()
    print(f"\n{'Wertpapier':30s} {'Ticker':14s} Whg  bis         Abw.")
    for isin, name, ticker, cur, quelle, abw, last in rows:
        flag = "" if quelle == "auto" else " (manuell)"
        abw_s = f"{abw:5.1%}" if abw is not None else "  –  "
        print(f"{(name or isin)[:30]:30s} {(ticker or 'Ersatzkurs')[:14]:14s} {cur or '':4s} {last or '–':11s} {abw_s}{flag}")
    return 0


def cmd_web(cfg, args) -> int:
    """Web-App: baut das Frontend bei Bedarf und startet die lokale API (nur localhost)."""
    import shutil
    import subprocess
    import threading
    import webbrowser

    web = config.ROOT / "web"
    dist = web / "dist" / "index.html"
    quellen = list((web / "src").rglob("*")) if (web / "src").exists() else []   # im Container nur dist/
    src_neuer = dist.exists() and bool(quellen) and max(p.stat().st_mtime for p in quellen) > dist.stat().st_mtime
    if args.build or not dist.exists() or src_neuer:
        npm = shutil.which("npm")
        if not npm:
            print("npm nicht gefunden – bitte Node.js installieren.")
            return 1
        if not (web / "node_modules").exists():
            subprocess.check_call([npm, "install", "--no-audit", "--no-fund"], cwd=web)
        print("Baue Frontend …")
        subprocess.check_call([npm, "run", "build"], cwd=web)

    import uvicorn

    url = f"http://localhost:{args.port}"
    print(f"Flatex Terminal läuft auf {url}  (Beenden mit Strg+C)")
    if not args.kein_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("flatex.api:app", host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_pdfs(cfg, args) -> int:
    from flatex import pdfs

    con = db.connect(cfg.db_path)
    if args.pfad:
        n = 0
        for f in sorted(Path(args.pfad).rglob("*.pdf")):
            k = pdfs.ingest_pdf(con, cfg, f)
            print(f"{f.name}: {k} Transaktion(en)")
            n += k
        con.commit()
    else:
        pdfs.ingest_pending(con, cfg)
    return 0


def cmd_status(cfg, args) -> int:
    from flatex.sync import pending_windows

    con = db.connect(cfg.db_path)
    today = date.today()
    for q, months in (("konto", 1), ("depot", 1), ("postfach", cfg.postfach_window_months)):
        rows = con.execute(
            "SELECT status, COUNT(*) n, MAX(geladen_am) last FROM sync_fenster WHERE quelle=? GROUP BY status", (q,)
        ).fetchall()
        offen = len(pending_windows(con, q, cfg.depot_start, today, months))
        info = ", ".join(f"{r['n']} {r['status']}" for r in rows) or "noch nichts geladen"
        print(f"{q:9s} {info}; {offen} Fenster ausstehend")
    for t in ("konto_umsaetze", "depot_umsaetze", "dokumente", "pdf_transaktionen"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t:18s} {n} Einträge")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flatex", description="flatex.at Depot herunterladen und auswerten")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="flatex-pdf-cli installieren, Datenbank anlegen")
    sub.add_parser("login", help="Zugangsdaten im Windows Credential Manager speichern")
    p = sub.add_parser("import", help="manuell exportierte CSV/XLSX importieren")
    p.add_argument("pfad")
    p.add_argument("--art", choices=["konto", "depot"], help="Art erzwingen (sonst automatisch)")
    p = sub.add_parser("sync", help="neue Daten vom Portal laden (schonend, inkrementell)")
    p.add_argument("--dry-run", action="store_true", help="nur anzeigen, was geladen würde")
    p.add_argument("--nur", nargs="+", choices=["konto", "depot", "postfach"])
    p.add_argument("--max", type=int, help="max. Aktionen in diesem Lauf")
    p.add_argument("--debug", action="store_true", help="Server-Antworten in data/erkunden/ ablegen")
    p.add_argument("--postfach-neu", action="store_true",
                   help="alle Postfach-Zeiträume neu auflisten (lädt nur fehlende Dokumente)")
    p.add_argument("--geloeschte-neu-laden", action="store_true",
                   help="lokal gelöschte PDFs erneut herunterladen (sonst bleiben sie bewusst weg)")
    p.add_argument("--monate", type=int, help="nur laufenden Monat + (N-1) Vormonate laden (zum Testen)")
    p.add_argument("--von", help="erst ab diesem Datum laden (YYYY-MM-DD)")
    p.add_argument("--bis", help="nur bis zu diesem Monat laden (YYYY-MM-DD, wird aufs Monatsende gerundet)")
    p = sub.add_parser("startdatum", help="Depotstart aus dem ältesten Postfach-Dokument ermitteln")
    p.add_argument("--bis", help="nur Dokumente bis zu diesem Datum abfragen (YYYY-MM-DD), spart Anfragen")
    p.add_argument("--von", default="2020-01-01", help="Suchbeginn (YYYY-MM-DD), Standard 2020-01-01")
    p = sub.add_parser("probe", help="ein einzelner Test-Export (ohne Datenbank), mit Debug-Ablage")
    p.add_argument("quelle", choices=["konto", "depot"])
    p.add_argument("--von", required=True, help="YYYY-MM-DD")
    p.add_argument("--bis", required=True, help="YYYY-MM-DD")
    p = sub.add_parser("pdfs", help="PDFs auswerten (neue aus dem Postfach, oder einen Ordner)")
    p.add_argument("pfad", nargs="?")
    sub.add_parser("status", help="Stand der Daten anzeigen")
    sub.add_parser("neu-einlesen", help="geladene Rohdateien neu in die Datenbank einlesen (ohne Portal)")
    p = sub.add_parser("kurse", help="Tageskurse laden (Yahoo Finance) und gegen flatex-Kurse prüfen")
    p.add_argument("--nur-pruefen", action="store_true", help="keine Downloads, nur die Prüfung wiederholen")
    p = sub.add_parser("web", help="Web-App starten (http://localhost:8600)")
    p.add_argument("--port", type=int, default=8600)
    p.add_argument("--host", default="127.0.0.1",
                   help="Adresse (Standard nur localhost; im Docker-Container 0.0.0.0, Freigabe über -p 127.0.0.1:…)")
    p.add_argument("--build", action="store_true", help="Frontend neu bauen")
    p.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = ap.parse_args(argv)
    cfg = config.load()
    if args.cmd not in ("setup", "login"):
        from flatex.einstellungen import wirksame_config

        cfg = wirksame_config(cfg, db.connect(cfg.db_path))   # Depotstart aus der Web-App gilt auch hier
    handler = {"setup": cmd_setup, "login": cmd_login, "import": cmd_import, "sync": cmd_sync,
               "pdfs": cmd_pdfs, "status": cmd_status, "probe": cmd_probe,
               "startdatum": cmd_startdatum, "neu-einlesen": cmd_neu_einlesen,
               "kurse": cmd_kurse, "web": cmd_web}[args.cmd]
    return handler(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
