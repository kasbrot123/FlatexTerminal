"""Tagesschlusskurse über Yahoo Finance (yfinance), umgerechnet in EUR.

- Ticker je ISIN: automatische Suche, bevorzugt eine Euro-Börse; sonst die
  Heimatbörse plus Wechselkurs. Korrekturen in securities.toml haben Vorrang.
- Nur fehlende Tage werden geladen (plus ein paar Tage Überlappung).
- Prüfung: Yahoo-Kurs am Handelstag vs. echter flatex-Ausführungskurs.
- Fehlt ein Kurs (z. B. delistet), wird der letzte flatex-Handelskurs verwendet
  und als Ersatz markiert.
"""

from __future__ import annotations

import sqlite3
import time
import tomllib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS wertpapiere (
    isin        TEXT PRIMARY KEY,
    bezeichnung TEXT,
    ticker      TEXT,          -- leer = kein Kurs verfügbar
    waehrung    TEXT,
    quelle      TEXT,          -- auto | manuell
    abweichung  REAL,          -- Median |Yahoo/flatex - 1| an Handelstagen
    geprueft_am TEXT
);
CREATE TABLE IF NOT EXISTS kurse (
    isin      TEXT NOT NULL,
    datum     TEXT NOT NULL,
    close     REAL NOT NULL,   -- in Handelswährung
    close_eur REAL NOT NULL,
    PRIMARY KEY (isin, datum)
);
CREATE TABLE IF NOT EXISTS dividenden_yahoo (
    isin     TEXT NOT NULL,
    ex_datum TEXT NOT NULL,
    betrag   REAL NOT NULL,    -- je Stück, in Handelswährung des Tickers
    PRIMARY KEY (isin, ex_datum)
);
CREATE TABLE IF NOT EXISTS fx (
    waehrung TEXT NOT NULL,    -- z. B. USD
    datum    TEXT NOT NULL,
    pro_eur  REAL NOT NULL,    -- Einheiten Fremdwährung je 1 EUR
    PRIMARY KEY (waehrung, datum)
);
"""

# Börsenkürzel bei Yahoo, die in EUR notieren (Reihenfolge = Vorrang).
EUR_EXCHANGES = ["GER", "VIE", "BRU", "PAR", "AMS", "MIL", "MCE", "LIS", "HEL", "DUB",
                 "FRA", "STU", "MUN", "BER", "DUS", "HAM"]
WARN_ABWEICHUNG = 0.10   # >10 % Abweichung zum flatex-Kurs = vermutlich falsche Börse/Einheit
OVERLAP_DAYS = 5


TYPEN = ("Aktie", "ETF", "Derivat", "Sonstige")
DERIVAT_WORTE = ("TURBO", " CALL", " PUT", "OPTIONSSCHEIN", "OPT.SCH", "ZERTIFIKAT", "ZERT.", "KNOCK",
                 "MINI L", "MINI S", "FAKTOR", "BONUS", "DISCOUNT", " OPEN END", "WARRANT")


def connect_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(wertpapiere)")}
    if "typ" not in have:
        con.execute("ALTER TABLE wertpapiere ADD COLUMN typ TEXT")   # Aktie | ETF | Derivat | Sonstige


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return {isin.upper(): v for isin, v in tomllib.load(f).items() if isinstance(v, dict)}


def load_overrides(path: Path) -> dict[str, str]:
    """securities.toml: [ISIN] ticker = "XYZ.DE"   (ticker = "" erzwingt Ersatzkurs)."""
    return {isin: str(v["ticker"]) for isin, v in _load_toml(path).items() if "ticker" in v}


def load_typ_overrides(path: Path) -> dict[str, str]:
    """securities.toml: [ISIN] typ = "ETF" | "Aktie" | "Derivat" | "Sonstige"."""
    return {isin: str(v["typ"]) for isin, v in _load_toml(path).items() if v.get("typ") in TYPEN}


def typ_aus_name(name: str) -> str | None:
    n = f" {name.upper()} "
    if any(w in n for w in DERIVAT_WORTE):
        return "Derivat"
    if " ETF " in n or "UCITS" in n or " ETC " in n:
        return "ETF"
    return None


def klassifizieren(con: sqlite3.Connection, typ_overrides: dict[str, str], log=print) -> None:
    """Setzt wertpapiere.typ: Override > Name (Derivat/ETF) > Yahoo-Wertpapierart > Aktie."""
    connect_schema(con)
    for isin, name, typ in con.execute("SELECT isin, bezeichnung, typ FROM wertpapiere").fetchall():
        neu = typ_overrides.get(isin) or typ_aus_name(name or "")
        if not neu and not typ:
            try:
                import yfinance as yf

                qt = next((q.get("quoteType") for q in yf.Search(isin, max_results=5).quotes
                           if q.get("quoteType")), None)
            except Exception:  # noqa: BLE001
                qt = None
            neu = {"ETF": "ETF", "MUTUALFUND": "ETF", "EQUITY": "Aktie"}.get(qt or "", "Aktie")
            time.sleep(0.3)
        if neu and neu != typ:
            con.execute("UPDATE wertpapiere SET typ=? WHERE isin=?", (neu, isin))
    con.commit()


MIN_TAGE = 5   # ein Ticker mit weniger Kursen gilt als unbrauchbar


def search_candidates(isin: str) -> list[str]:
    """Ticker-Kandidaten in Vorrang-Reihenfolge:
    1. echte Ticker an Euro-Börsen, 2. echte Ticker anderswo (Umrechnung per Wechselkurs),
    3. ISIN-Kunstticker (z. B. 'IE00B4L5Y983.SG' – oft lückenhaft)."""
    import yfinance as yf

    quotes = [q for q in yf.Search(isin, max_results=10).quotes if q.get("symbol")]
    real = [q for q in quotes if not q["symbol"].upper().startswith(isin)]
    kunst = [q["symbol"] for q in quotes if q["symbol"].upper().startswith(isin)]
    rank = {ex: i for i, ex in enumerate(EUR_EXCHANGES)}
    eur = sorted((q for q in real if q.get("exchange") in rank), key=lambda q: rank[q["exchange"]])
    andere = [q for q in real if q.get("exchange") not in rank]
    out: list[str] = []
    for sym in [q["symbol"] for q in eur] + [q["symbol"] for q in andere] + kunst:
        if sym not in out:
            out.append(sym)
    return out


def _history(ticker: str, start: date, end: date) -> tuple[pd.Series, str | None]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    h = t.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                  auto_adjust=False, actions=False)
    cur = None
    try:
        cur = t.history_metadata.get("currency")
    except Exception:  # noqa: BLE001
        pass
    if h.empty:
        return pd.Series(dtype=float), cur
    s = h["Close"].dropna()
    s.index = s.index.tz_localize(None).normalize()
    return s, cur


def _first_working(candidates: list[str], start: date, end: date, log) -> str:
    """Erster Kandidat, der genug Kurse liefert (kurzer Testabruf über 60 Tage)."""
    probe_end = min(end, start + timedelta(days=60))
    for sym in candidates:
        try:
            s, _ = _history(sym, start, probe_end)
        except Exception:  # noqa: BLE001
            continue
        if len(s) >= MIN_TAGE:
            return sym
        log(f"    {sym}: nur {len(s)} Kurs(e) – nächster Kandidat")
        time.sleep(0.3)
    return ""


def _to_eur(con: sqlite3.Connection, close: pd.Series, cur: str, start: date, end: date, log) -> pd.Series:
    if cur in (None, "EUR"):
        return close
    factor = 1.0
    if cur in ("GBp", "GBX"):        # Pence
        cur, factor = "GBP", 100.0
    if cur == "ILA":
        cur, factor = "ILS", 100.0
    fx = _fx(con, cur, start, end, log)
    rate = fx.reindex(close.index).ffill().bfill()
    return close / factor / rate


def _fx(con: sqlite3.Connection, cur: str, start: date, end: date, log) -> pd.Series:
    have = pd.read_sql_query("SELECT datum, pro_eur FROM fx WHERE waehrung=? ORDER BY datum", con, params=(cur,))
    last = date.fromisoformat(have["datum"].iloc[-1]) if len(have) else None
    first = date.fromisoformat(have["datum"].iloc[0]) if len(have) else None
    if last is None or first > start or last < end - timedelta(days=1):
        s, _ = _history(f"EUR{cur}=X", min(start, first or start) - timedelta(days=7), end)
        for d, v in s.items():
            con.execute("INSERT OR REPLACE INTO fx VALUES (?,?,?)", (cur, d.date().isoformat(), float(v)))
        con.commit()
        log(f"  Wechselkurs EUR/{cur}: {len(s)} Tage")
        have = pd.read_sql_query("SELECT datum, pro_eur FROM fx WHERE waehrung=? ORDER BY datum", con, params=(cur,))
    return pd.Series(have["pro_eur"].values, index=pd.to_datetime(have["datum"]))


def dividenden_laden(con: sqlite3.Connection, log=print, pause: float = 0.3) -> None:
    """Dividendenhistorie (Ex-Tag, Betrag je Stück) je Ticker – Grundlage für den Kalender."""
    import yfinance as yf

    connect_schema(con)
    n = 0
    for isin, ticker in con.execute("SELECT isin, ticker FROM wertpapiere WHERE ticker IS NOT NULL AND ticker != ''"):
        try:
            s = yf.Ticker(ticker).dividends
        except Exception as e:  # noqa: BLE001
            log(f"  {isin} {ticker}: Dividenden nicht abrufbar ({e})")
            continue
        for tag, betrag in s.items():
            con.execute("INSERT OR REPLACE INTO dividenden_yahoo VALUES (?,?,?)",
                        (isin, tag.tz_localize(None).date().isoformat() if tag.tzinfo else tag.date().isoformat(),
                         float(betrag)))
        n += len(s)
        time.sleep(pause)
    con.commit()
    log(f"Dividendenhistorie: {n} Einträge")


def fx_letzt(con: sqlite3.Connection, waehrung: str | None) -> float | None:
    """Euro-Wert einer Einheit der Währung (letzter Kurs). GBp/ILA in Hundertstel."""
    if not waehrung or waehrung == "EUR":
        return 1.0
    faktor = 1.0
    if waehrung in ("GBp", "GBX"):
        waehrung, faktor = "GBP", 100.0
    if waehrung == "ILA":
        waehrung, faktor = "ILS", 100.0
    row = con.execute("SELECT pro_eur FROM fx WHERE waehrung=? ORDER BY datum DESC LIMIT 1", (waehrung,)).fetchone()
    return None if not row else 1.0 / (row[0] * faktor)


def wertpapier_liste(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT isin, MAX(bezeichnung) AS bezeichnung, MIN(buchtag) AS erst FROM depot_umsaetze "
        "WHERE isin IS NOT NULL GROUP BY isin ORDER BY isin", con)


def update(con: sqlite3.Connection, overrides: dict[str, str], today: date | None = None,
           log=print, pause: float = 0.5) -> None:
    connect_schema(con)
    today = today or date.today()
    for _, w in wertpapier_liste(con).iterrows():
        isin, name = w["isin"], w["bezeichnung"]
        erst = date.fromisoformat(w["erst"]) - timedelta(days=7)
        prev = con.execute("SELECT ticker, quelle FROM wertpapiere WHERE isin=?", (isin,)).fetchone()
        n_kurse = con.execute("SELECT COUNT(*) FROM kurse WHERE isin=?", (isin,)).fetchone()[0]
        if isin in overrides:
            ticker, quelle = overrides[isin], "manuell"
        elif prev and prev[1] == "auto" and (not prev[0] or n_kurse >= MIN_TAGE):
            ticker, quelle = prev[0] or "", "auto"
        else:  # neu, manuelle Zuordnung entfernt, oder bisheriger Ticker lieferte zu wenig
            try:
                ticker = _first_working(search_candidates(isin), erst, today, log)
            except Exception as e:  # noqa: BLE001
                log(f"  {isin}: Suche fehlgeschlagen ({e})")
                continue
            quelle = "auto"
            time.sleep(pause)
        if prev and (prev[0] or "") != ticker:  # Zuordnung geändert -> alte Kurse verwerfen
            con.execute("DELETE FROM kurse WHERE isin=?", (isin,))
        con.execute(
            "INSERT INTO wertpapiere(isin, bezeichnung, ticker, quelle) VALUES (?,?,?,?) "
            "ON CONFLICT(isin) DO UPDATE SET bezeichnung=excluded.bezeichnung, ticker=excluded.ticker, "
            "quelle=excluded.quelle", (isin, name, ticker, quelle))
        if not ticker:
            log(f"  {isin} {name[:30]}: kein Ticker – Ersatzkurs aus flatex-Handelskursen")
            continue
        last = con.execute("SELECT MAX(datum) FROM kurse WHERE isin=?", (isin,)).fetchone()[0]
        start = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)) if last else erst
        if start >= today:
            continue
        try:
            close, cur = _history(ticker, start, today)
        except Exception as e:  # noqa: BLE001
            log(f"  {isin} {ticker}: Kursabruf fehlgeschlagen ({e})")
            continue
        if close.empty:
            log(f"  {isin} {ticker}: keine Kurse geliefert")
            continue
        eur = _to_eur(con, close, cur, start, today, log)
        for d, v in close.items():
            con.execute("INSERT OR REPLACE INTO kurse VALUES (?,?,?,?)",
                        (isin, d.date().isoformat(), float(v), float(eur.loc[d])))
        con.execute("UPDATE wertpapiere SET waehrung=? WHERE isin=?", (cur, isin))
        con.commit()
        log(f"  {isin} {ticker:14s} {cur or '?':4s} {len(close):4d} Tage ab {start}")
        time.sleep(pause)
    pruefen(con, log)


def pruefen(con: sqlite3.Connection, log=print) -> pd.DataFrame:
    """Vergleicht Yahoo-Schlusskurse mit flatex-Ausführungskursen (in EUR) an Handelstagen."""
    trades = pd.read_sql_query(
        "SELECT isin, buchtag, kurs, kurs_waehrung, devisenkurs, text FROM depot_umsaetze "
        "WHERE kurs IS NOT NULL AND (text LIKE '%ORDER Kauf%' OR text LIKE '%ORDER Verkauf%')", con)
    kurse = pd.read_sql_query("SELECT isin, datum, close_eur FROM kurse", con)
    if trades.empty or kurse.empty:
        return pd.DataFrame()
    # flatex-Kurs in EUR: bei Fremdwährung durch den Devisenkurs teilen
    fx = trades["devisenkurs"].where(trades["kurs_waehrung"].fillna("EUR") != "EUR", 1.0).fillna(1.0)
    trades["kurs_eur"] = trades["kurs"] / fx
    out = []
    for isin, grp in trades.groupby("isin"):
        k = kurse[kurse["isin"] == isin]
        if k.empty:
            continue
        s = pd.Series(k["close_eur"].values, index=pd.to_datetime(k["datum"])).sort_index()
        # Schlusskurs Vortag / Tag / Folgetag – der nächstliegende zählt. Buchtag und
        # Ausführung können um einen Handelstag auseinanderliegen (z. B. nachbörsliche Zahlen).
        devs = []
        for t, kurs in zip(pd.to_datetime(grp["buchtag"]), grp["kurs_eur"]):
            nah = [s.asof(t - pd.Timedelta(days=1)), s.asof(t)]
            nach = s.loc[t + pd.Timedelta(days=1):]
            if len(nach):
                nah.append(nach.iloc[0])
            werte = [abs(x / kurs - 1) for x in nah if pd.notna(x) and kurs]
            if werte:
                devs.append(min(werte))
        dev = pd.Series(devs, dtype=float)
        if len(dev):
            out.append({"isin": isin, "abweichung": float(dev.median()), "handelstage": len(dev)})
    res = pd.DataFrame(out)
    for _, r in res.iterrows():
        con.execute("UPDATE wertpapiere SET abweichung=?, geprueft_am=date('now') WHERE isin=?",
                    (r["abweichung"], r["isin"]))
    con.commit()
    bad = res[res["abweichung"] > WARN_ABWEICHUNG] if len(res) else res
    names = dict(con.execute("SELECT isin, ticker FROM wertpapiere").fetchall())
    log(f"Prüfung gegen flatex-Kurse: {len(res)} Wertpapiere, "
        f"Median-Abweichung {res['abweichung'].median():.1%}" if len(res) else "Prüfung: keine Daten")
    for _, r in bad.iterrows():
        log(f"  WARNUNG {r['isin']} ({names.get(r['isin'])}): Yahoo weicht {r['abweichung']:.0%} vom "
            "flatex-Kurs ab – falsche Börse/Einheit? In securities.toml korrigieren.")
    return res


def preis_tabelle(con: sqlite3.Connection, bis: date) -> tuple[pd.DataFrame, set[str]]:
    """Tagespreise in EUR je ISIN (Spalten), Kalendertage, vorwärts gefüllt.

    Wo Yahoo keinen Kurs hat, wird der letzte flatex-Handelskurs (in EUR) verwendet.
    Gibt (Preise, ISINs mit Ersatzkurs) zurück.
    """
    connect_schema(con)
    k = pd.read_sql_query("SELECT isin, datum, close_eur FROM kurse WHERE datum <= ?", con,
                          params=(bis.isoformat(),))
    t = pd.read_sql_query(
        "SELECT isin, buchtag AS datum, kurs, kurs_waehrung, devisenkurs FROM depot_umsaetze "
        "WHERE kurs IS NOT NULL AND buchtag <= ?", con, params=(bis.isoformat(),))
    fx = t["devisenkurs"].where(t["kurs_waehrung"].fillna("EUR") != "EUR", 1.0).fillna(1.0)
    t["kurs_eur"] = t["kurs"] / fx
    yahoo = k.pivot_table(index="datum", columns="isin", values="close_eur", aggfunc="last")
    flatex = t.pivot_table(index="datum", columns="isin", values="kurs_eur", aggfunc="last")
    for df in (yahoo, flatex):
        df.index = pd.to_datetime(df.index)
    ersatz = set(flatex.columns) - set(yahoo.columns)
    start = min([x.index.min() for x in (yahoo, flatex) if len(x)], default=pd.Timestamp(bis))
    idx = pd.date_range(start, pd.Timestamp(bis), freq="D")
    preise = yahoo.reindex(idx).ffill()
    fb = flatex.reindex(idx).ffill()
    for c in fb.columns:
        if c not in preise:
            preise[c] = fb[c]
        else:   # vor dem ersten Yahoo-Kurs: flatex-Kurs
            preise[c] = preise[c].fillna(fb[c])
    return preise, ersatz
