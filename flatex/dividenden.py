"""Dividendenanalyse: erhaltene Zahlungen (Konto) und erwartete Zahlungen (Yahoo-Historie).

Erwartet = für jede gehaltene Position die Ausschüttungen der letzten 12 Monate um ein Jahr
fortgeschrieben (gleicher Rhythmus, gleicher Betrag je Stück), mal aktueller Stückzahl.
Das ist eine Prognose, keine Ankündigung. Netto wird mit 27,5 % KESt geschätzt.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from flatex.analytics import Bestand, Daten, stueck_taeglich
from flatex.kurse import fx_letzt
from flatex.steuer import KEST

ZAHLTAG_VERSATZ = 14   # Standard-Tage zwischen Ex-Tag und Gutschrift, wenn nichts Besseres bekannt ist


def erhalten(d: Daten, namen: dict[str, str]) -> pd.DataFrame:
    k = d.konto[d.konto["kategorie"].isin(["dividende", "ausschuettung"])]
    return pd.DataFrame({
        "d": k["buchtag"], "isin": k["isin"], "name": k["isin"].map(namen),
        "art": k["kategorie"], "netto": k["betrag"],
    }).reset_index(drop=True)


def _yahoo(con: sqlite3.Connection) -> pd.DataFrame:
    y = pd.read_sql_query(
        "SELECT d.isin, d.ex_datum, d.betrag, w.waehrung FROM dividenden_yahoo d JOIN wertpapiere w USING (isin)", con)
    y["ex_datum"] = pd.to_datetime(y["ex_datum"])
    y["fx"] = y["waehrung"].map(lambda w: fx_letzt(con, w))
    y["betrag_eur"] = y["betrag"] * y["fx"]
    return y


def abgleich(con: sqlite3.Connection, d: Daten, b: Bestand) -> pd.DataFrame:
    """Je erhaltener Dividende: passender Yahoo-Ex-Tag (bis 60 Tage davor), Stück am Ex-Tag,
    erwartetes Brutto laut Yahoo vs. Brutto laut Konto (Netto / 0,725)."""
    y = _yahoo(con)
    st = stueck_taeglich(d, b)
    out = []
    for _, r in erhalten(d, {}).iterrows():
        kand = y[(y["isin"] == r["isin"]) & (y["ex_datum"] <= r["d"]) & (y["ex_datum"] >= r["d"] - timedelta(days=60))]
        if kand.empty:
            continue
        ex = kand.sort_values("ex_datum").iloc[-1]
        vortag = ex["ex_datum"] - timedelta(days=1)
        stueck = float(st[r["isin"]].get(vortag, 0.0)) if r["isin"] in st else 0.0
        brutto_konto = r["netto"] / (1 - KEST)
        brutto_yahoo = stueck * ex["betrag_eur"] if pd.notna(ex["betrag_eur"]) else None
        out.append({"d": r["d"], "isin": r["isin"], "ex": ex["ex_datum"], "stueck": stueck,
                    "je_stueck_eur": ex["betrag_eur"], "brutto_konto": brutto_konto, "brutto_yahoo": brutto_yahoo,
                    "versatz_tage": (r["d"] - ex["ex_datum"]).days,
                    "abweichung": None if not brutto_yahoo else brutto_yahoo / brutto_konto - 1})
    return pd.DataFrame(out)


def erwartet(con: sqlite3.Connection, d: Daten, b: Bestand, ab: date, monate: int = 12,
             namen: dict[str, str] | None = None) -> pd.DataFrame:
    """Prognose der Zahlungen in (ab, ab + monate] für den Bestand am Tag `ab`."""
    y = _yahoo(con)
    st = stueck_taeglich(d, b)
    if st.empty:
        return pd.DataFrame(columns=["d", "ex", "isin", "name", "stueck", "je_stueck_eur", "brutto", "netto"])
    bestand = st.loc[:pd.Timestamp(ab)].iloc[-1]
    ab_ts, bis_ts = pd.Timestamp(ab), pd.Timestamp(ab) + pd.DateOffset(months=monate)
    versatz = abgleich(con, d, b).groupby("isin")["versatz_tage"].median() if len(y) else pd.Series(dtype=float)
    out = []
    for isin, n in bestand.items():
        if n <= 1e-9:
            continue
        hist = y[(y["isin"] == isin) & (y["ex_datum"] <= ab_ts)].sort_values("ex_datum")
        letzte = hist[hist["ex_datum"] > ab_ts - pd.DateOffset(months=12)]
        if letzte.empty or letzte["betrag_eur"].isna().all():
            continue
        lag = int(versatz.get(isin, ZAHLTAG_VERSATZ)) if pd.notna(versatz.get(isin, None)) else ZAHLTAG_VERSATZ
        for _, h in letzte.iterrows():
            ex = h["ex_datum"] + pd.DateOffset(years=1)
            # bereits angekündigte, echte Termine nach `ab` haben Vorrang vor der Fortschreibung
            echt = y[(y["isin"] == isin) & (y["ex_datum"] > ab_ts) & ((y["ex_datum"] - ex).abs() <= pd.Timedelta(days=45))]
            quelle = "Prognose"
            if len(echt):
                ex, je = echt.iloc[0]["ex_datum"], echt.iloc[0]["betrag_eur"]
                quelle = "angekündigt" if echt.iloc[0]["ex_datum"] > pd.Timestamp(date.today()) else "Yahoo"
            else:
                je = h["betrag_eur"]
            zahl = ex + pd.Timedelta(days=lag)
            if not (ab_ts < zahl <= bis_ts) or pd.isna(je):
                continue
            brutto = float(n) * float(je)
            out.append({"d": zahl, "ex": ex, "isin": isin, "name": (namen or {}).get(isin, isin), "stueck": float(n),
                        "je_stueck_eur": float(je), "brutto": brutto, "netto": brutto * (1 - KEST), "quelle": quelle})
    return pd.DataFrame(out, columns=["d", "ex", "isin", "name", "stueck", "je_stueck_eur", "brutto", "netto",
                                      "quelle"]).sort_values("d").reset_index(drop=True)
