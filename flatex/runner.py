"""Ein Sync-Lauf (Konto, Depot, optional Postfach) plus Kurse – gemeinsam für Konsole und Web-App."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx

from flatex import db, sync
from flatex.config import Config


@dataclass
class Ergebnis:
    status: str            # ok | blockiert | fehler | abgebrochen | keine_zugangsdaten
    nachricht: str = ""
    aktionen: int = 0
    anfragen: int = 0


@dataclass
class Fortschritt:
    """Wird während des Laufs aktualisiert – die Web-App liest es aus."""
    schritt: str = ""
    aktionen: int = 0
    anfragen: int = 0
    log: list[str] = field(default_factory=list)

    def add(self, zeile: str) -> None:
        self.log.append(f"{datetime.now():%H:%M:%S}  {zeile.strip()}")
        del self.log[:-400]   # nur die letzten Zeilen behalten


def run_sync(cfg: Config, quellen: list[str], start: date | None = None, ende: date | None = None,
             max_aktionen: int | None = None, debug: bool = False, kurse_laden: bool = False,
             log=print, cancel: threading.Event | None = None,
             fortschritt: Fortschritt | None = None, postfach_neu_pruefen: bool = False,
             geloeschte_neu_laden: bool = False) -> Ergebnis:
    from flatex import credentials, pdfs
    from flatex.portal.exports import UmsatzExporter
    from flatex.portal.postfach import Postfach
    from flatex.portal.session import PortalBlocked, PortalError, Session, SyncAbgebrochen, Throttle

    def schritt(text: str) -> None:
        if fortschritt:
            fortschritt.schritt = text
        log(text)

    start = start or cfg.depot_start
    con = db.connect(cfg.db_path)
    throttle = Throttle(cfg.request_delay, cfg.action_pause, max_aktionen or cfg.max_actions_per_run,
                        burst_every=cfg.burst_every, burst_pause=cfg.burst_pause, cancel=cancel,
                        on_change=(lambda t: _zaehler(fortschritt, t)) if fortschritt else None)
    erg = Ergebnis("ok")
    if quellen:
        if not credentials.vorhanden():
            return Ergebnis("keine_zugangsdaten", "Keine Zugangsdaten gespeichert.")
        user, pw = credentials.load()
        debug_dir = cfg.data_dir / "erkunden" / date.today().isoformat() if debug else None
        try:
            with Session(cfg.domain, throttle, log=log, debug_dir=debug_dir) as s:
                schritt("Anmelden bei flatex …")
                s.login(user, pw)
                exporter = UmsatzExporter(s)
                warnungen: list[str] = []
                for q in quellen:
                    if q == "postfach":
                        if postfach_neu_pruefen:
                            # Fenster neu auflisten; vorhandene Dokumente werden trotzdem nicht erneut geladen
                            n = con.execute("DELETE FROM sync_fenster WHERE quelle='postfach'").rowcount
                            con.commit()
                            log(f"Postfach wird komplett neu geprüft ({n} Zeitfenster zurückgesetzt)")
                        if geloeschte_neu_laden:
                            # Einträge, deren Datei der Nutzer gelöscht hat, vergessen -> werden erneut geladen
                            weg = [p for (p,) in con.execute("SELECT pfad FROM dokumente WHERE pfad IS NOT NULL")
                                   if not (cfg.data_dir / p).exists()]
                            for p in weg:
                                con.execute("DELETE FROM pdf_transaktionen WHERE pfad = ?", (p,))
                                con.execute("DELETE FROM dokumente WHERE pfad = ?", (p,))
                            con.commit()
                            log(f"{len(weg)} gelöschte PDF(s) werden erneut geladen")
                        schritt("Postfach-Dokumente …")
                        pf = Postfach(s)
                        neu = sync.sync_postfach(con, cfg, pf, throttle, start=start, ende=ende, log=log)
                        gesamt = con.execute("SELECT COUNT(*) FROM dokumente").fetchone()[0]
                        log(f"Postfach: {neu} neue Dokumente geladen, {gesamt} insgesamt bekannt")
                        warnungen += pf.warnungen
                        continue
                    schritt({"konto": "Kontoumsätze …", "depot": "Depotumsätze …"}.get(q, q))

                    def fetch(von: date, bis: date, q=q):
                        throttle.action()
                        return exporter.export(q, von, bis)

                    sync.sync_umsaetze(con, cfg, q, fetch, start=start, ende=ende, log=log)
                if warnungen:
                    erg = Ergebnis("ok", f"Fertig, aber {len(warnungen)} Warnung(en) – siehe Protokoll.")
        except SyncAbgebrochen:
            erg = Ergebnis("abgebrochen", "Vom Benutzer abgebrochen – bereits Geladenes bleibt erhalten.")
        except PortalBlocked as e:
            erg = Ergebnis("blockiert", str(e))
        except (PortalError, ValueError) as e:
            erg = Ergebnis("fehler", str(e))
        except httpx.HTTPError as e:   # Netzwerkfehler: lesbare Meldung statt Absturz
            erg = Ergebnis("fehler", f"Netzwerkfehler beim Abruf ({type(e).__name__}) – bitte später erneut versuchen.")
        log(f"Aktionen: {throttle.actions_done}, Anfragen: {throttle.requests_done}")
        if cfg.pdf_cli.exists():
            pdfs.ingest_pending(con, cfg, log=log)
    if kurse_laden and erg.status == "ok":
        from flatex import kurse

        schritt("Kurse und Dividenden (Yahoo Finance) …")
        try:
            kurse.connect_schema(con)
            kurse.update(con, kurse.load_overrides(cfg.securities), log=log)
            kurse.klassifizieren(con, kurse.load_typ_overrides(cfg.securities), log=log)
            kurse.dividenden_laden(con, log=log)
        except Exception as e:  # noqa: BLE001 – Kurse sind optional, der Sync war erfolgreich
            log(f"Kurse konnten nicht vollständig geladen werden: {e}")
    erg.aktionen, erg.anfragen = throttle.actions_done, throttle.requests_done
    if erg.status == "ok" and not erg.nachricht:
        erg.nachricht = "Fertig."
    schritt(erg.nachricht)
    return erg


def _zaehler(f: Fortschritt, t) -> None:
    f.aktionen, f.anfragen = t.actions_done, t.requests_done
