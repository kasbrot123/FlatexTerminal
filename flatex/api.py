"""Lokale JSON-API für das Web-Frontend (nur localhost).

Rechnet ausschließlich mit flatex.analytics / flatex.kurse; das Frontend zeigt nur an.
Start: python -m flatex web
"""

from __future__ import annotations

import math
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from flatex import analytics as a
from flatex import config, db, kurse

cfg = config.load()
app = FastAPI(title="Flatex Terminal", docs_url="/api/docs", openapi_url="/api/openapi.json")
_lock = threading.Lock()
_cache: dict = {}

KATEGORIE_LABEL = {**a.KATEGORIEN, "thesaurierung": "Thesaurierung", "umbuchung": "Depotbuchung"}

_ERLAUBTE_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"} | {
    h.strip() for h in os.environ.get("FLATEX_ALLOWED_HOSTS", "").split(",") if h.strip()}


def _hostname(host: str) -> str:
    """'localhost:8600' -> 'localhost', '[::1]:8600' -> '[::1]'."""
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0]


@app.middleware("http")
async def nur_localhost(request: Request, call_next):
    """Schutz gegen DNS-Rebinding: nur Anfragen an localhost beantworten (auch im Container)."""
    if _hostname(request.headers.get("host", "")) not in _ERLAUBTE_HOSTS:
        return PlainTextResponse("Nur über localhost erreichbar", status_code=403)
    return await call_next(request)


# --- Hilfen ----------------------------------------------------------------------------------

def _con() -> sqlite3.Connection:
    con = db.connect(cfg.db_path)
    kurse.connect_schema(con)
    return con


def _clean(x):
    """NaN/inf -> None, numpy/pandas -> Python, rekursiv."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (pd.Timestamp, date)):
        return x.strftime("%Y-%m-%d")
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            x = x.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def _records(df: pd.DataFrame) -> list[dict]:
    return [_clean(r) for r in df.to_dict(orient="records")]


def _daten_bis(con) -> date:
    row = con.execute("SELECT MAX(buchtag) FROM konto_umsaetze").fetchone()[0]
    return date.fromisoformat(row) if row else date.today()


def _default_bis(con) -> date:
    return min(cfg.auswertung_bis or date.today(), date.today())


def _parse(d: str | None, fallback: date) -> date:
    return date.fromisoformat(d) if d else fallback


def _start(con) -> date:
    """Depotstart: in der Web-App gespeichert > FLATEX_DEPOT_START > config.toml."""
    from flatex.einstellungen import wirksame_config

    return wirksame_config(cfg, con).depot_start


@dataclass
class Kontext:
    bis: date
    voll: a.Daten
    bestand: a.Bestand
    preise: pd.DataFrame
    ersatz: set
    verlauf: pd.DataFrame       # verlauf_markt über die ganze Historie bis `bis`
    typen: dict                 # isin -> Aktie/ETF/Derivat/Sonstige
    namen: dict                 # isin -> Bezeichnung


def _kontext(bis: date) -> Kontext:
    """Ganze Historie bis `bis`, zwischengespeichert bis sich die Datenbank ändert."""
    # Datenbank + WAL-Datei: Schreibvorgänge landen zuerst in der WAL-Datei
    stand = tuple(p.stat().st_mtime_ns if p.exists() else 0
                  for p in (cfg.db_path, cfg.db_path.with_name(cfg.db_path.name + "-wal")))
    key = (bis, stand)
    with _lock:
        if key in _cache:
            return _cache[key]
        con = _con()
        voll = a.load(con, _start(con), bis)
        b = a.bestand(voll)
        preise, ersatz = kurse.preis_tabelle(con, bis)
        v = a.verlauf_markt(voll, preise)
        typen = dict(con.execute("SELECT isin, COALESCE(typ, 'Aktie') FROM wertpapiere").fetchall())
        namen = dict(con.execute("SELECT isin, MAX(bezeichnung) FROM depot_umsaetze GROUP BY isin").fetchall())
        ctx = Kontext(bis, voll, b, preise, ersatz, v, typen, namen)
        _cache.clear()
        _cache[key] = ctx
        return ctx


def _marktwerte_am(ctx: Kontext, tag: date) -> pd.Series:
    mw, _ = a.marktwerte(ctx.voll, ctx.preise, ctx.bestand)
    if mw.empty:
        return pd.Series(dtype=float)
    return mw.loc[:pd.Timestamp(tag)].iloc[-1]


# --- Endpunkte --------------------------------------------------------------------------------

@app.get("/api/meta")
def meta():
    con = _con()
    geladen = con.execute(
        "SELECT quelle, COUNT(*), MAX(geladen_am) FROM sync_fenster GROUP BY quelle").fetchall()
    return _clean({
        "depot_start": _start(con),
        "bis_default": _default_bis(con),
        "daten_bis": _daten_bis(con),
        "kurse_bis": con.execute("SELECT MAX(datum) FROM kurse").fetchone()[0],
        "heute": date.today(),
        "hat_daten": con.execute("SELECT COUNT(*) FROM konto_umsaetze").fetchone()[0] > 0,
        "sync": {q: {"fenster": n, "zuletzt": z} for q, n, z in geladen},
    })


@app.get("/api/overview")
def overview(von: str | None = None, bis: str | None = None):
    con = _con()
    b_ = _parse(bis, _default_bis(con))
    start = _start(con)
    v_ = max(_parse(von, start), start)
    ctx = _kontext(b_)
    vm = ctx.verlauf
    teil = vm.loc[pd.Timestamp(v_):pd.Timestamp(b_)]
    vor = vm.loc[:pd.Timestamp(v_) - pd.Timedelta(days=1)]
    ende = vm.iloc[-1]

    # Aufteilung nach Klasse am Ende
    mw_ende = _marktwerte_am(ctx, b_)
    alloc: dict[str, float] = {}
    pos = []
    for isin, wert in mw_ende.items():
        if abs(wert) < 0.005:
            continue
        typ = ctx.typen.get(isin, "Aktie")
        alloc[typ] = alloc.get(typ, 0.0) + float(wert)
        pos.append({"isin": isin, "name": ctx.namen.get(isin, isin), "typ": typ, "wert": float(wert)})
    depotwert = float(ende["depotwert"]) or 1.0
    pos.sort(key=lambda p: -p["wert"])
    for p in pos:
        p["anteil"] = p["wert"] / depotwert * 100

    d = a.load(con, v_, b_)
    k = a.kennzahlen(d)
    real = ctx.bestand.realisiert
    real = real[(real["buchtag"] >= pd.Timestamp(v_)) & (real["buchtag"] <= pd.Timestamp(b_))]
    basis = float(vor["twr_index"].iloc[-1]) if len(vor) else 1.0
    gewinn_vor = float(vor["gewinn"].iloc[-1]) if len(vor) else 0.0

    serie = pd.DataFrame({
        "d": teil.index,
        "vermoegen": teil["vermoegen"].round(2),
        "eingezahlt": teil["einzahlungen_netto"].round(2),
        "depotwert": teil["depotwert"].round(2),
        "cash": teil["kontostand"].round(2),
        "gewinn": (teil["gewinn"] - gewinn_vor).round(2),
        "rendite": ((teil["twr_index"] / basis - 1) * 100).round(3),
    })
    return _clean({
        "von": v_, "bis": b_,
        "kpi": {
            "vermoegen": ende["vermoegen"], "cash": ende["kontostand"], "depotwert": ende["depotwert"],
            "nach_typ": {t: alloc.get(t, 0.0) for t in kurse.TYPEN},
            "eingezahlt": ende["einzahlungen_netto"], "gewinn_gesamt": ende["gewinn"],
            "einstand": ende["einstand"], "unrealisiert": ende["depotwert"] - ende["einstand"],
            "gewinn_zeitraum": float(ende["gewinn"]) - gewinn_vor,
            "rendite_zeitraum": a.rendite_zeitraum(vm, v_, b_) * 100,
            # Interner Zinsfuß (IZF) = geldgewichtete Rendite p.a.: für den Zeitraum und seit Eröffnung
            "xirr": (lambda x: None if x is None else x * 100)(a.xirr_zeitraum(vm, v_, b_)),
            "izf_gesamt": (lambda x: None if x is None else x * 100)(a.xirr_zeitraum(vm, start, b_)),
            "realisiert": float(real["kursgewinn"].sum()) if len(real) else 0.0,
            "dividenden": k["dividenden"] + k["ausschuettungen"], "zinsen": k["zinsen"],
            "gebuehren": k["kaufgebuehren"], "abzuege_verkauf": k["abzuege_verkauf"],
            "steuer_thesaurierung": k["steuer_thesaurierung"],
            "kaeufe": k["kaeufe"], "verkaeufe": k["verkaeufe"], "positionen": len(pos),
        },
        "serie": _records(serie),
        "aufteilung": [{"typ": t, "wert": alloc[t], "anteil": alloc[t] / depotwert * 100}
                       for t in kurse.TYPEN if alloc.get(t)],
        "positionen": pos,
        "ersatzkurse": sorted(ctx.namen.get(i, i) for i in ctx.ersatz),
    })


@app.get("/api/positions")
def positions(bis: str | None = None):
    con = _con()
    b_ = _parse(bis, _default_bis(con))
    ctx = _kontext(b_)
    offen = a.positionen_markt(ctx.voll, ctx.preise)
    gesamt = float(offen["marktwert"].sum()) or 1.0
    spark_von = pd.Timestamp(b_) - pd.Timedelta(days=90)
    # Anzahl Transaktionen je Wertpapier: Käufe, Verkäufe und Ertragsbuchungen (Dividenden, Ausschüttungen)
    dep = ctx.voll.depot
    kaeufe = dep[dep["art"] == "kauf"].groupby("isin").size()
    verkaeufe = dep[dep["art"] == "verkauf"].groupby("isin").size()
    k = ctx.voll.konto
    ertr = k[k["kategorie"].isin(["dividende", "ausschuettung"])].groupby("isin").size()

    def anzahl(isin: str) -> dict:
        n = {"kaeufe": int(kaeufe.get(isin, 0)), "verkaeufe": int(verkaeufe.get(isin, 0)),
             "ertraege": int(ertr.get(isin, 0))}
        n["transaktionen"] = n["kaeufe"] + n["verkaeufe"] + n["ertraege"]
        return n

    aktiv = []
    for _, r in offen.iterrows():
        s = ctx.preise[r["isin"]].loc[spark_von:pd.Timestamp(b_)].dropna() if r["isin"] in ctx.preise else []
        aktiv.append({
            "isin": r["isin"], "name": r["bezeichnung"], "typ": ctx.typen.get(r["isin"], "Aktie"),
            "stueck": r["stueck"], "kurs": r["kurs"], "durchschnitt": r["durchschnitt"],
            "einstand": r["einstand"], "einstand_steuer": r["einstand_steuer"], "wert": r["marktwert"],
            "gewinn": r["unrealisiert"], "gewinn_pct": r["unrealisiert_pct"],
            "anteil": r["marktwert"] / gesamt * 100, "ersatzkurs": r["isin"] in ctx.ersatz,
            "spark": [round(float(x), 4) for x in list(s)[::3]] if len(s) else [],
            **anzahl(r["isin"]),
        })
    # geschlossene Positionen: alles, was gehandelt wurde, aber nicht mehr im Bestand ist
    geschlossen = []
    offen_isins = set(offen["isin"])
    for isin in sorted(set(ctx.voll.depot["isin"]) - offen_isins):
        p = a.position_detail(ctx.voll, isin, ctx.preise, ctx.bestand)
        geschlossen.append({"isin": isin, "name": p.bezeichnung, "typ": ctx.typen.get(isin, "Aktie"),
                            "gekauft": p.summe["gekauft_eur"], "verkauft": p.summe["verkauft_eur"],
                            "ergebnis": p.summe["ergebnis"], "ergebnis_pct": p.summe["ergebnis_pct"],
                            "letzte": p.buchungen["buchtag"].max(), **anzahl(isin)})
    return _clean({"bis": b_, "aktiv": aktiv, "geschlossen": geschlossen})


@app.get("/api/positions/{isin}")
def position(isin: str, bis: str | None = None):
    con = _con()
    b_ = _parse(bis, _default_bis(con))
    ctx = _kontext(b_)
    if isin not in set(ctx.voll.depot["isin"]):
        raise HTTPException(404, "Unbekannte ISIN")
    p = a.position_detail(ctx.voll, isin, ctx.preise, ctx.bestand)
    w = con.execute("SELECT ticker, waehrung, typ, abweichung FROM wertpapiere WHERE isin=?", (isin,)).fetchone()
    pv = p.verlauf.reset_index()
    bu = p.buchungen.assign(art=p.buchungen["art"].map(
        {"kauf": "Kauf", "verkauf": "Verkauf", "thesaurierung": "Thesaurierung", "sonstige": "Depotbuchung"}))
    er = p.ertraege.assign(kategorie=p.ertraege["kategorie"].map(a.KATEGORIEN))
    return _clean({
        "isin": isin, "name": p.bezeichnung, "typ": ctx.typen.get(isin, "Aktie"),
        "ticker": w[0] if w else None, "waehrung": w[1] if w else None,
        "kurs_abweichung": w[3] if w else None, "ersatzkurs": isin in ctx.ersatz,
        "summe": p.summe,
        "verlauf": _records(pd.DataFrame({
            "d": pv["datum"], "kurs": pv["kurs"].round(4), "wert": pv["marktwert"].round(2),
            "investiert": pv["investiert_netto"].round(2), "stueck": pv["stueck"]})),
        "buchungen": _records(bu.rename(columns={"buchtag": "d"})),
        "ertraege": _records(er.rename(columns={"buchtag": "d"})),
    })


@app.get("/api/transactions")
def transactions(bis: str | None = None):
    """Alle Bewegungen chronologisch: jede Kontobuchung, angereichert mit den Depotdaten derselben
    Order; dazu Depotbuchungen ohne Geldfluss (Thesaurierungs-Umbuchung, Splits)."""
    con = _con()
    b_ = _parse(bis, _default_bis(con))
    ctx = _kontext(b_)
    d = ctx.voll
    tr = a.trades(d).drop_duplicates("order_nr").set_index("order_nr")
    out = []
    for _, r in d.konto.iterrows():
        t = tr.loc[r["order_nr"]] if pd.notna(r["order_nr"]) and r["order_nr"] in tr.index else None
        isin = r["isin"] if pd.notna(r["isin"]) else None
        out.append({
            "id": f"k{r['id']}", "d": r["buchtag"], "valuta": r.get("valuta"),
            "kategorie": KATEGORIE_LABEL.get(r["kategorie"], r["kategorie"]),
            "isin": isin, "name": ctx.namen.get(isin) if isin else None,
            "typ": ctx.typen.get(isin) if isin else None,
            "stueck": None if t is None else abs(float(t["stueck"])),
            "kurs": None if t is None else t["kurs"],
            "betrag": r["betrag"],
            "gebuehr": None if t is None else (t["gebuehr"] if pd.notna(t["gebuehr"]) else t["abzuege_verkauf"]),
            "text": r["text"], "geldfluss": True,
        })
    for _, r in d.depot[d.depot["art"].isin(["thesaurierung", "sonstige"])].iterrows():
        out.append({
            "id": f"d{r['id']}", "d": r["buchtag"], "valuta": r.get("valuta"),
            "kategorie": KATEGORIE_LABEL["thesaurierung" if r["art"] == "thesaurierung" else "umbuchung"],
            "isin": r["isin"], "name": ctx.namen.get(r["isin"]), "typ": ctx.typen.get(r["isin"]),
            "stueck": r["stueck"], "kurs": r.get("kurs"), "betrag": None, "gebuehr": None,
            "text": r["text"], "geldfluss": False,
        })
    out.sort(key=lambda x: (x["d"], x["id"]), reverse=True)
    return _clean({"bis": b_, "transaktionen": out})


@app.get("/api/dividends")
def dividends(bis: str | None = None):
    from flatex import dividenden as dv

    con = _con()
    b_ = _parse(bis, _default_bis(con))
    ctx = _kontext(b_)
    erh = dv.erhalten(ctx.voll, ctx.namen)
    erh["brutto"] = erh["netto"] / (1 - dv.KEST)
    erw = dv.erwartet(con, ctx.voll, ctx.bestand, b_, 12, ctx.namen)
    abg = dv.abgleich(con, ctx.voll, ctx.bestand)
    depotwert = float(ctx.verlauf["depotwert"].iloc[-1]) or None
    ttm = erh[erh["d"] > pd.Timestamp(b_) - pd.DateOffset(months=12)]["netto"].sum()

    monate = pd.date_range(pd.Timestamp(_start(con)).to_period("M").to_timestamp(),
                           pd.Timestamp(b_).to_period("M").to_timestamp(), freq="MS")
    pro_monat = erh.assign(m=erh["d"].dt.to_period("M").dt.to_timestamp()).groupby("m")["netto"].sum() \
        .reindex(monate, fill_value=0.0)
    pro_titel = erh.groupby(["isin", "name"], dropna=False).agg(netto=("netto", "sum"), anzahl=("netto", "size")) \
        .reset_index().sort_values("netto", ascending=False)
    pro_jahr = erh.assign(j=erh["d"].dt.year).groupby("j")["netto"].sum()

    kal = [{"d": r["d"], "isin": r["isin"], "name": r["name"], "netto": r["netto"], "brutto": r["brutto"],
            "status": "erhalten"} for _, r in erh.iterrows()]
    kal += [{"d": r["d"], "ex": r["ex"], "isin": r["isin"], "name": r["name"], "netto": r["netto"],
             "brutto": r["brutto"], "stueck": r["stueck"], "je_stueck": r["je_stueck_eur"],
             "status": "erwartet", "quelle": r["quelle"]} for _, r in erw.iterrows()]
    return _clean({
        "bis": b_,
        "kpi": {
            "gesamt": float(erh["netto"].sum()), "anzahl": len(erh), "ttm": float(ttm),
            "rendite_ttm": float(ttm) / depotwert * 100 if depotwert else None,
            "erwartet_brutto": float(erw["brutto"].sum()), "erwartet_netto": float(erw["netto"].sum()),
            "rendite_erwartet": float(erw["brutto"].sum()) / depotwert * 100 if depotwert else None,
            "abgleich_abweichung": float(abg["abweichung"].abs().median() * 100) if len(abg) else None,
            "abgleich_anzahl": len(abg),
        },
        "pro_monat": [{"m": m, "netto": v} for m, v in pro_monat.items()],
        "pro_jahr": [{"jahr": int(j), "netto": v} for j, v in pro_jahr.items()],
        "pro_titel": _records(pro_titel),
        "kalender": sorted(kal, key=lambda x: x["d"]),
    })


@app.get("/api/taxes")
def taxes(bis: str | None = None):
    from flatex import steuer

    con = _con()
    b_ = _parse(bis, _default_bis(con))
    ctx = _kontext(b_)
    pdf = steuer.pdf_daten(con)
    vk = steuer.veraeusserungen(ctx.voll, pdf)
    er = steuer.ertraege(ctx.voll, pdf)
    letzt = {c: float(ctx.preise[c].dropna().iloc[-1]) for c in ctx.preise.columns if ctx.preise[c].notna().any()}
    offen = steuer.offene_steuerlast(ctx.voll, letzt)
    art_label = {"dividende": "Dividende", "ausschuettung": "Ausschüttung", "zinsen": "Zinsen",
                 "age": "Ausschüttungsgleicher Ertrag"}
    return _clean({
        "bis": b_,
        "satz": round(steuer.KEST * 100, 2),
        "pdf_anzahl": int(len(pdf)),
        "pdf_status": steuer.pdf_status(con, vk, er),
        "jahre": [vars(j) for j in steuer.jahre(vk, er)],
        "verkaeufe": _records(vk),
        "ertraege": _records(er.assign(name=er["isin"].map(ctx.namen), art=er["art"].map(art_label))),
        "offen": _records(offen.sort_values("gewinn")),
        "kest_latent": float(offen["kest_latent"].dropna().sum()),
        "verlust_offen": float(offen.loc[offen["gewinn"] < 0, "gewinn"].sum()),
    })


# --- Daten abrufen (Sync) aus der Web-App -----------------------------------------------------

class _SyncJob:
    """Höchstens ein Lauf gleichzeitig, im Hintergrund-Thread."""

    def __init__(self):
        self.thread: threading.Thread | None = None
        self.cancel = threading.Event()
        self.fortschritt = None
        self.ergebnis = None
        self.gestartet: str | None = None
        self.beendet: str | None = None
        self.optionen: dict = {}

    @property
    def laeuft(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


_job = _SyncJob()


def _nur_lokal(request: Request) -> None:
    """Auslösende Anfragen nur aus der eigenen Oberfläche: eigener Header (blockt fremde Webseiten
    per CORS-Preflight) und Origin/Host = localhost."""
    if request.headers.get("x-flatex-terminal") != "1":
        raise HTTPException(403, "Nur aus der Flatex-Terminal-Oberfläche erlaubt")
    origin = request.headers.get("origin")
    if origin and not any(origin.startswith(p) for p in ("http://localhost", "http://127.0.0.1")):
        raise HTTPException(403, "Fremder Ursprung")


@app.get("/api/sync/status")
def sync_status():
    from flatex import credentials

    con = _con()
    quellen = {}
    for q, n, zuletzt, von, bis in con.execute(
            "SELECT quelle, COUNT(*), MAX(geladen_am), MIN(von), MAX(bis) FROM sync_fenster GROUP BY quelle"):
        quellen[q] = {"fenster": n, "zuletzt": zuletzt, "von": von, "bis": bis}
    f = _job.fortschritt
    return _clean({
        "laeuft": _job.laeuft,
        "gestartet": _job.gestartet, "beendet": _job.beendet, "optionen": _job.optionen,
        "schritt": f.schritt if f else None,
        "aktionen": f.aktionen if f else 0, "anfragen": f.anfragen if f else 0,
        "log": f.log[-200:] if f else [],
        "ergebnis": vars(_job.ergebnis) if _job.ergebnis else None,
        "quellen": quellen,
        "kurse_bis": con.execute("SELECT MAX(datum) FROM kurse").fetchone()[0],
        "zugangsdaten": credentials.vorhanden(),
        "benutzer": credentials.benutzer_maskiert(),
        "zugang_quelle": credentials.quelle(),
        "depot_start": _start(con),
        "heute": date.today(),
        "postfach_automatisch": cfg.postfach_automatisch,
    })


class SyncStart(BaseModel):
    konto_depot: bool = True
    kurse: bool = True
    postfach: bool = False
    postfach_neu_pruefen: bool = False   # alle Zeitfenster neu auflisten (lädt nur Fehlendes)
    debug: bool = False                  # Server-Antworten unter /data/erkunden speichern
    von: str | None = None          # None = ab Depotstart (Einstellungen)
    bis: str | None = None          # None = bis heute


def zeitraum_pruefen(von: str | None, bis: str | None, start: date, heute: date) -> tuple[date, date | None]:
    """Prüft den Abrufzeitraum vor dem Start – ein falsches Datum soll nicht erst bei flatex scheitern."""
    try:
        v = date.fromisoformat(von) if von else start
        b = date.fromisoformat(bis) if bis else None
    except ValueError:
        raise HTTPException(400, "Ungültiges Datum (Format JJJJ-MM-TT)")
    if v > heute:
        raise HTTPException(400, "„Von“ liegt in der Zukunft")
    if v < date(2000, 1, 1):
        raise HTTPException(400, "„Von“ vor 2000 nimmt flatex nicht an")
    if b and b < v:
        raise HTTPException(400, "„Bis“ liegt vor „Von“")
    return v, b


@app.post("/api/sync/start")
def sync_start(opt: SyncStart, request: Request):
    from flatex.runner import Fortschritt, run_sync
    from flatex import sync as sync_mod

    _nur_lokal(request)
    if _job.laeuft:
        raise HTTPException(409, "Es läuft bereits ein Abruf")
    quellen = (["konto", "depot"] if opt.konto_depot else []) + (["postfach"] if opt.postfach else [])
    if not quellen and not opt.kurse:
        raise HTTPException(400, "Nichts ausgewählt")
    con = _con()
    von, ende = zeitraum_pruefen(opt.von, opt.bis, _start(con), date.today())
    if ende:
        ende = sync_mod.clamp_end(ende, date.today())
    from flatex.einstellungen import wirksame_config

    lauf_cfg = wirksame_config(cfg, con)
    _job.cancel = threading.Event()
    _job.fortschritt = Fortschritt()
    _job.ergebnis = None
    _job.gestartet, _job.beendet = date.today().isoformat() + "T" + _uhrzeit(), None
    _job.optionen = opt.model_dump()

    def lauf():
        try:
            _job.ergebnis = run_sync(lauf_cfg, quellen, von, ende, kurse_laden=opt.kurse, debug=opt.debug,
                                     postfach_neu_pruefen=opt.postfach and opt.postfach_neu_pruefen,
                                     log=_job.fortschritt.add, cancel=_job.cancel, fortschritt=_job.fortschritt)
        except Exception as e:  # noqa: BLE001 – Fehler gehören in die Oberfläche, nicht in den Server-Log
            from flatex.runner import Ergebnis

            _job.fortschritt.add(f"Unerwarteter Fehler: {e}")
            _job.ergebnis = Ergebnis("fehler", str(e))
        finally:
            _job.beendet = date.today().isoformat() + "T" + _uhrzeit()
            _cache.clear()   # neue Daten -> Kennzahlen neu rechnen

    _job.thread = threading.Thread(target=lauf, name="flatex-sync", daemon=True)
    _job.thread.start()
    return {"gestartet": True}


@app.post("/api/sync/stop")
def sync_stop(request: Request):
    _nur_lokal(request)
    if _job.laeuft:
        _job.cancel.set()
        _job.fortschritt.add("Abbruch angefordert …")
    return {"laeuft": _job.laeuft}


class Zugang(BaseModel):
    benutzer: str
    passwort: str


@app.post("/api/credentials")
def credentials_setzen(z: Zugang, request: Request):
    from flatex import credentials

    _nur_lokal(request)
    if not z.benutzer.strip() or not z.passwort:
        raise HTTPException(400, "Benutzer und Passwort angeben")
    credentials.store(z.benutzer.strip(), z.passwort)
    return {"gespeichert": True, "benutzer": credentials.benutzer_maskiert()}


def _uhrzeit() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")


# --- Einstellungen ----------------------------------------------------------------------------

class EinstellungenIn(BaseModel):
    depot_start: str | None = None
    eigene_namen: list[str] = []
    farben: dict[str, str] = {}


@app.get("/api/einstellungen")
def einstellungen_lesen():
    from flatex import einstellungen

    con = _con()
    e = einstellungen.laden(con)
    # Gegenkonten aus den Kontoumsätzen als Auswahlhilfe (bleibt lokal)
    konto = pd.read_sql_query("SELECT * FROM konto_umsaetze", con)
    gegen = a._gegenkonto(konto) if len(konto) else []
    zaehler: dict[str, dict] = {}
    for g, cent in zip(gegen, konto["betrag_cent"] if len(konto) else []):
        if g:
            z = zaehler.setdefault(g, {"gegenkonto": g, "anzahl": 0, "summe": 0.0})
            z["anzahl"] += 1
            z["summe"] += cent / 100
    for z in zaehler.values():
        z["erkannt"] = a.ist_eigenes_konto(z["gegenkonto"], e.eigene_namen)
    return _clean({
        "depot_start": e.depot_start, "depot_start_wirksam": _start(con),
        "depot_start_config": cfg.depot_start,
        "eigene_namen": e.eigene_namen, "farben": e.farben,
        "gegenkonten": sorted(zaehler.values(), key=lambda z: -z["anzahl"]),
    })


@app.post("/api/einstellungen")
def einstellungen_speichern(e_in: EinstellungenIn, request: Request):
    from flatex import einstellungen

    _nur_lokal(request)
    con = _con()
    try:
        einstellungen.speichern(con, einstellungen.Einstellungen(
            depot_start=e_in.depot_start or None, eigene_namen=e_in.eigene_namen, farben=e_in.farben))
    except ValueError:
        raise HTTPException(400, "Ungültiges Datum für den Depotstart (JJJJ-MM-TT)")
    _cache.clear()
    return einstellungen_lesen()


# --- Rohdaten (CSV-Exporte, PDFs) ansehen und herunterladen -----------------------------------

def _rohpfad(rel: str) -> Path:
    """Pfad relativ zum Datenordner – nur Dateien unter data/raw sind erlaubt."""
    basis = (cfg.data_dir / "raw").resolve()
    p = (cfg.data_dir / rel).resolve()
    if basis not in p.parents or not p.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
    return p


@app.get("/api/rohdaten")
def rohdaten():
    from flatex.sync import rohdatei_bereich

    con = _con()
    raw = cfg.data_dir / "raw"
    csv_dateien = []
    for quelle in ("konto", "depot"):
        for f in sorted((raw / quelle).glob("*.*"), reverse=True) if (raw / quelle).exists() else []:
            r = rohdatei_bereich(f.stem)
            csv_dateien.append({"quelle": quelle, "pfad": str(f.relative_to(cfg.data_dir)).replace("\\", "/"),
                                "name": f.name, "groesse": f.stat().st_size,
                                "von": r[0] if r else None, "bis": r[1] if r else None})
    pdfs = []
    for d_, name, pfad, geladen in con.execute(
            "SELECT datum, name, pfad, geladen_am FROM dokumente WHERE pfad IS NOT NULL ORDER BY datum DESC"):
        f = cfg.data_dir / pfad
        if f.exists():
            pdfs.append({"datum": d_, "name": name, "pfad": pfad.replace("\\", "/"), "groesse": f.stat().st_size,
                         "geladen": geladen})
    return _clean({"csv": csv_dateien, "pdf": pdfs})


@app.get("/api/rohdaten/datei")
def rohdatei(pfad: str, download: bool = False):
    p = _rohpfad(pfad)
    typ = "application/pdf" if p.suffix.lower() == ".pdf" else \
        "text/csv; charset=utf-8" if p.suffix.lower() == ".csv" else "application/octet-stream"
    return FileResponse(p, media_type=typ, filename=p.name,
                        content_disposition_type="attachment" if download else "inline")


@app.get("/api/rohdaten/vorschau")
def rohdatei_vorschau(pfad: str):
    """CSV/XLSX als Tabelle (Originalspalten) zum Ansehen im Browser."""
    from flatex.parse.umsaetze import _table_from_bytes

    p = _rohpfad(pfad)
    if p.suffix.lower() not in (".csv", ".xlsx"):
        raise HTTPException(400, "Nur CSV/XLSX")
    data = p.read_bytes()
    if not data.strip():
        return {"kopf": [], "zeilen": [], "hinweis": "Leerer Export (keine Buchungen im Zeitraum)"}
    tabelle = _table_from_bytes(data, p.suffix.lower().lstrip("."))
    kopf = [str(c) if c not in (None, "") else "" for c in tabelle[0]] if tabelle else []
    zeilen = [[("" if c is None else str(c)) for c in r] for r in tabelle[1:501]]
    return {"kopf": kopf, "zeilen": zeilen, "hinweis": None, "gesamt": max(len(tabelle) - 1, 0)}


# --- Frontend ausliefern ----------------------------------------------------------------------

WEB_DIST = config.ROOT / "web" / "dist"


def mount_frontend(application: FastAPI, dist: Path = WEB_DIST) -> None:
    if not dist.exists():
        return
    application.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @application.get("/{pfad:path}", include_in_schema=False)
    def spa(pfad: str):
        datei = dist / pfad
        if pfad and datei.is_file() and dist in datei.resolve().parents:
            return FileResponse(datei)
        return FileResponse(dist / "index.html")


mount_frontend(app)
