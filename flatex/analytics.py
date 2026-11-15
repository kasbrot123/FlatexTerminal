"""Auswertung aus Konto- und Depotumsätzen (ohne Kursdaten).

Begriffe:
- Einstand: tatsächlich bezahltes Geld für offene Positionen inkl. Kaufgebühren, nach
  gleitendem Durchschnittspreis. Grundlage für Gewinn/Verlust.
- Steuerlicher Einstand: wie flatex ihn führt – zusätzlich erhöht um die ausschüttungsgleichen
  Erträge ("Thesaurierung transparenter Fonds"). Kein bezahltes Geld, nur für die KESt relevant.
- Kaufgebühr: Kontobuchung minus Kurswert im Depot (gleiche Ordernummer).
- Abzüge beim Verkauf: Kurswert minus Gutschrift = Gebühren + einbehaltene KESt.
  Ohne PDF lassen sich die beiden nicht trennen.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

import pandas as pd

RE_ORDER = re.compile(r"ORDER\s+(Kauf|Verkauf)\s+([A-Z]{2}[A-Z0-9]{9}\d)\s+(\d+)")
RE_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")

KATEGORIEN = {
    "einlage": "Einzahlung",
    "auszahlung": "Auszahlung",
    "kauf": "Kauf",
    "verkauf": "Verkauf",
    "dividende": "Dividende",
    "ausschuettung": "Ausschüttung",
    "zinsen": "Zinsen",
    "steuer": "Steuer (Thesaurierung)",
    "sonstige": "Sonstiges",
}


def _norm(s: str) -> str:
    return " ".join(str(s).lower().replace(" ", "").split()) if s else ""


def ist_eigenes_konto(gegenkonto: str, eigene_namen: list[str] | None) -> bool:
    """Passt Empfänger/Zahlungspfl. zu einem der eigenen Namen bzw. IBANs (Groß/Klein und
    Leerzeichen egal)? Ohne Liste zählt jedes Gegenkonto."""
    if not gegenkonto:
        return False
    if not eigene_namen:
        return True
    g = _norm(gegenkonto)
    return any(_norm(n) and _norm(n) in g for n in eigene_namen)


def kategorie(text: str | None, betrag_cent: int, gegenkonto: str = "",
              eigene_namen: list[str] | None = None) -> str:
    """Kategorie einer Kontobuchung.

    Ein-/Auszahlungen: Buchungen mit Gegenkonto (Empfänger bzw. Zahlungspfl. gesetzt), das zu den
    eigenen Namen/IBANs aus den Einstellungen passt – ohne Einstellung jedes Gegenkonto. Interne
    Buchungen (Orders, Dividenden, Zinsen, Steuern) haben nie ein Gegenkonto. Der Buchungstext ist
    nur Rückfall für Exporte ohne diese Spalten.
    """
    t = text or ""
    if gegenkonto and not RE_ORDER.search(t):
        if ist_eigenes_konto(gegenkonto, eigene_namen):
            return "einlage" if betrag_cent > 0 else "auszahlung"
        return "sonstige"      # fremdes Gegenkonto: sichtbar machen statt raten
    if "ORDER Verkauf" in t:
        return "verkauf"
    if "ORDER Kauf" in t:
        return "kauf"
    if "Dividende" in t:
        return "dividende"
    if "Erträgnis" in t or "Ausschüttung" in t:
        return "ausschuettung"
    if "Zins" in t:
        return "zinsen"
    if "Thesaurierung" in t:
        return "steuer"
    if "Auszahlung" in t:
        return "auszahlung"
    if betrag_cent > 0 and ("Einlage" in t or "Sparplan" in t or "Überweisung" in t or "Gutschrift" in t):
        return "einlage"
    return "sonstige"


_GEGENKONTO_SPALTEN = ("Empfänger", "Zahlungspfl.", "Auftraggeber/Empfänger", "Zahlungspflichtiger")


def _gegenkonto(konto: pd.DataFrame) -> list[str]:
    """Empfänger und Zahlungspflichtiger einer Buchung als ein Text ("" = kein Gegenkonto)."""
    out = []
    for i in range(len(konto)):
        teile = []
        emp = konto["empfaenger"].iloc[i] if "empfaenger" in konto else None
        if isinstance(emp, str) and emp.strip():
            teile.append(emp.strip())
        raw = konto["raw_json"].iloc[i] if "raw_json" in konto else None
        try:
            r = json.loads(raw) if isinstance(raw, str) else {}
        except ValueError:
            r = {}
        teile += [str(r[s]).strip() for s in _GEGENKONTO_SPALTEN if str(r.get(s) or "").strip()]
        out.append(" | ".join(dict.fromkeys(teile)))
    return out


@dataclass
class Daten:
    konto: pd.DataFrame
    depot: pd.DataFrame
    von: date
    bis: date


def load(con: sqlite3.Connection, von: date, bis: date) -> Daten:
    q = "SELECT * FROM {t} WHERE buchtag BETWEEN ? AND ? ORDER BY buchtag, id"
    args = (von.isoformat(), bis.isoformat())
    konto = pd.read_sql_query(q.format(t="konto_umsaetze"), con, params=args)
    depot = pd.read_sql_query(q.format(t="depot_umsaetze"), con, params=args)
    from flatex.einstellungen import laden

    return prepare(konto, depot, von, bis, laden(con).eigene_namen)


def prepare(konto: pd.DataFrame, depot: pd.DataFrame, von: date, bis: date,
            eigene_namen: list[str] | None = None) -> Daten:
    konto = konto.copy()
    depot = depot.copy()
    for df in (konto, depot):
        df["buchtag"] = pd.to_datetime(df["buchtag"])
    konto["betrag"] = konto["betrag_cent"] / 100
    konto["gegenkonto"] = _gegenkonto(konto)
    konto["kategorie"] = [kategorie(t, b, g, eigene_namen) for t, b, g in
                          zip(konto["text"], konto["betrag_cent"], konto["gegenkonto"])]
    konto["isin"] = konto["text"].str.extract(RE_ISIN, expand=False)
    konto["order_nr"] = konto["text"].str.extract(RE_ORDER, expand=True)[2]
    depot["betrag"] = depot["betrag_cent"] / 100
    depot["order_nr"] = depot["text"].str.extract(RE_ORDER, expand=True)[2]
    depot["art"] = depot["text"].map(
        lambda t: "verkauf" if "Verkauf" in (t or "") else "kauf" if "Kauf" in (t or "")
        else "thesaurierung" if "Thesaurierung" in (t or "") else "sonstige")
    return Daten(konto, depot, von, bis)


def trades(d: Daten) -> pd.DataFrame:
    """Ein Eintrag pro Kauf/Verkauf: Kurswert (Depot), Kontobetrag, Gebühr bzw. Abzüge."""
    dep = d.depot[d.depot["art"].isin(["kauf", "verkauf"])]
    kon = d.konto[d.konto["kategorie"].isin(["kauf", "verkauf"])][["order_nr", "isin", "betrag"]]
    m = dep.merge(kon.rename(columns={"betrag": "konto_betrag"}), on=["order_nr", "isin"], how="left")
    m["kurswert"] = m["betrag"].abs()
    m["konto_abs"] = m["konto_betrag"].abs()
    m["gebuehr"] = (m["konto_abs"] - m["kurswert"]).where(m["art"] == "kauf")
    m["abzuege_verkauf"] = (m["kurswert"] - m["konto_abs"]).where(m["art"] == "verkauf")
    return m[["buchtag", "art", "isin", "bezeichnung", "stueck", "kurs", "kurswert", "konto_betrag", "konto_abs",
              "gebuehr", "abzuege_verkauf", "order_nr"]].sort_values("buchtag").reset_index(drop=True)


@dataclass
class Bestand:
    offen: pd.DataFrame          # offene Positionen am Ende
    realisiert: pd.DataFrame     # ein Eintrag je Verkauf
    einstand_tag: pd.Series      # Summe Einstand offener Positionen nach jedem Buchungstag
    stueck_tag: pd.DataFrame     # Stückzahl je ISIN (Spalten) nach jedem Buchungstag
    einstand_isin_tag: pd.DataFrame  # Einstand je ISIN (Spalten) nach jedem Buchungstag
    sonstige: pd.DataFrame       # Depotbuchungen ohne Kauf/Verkauf/Thesaurierung (z. B. Split)


def bestand(d: Daten) -> Bestand:
    """Gleitender Durchschnittspreis je Wertpapier, Buchung für Buchung."""
    tr = trades(d).drop_duplicates("order_nr").set_index("order_nr")

    def konto_abs(r) -> float:
        v = tr["konto_abs"].get(r["order_nr"]) if pd.notna(r["order_nr"]) else None
        return float(v) if v is not None and pd.notna(v) else abs(float(r["betrag"] or 0))

    state: dict[str, dict] = {}
    realisiert, einstand_tag, stueck_tag, einstand_isin, sonstige = [], {}, {}, {}, []
    for tag, grp in d.depot.sort_values(["buchtag", "id"]).groupby("buchtag"):
        for _, r in grp.iterrows():
            s = state.setdefault(r["isin"], {"stueck": 0.0, "einstand": 0.0, "einstand_steuer": 0.0,
                                             "bezeichnung": r["bezeichnung"]})
            q = float(r["stueck"] or 0)
            if r["art"] == "kauf":
                s["stueck"] += q
                s["einstand"] += konto_abs(r)
                s["einstand_steuer"] += konto_abs(r)
            elif r["art"] == "verkauf":
                qs = abs(q)
                quote = qs / s["stueck"] if s["stueck"] else 0.0
                anteil, anteil_st = s["einstand"] * quote, s["einstand_steuer"] * quote
                kurswert, gutschrift = abs(float(r["betrag"])), konto_abs(r)
                realisiert.append({
                    "buchtag": r["buchtag"], "isin": r["isin"], "bezeichnung": r["bezeichnung"], "stueck": qs,
                    "kurswert": kurswert, "einstand_anteil": anteil, "kursgewinn": kurswert - anteil,
                    "abzuege": kurswert - gutschrift, "netto": gutschrift - anteil,
                    "kursgewinn_steuerlich": kurswert - anteil_st,
                })
                s["stueck"] -= qs
                s["einstand"] -= anteil
                s["einstand_steuer"] -= anteil_st
                if abs(s["stueck"]) < 1e-9:
                    s["stueck"], s["einstand"], s["einstand_steuer"] = 0.0, 0.0, 0.0
            elif r["art"] == "thesaurierung":
                # Aus- und Wiedereinbuchung mit höherem Wert: nur der steuerliche Einstand steigt.
                s["stueck"] += q
                s["einstand_steuer"] += float(r["betrag"] or 0)
            else:
                # Unbekannte Depotbuchung (Split, Einbuchung, Kapitalmaßnahme): Stückzahl
                # übernehmen, Einstand unverändert lassen, im Dashboard ausweisen.
                s["stueck"] += q
                sonstige.append({"buchtag": r["buchtag"], "isin": r["isin"], "bezeichnung": r["bezeichnung"],
                                 "stueck": q, "text": r["text"]})
        einstand_tag[tag] = sum(v["einstand"] for v in state.values())
        stueck_tag[tag] = {k: v["stueck"] for k, v in state.items()}
        einstand_isin[tag] = {k: v["einstand"] for k, v in state.items()}
    offen = pd.DataFrame(
        [{"isin": k, **v, "durchschnitt": v["einstand"] / v["stueck"]} for k, v in state.items() if v["stueck"] > 1e-9],
        columns=["isin", "bezeichnung", "stueck", "einstand", "einstand_steuer", "durchschnitt"],
    ).sort_values("einstand", ascending=False).reset_index(drop=True)
    real = pd.DataFrame(realisiert, columns=["buchtag", "isin", "bezeichnung", "stueck", "kurswert",
                                             "einstand_anteil", "kursgewinn", "abzuege", "netto",
                                             "kursgewinn_steuerlich"])
    st = pd.DataFrame.from_dict(stueck_tag, orient="index").fillna(0.0)
    ei = pd.DataFrame.from_dict(einstand_isin, orient="index").fillna(0.0)
    return Bestand(offen, real, pd.Series(einstand_tag, dtype=float), st, ei,
                   pd.DataFrame(sonstige, columns=["buchtag", "isin", "bezeichnung", "stueck", "text"]))


def positionen(d: Daten) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = bestand(d)
    return b.offen, b.realisiert


def verlauf(d: Daten) -> pd.DataFrame:
    """Täglicher Verlauf: Einzahlungen netto, Kontostand, Einstand offener Positionen, Summe."""
    idx = pd.date_range(pd.Timestamp(d.von), pd.Timestamp(d.bis), freq="D")
    k = d.konto
    einz = k[k["kategorie"].isin(["einlage", "auszahlung"])].groupby("buchtag")["betrag"].sum()
    konto = k.groupby("buchtag")["betrag"].sum()
    einstand_tag = bestand(d).einstand_tag

    out = pd.DataFrame(index=idx)
    out["einzahlungen_netto"] = einz.reindex(idx, fill_value=0).astype(float).cumsum()
    out["kontostand"] = konto.reindex(idx, fill_value=0).astype(float).cumsum()
    out["einstand"] = einstand_tag.reindex(idx).ffill().fillna(0).astype(float)
    out["vermoegen_einstand"] = out["kontostand"] + out["einstand"]
    out.index.name = "datum"
    return out


# --- Marktwerte & Rendite (brauchen Tagespreise in EUR, siehe flatex.kurse.preis_tabelle) -------

def stueck_taeglich(d: Daten, b: Bestand | None = None) -> pd.DataFrame:
    b = b or bestand(d)
    idx = pd.date_range(pd.Timestamp(d.von), pd.Timestamp(d.bis), freq="D")
    st = b.stueck_tag
    if st.empty:
        return pd.DataFrame(index=idx)
    return st.reindex(st.index.union(idx)).ffill().reindex(idx).fillna(0.0)


def marktwerte(d: Daten, preise: pd.DataFrame, b: Bestand | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Täglicher Marktwert je ISIN (Spalten). Gibt zusätzlich ISINs zurück, die an
    mindestens einem Tag Bestand, aber keinen Preis hatten (dort mit 0 bewertet)."""
    st = stueck_taeglich(d, b)
    p = preise.reindex(st.index).ffill().reindex(columns=st.columns)
    fehlend = [c for c in st.columns if ((st[c].abs() > 1e-9) & p[c].isna()).any()]
    return (st * p.fillna(0.0)), fehlend


def verlauf_markt(d: Daten, preise: pd.DataFrame) -> pd.DataFrame:
    """Verlauf inkl. Depotwert zu Marktkursen und zeitgewichteter Rendite (TWR)."""
    b = bestand(d)
    v = verlauf(d)
    mw, _ = marktwerte(d, preise, b)
    v["depotwert"] = mw.sum(axis=1).reindex(v.index).fillna(0.0)
    v["vermoegen"] = v["kontostand"] + v["depotwert"]
    v["gewinn"] = v["vermoegen"] - v["einzahlungen_netto"]
    flows = v["einzahlungen_netto"].diff().fillna(v["einzahlungen_netto"].iloc[0])
    prev = v["vermoegen"].shift(1)
    # Tagesrendite; Ein-/Auszahlungen zählen am Tagesende (nicht als Ertrag)
    # Tage ohne nennenswertes Vorvermögen (Start, leeres Depot) zählen mit 0 % – keine Division durch 0
    r = ((v["vermoegen"] - flows) / prev.where(prev > 1.0) - 1).fillna(0.0)
    v["twr_index"] = (1 + r.fillna(0.0)).cumprod()
    return v


def rendite_zeitraum(v: pd.DataFrame, von: date, bis: date) -> float:
    """TWR zwischen Ende des Vortags von `von` und `bis` (aus verlauf_markt)."""
    s = v["twr_index"]
    vor = s.loc[:pd.Timestamp(von) - pd.Timedelta(days=1)]
    start = vor.iloc[-1] if len(vor) else 1.0
    return float(s.loc[:pd.Timestamp(bis)].iloc[-1] / start - 1)


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Geldgewichtete Rendite p.a. (Einzahlungen negativ, Auszahlungen/Endwert positiv)."""
    cf = [(pd.Timestamp(t), a) for t, a in cashflows if abs(a) > 1e-9]
    if len(cf) < 2 or not (any(a < 0 for _, a in cf) and any(a > 0 for _, a in cf)):
        return None
    t0 = min(t for t, _ in cf)

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** ((t - t0).days / 365.0) for t, a in cf)

    lo, hi = -0.9999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def xirr_zeitraum(v: pd.DataFrame, von: date, bis: date) -> float | None:
    """XIRR für [von, bis]: Startvermögen als Einzahlung, Ein-/Auszahlungen, Endvermögen als Auszahlung."""
    vor = v.loc[:pd.Timestamp(von) - pd.Timedelta(days=1)]
    teil = v.loc[pd.Timestamp(von):pd.Timestamp(bis)]
    if teil.empty:
        return None
    cf: list[tuple[date, float]] = []
    if len(vor) and vor["vermoegen"].iloc[-1] > 0:
        cf.append((pd.Timestamp(von), -float(vor["vermoegen"].iloc[-1])))
    start_netto = float(vor["einzahlungen_netto"].iloc[-1]) if len(vor) else 0.0
    flows = teil["einzahlungen_netto"].diff().fillna(teil["einzahlungen_netto"].iloc[0] - start_netto)
    cf += [(t, -float(a)) for t, a in flows.items() if abs(a) > 1e-9]
    cf.append((teil.index[-1], float(teil["vermoegen"].iloc[-1])))
    return xirr(cf)


def positionen_markt(d: Daten, preise: pd.DataFrame) -> pd.DataFrame:
    """Offene Positionen am Ende mit Marktwert und unrealisiertem Gewinn."""
    b = bestand(d)
    offen = b.offen.copy()
    p = preise.reindex(pd.date_range(preise.index.min(), pd.Timestamp(d.bis), freq="D")).ffill() \
        if len(preise) else preise
    last = p.iloc[-1] if len(p) else pd.Series(dtype=float)
    offen["kurs"] = offen["isin"].map(last)
    offen["marktwert"] = offen["stueck"] * offen["kurs"]
    offen["unrealisiert"] = offen["marktwert"] - offen["einstand"]
    offen["unrealisiert_pct"] = offen["unrealisiert"] / offen["einstand"] * 100
    return offen.sort_values("marktwert", ascending=False, na_position="last").reset_index(drop=True)


@dataclass
class PositionDetail:
    isin: str
    bezeichnung: str
    buchungen: pd.DataFrame    # Käufe/Verkäufe/Thesaurierung mit Kurs, Kurswert, Konto, Gebühr
    ertraege: pd.DataFrame     # Dividenden, Ausschüttungen, Steuer auf Thesaurierung (Konto)
    verlauf: pd.DataFrame      # täglich: stueck, kurs, marktwert, einstand, investiert_netto
    summe: dict


def position_detail(d: Daten, isin: str, preise: pd.DataFrame, b: Bestand | None = None) -> PositionDetail:
    """Alles zu einem Wertpapier. 'investiert_netto' = bezahlte Käufe minus Verkaufsgutschriften."""
    b = b or bestand(d)
    dep = d.depot[d.depot["isin"] == isin].sort_values(["buchtag", "id"])
    name = str(dep["bezeichnung"].dropna().iloc[-1]) if len(dep) else isin
    tr = trades(d)
    tr = tr[tr["isin"] == isin].set_index("order_nr")
    rows = []
    for _, r in dep.iterrows():
        t = tr.loc[r["order_nr"]] if pd.notna(r["order_nr"]) and r["order_nr"] in tr.index else None
        rows.append({
            "buchtag": r["buchtag"], "art": r["art"], "stueck": r["stueck"], "kurs": r["kurs"],
            "kurswert": abs(float(r["betrag"] or 0)),
            "konto": None if t is None else t["konto_betrag"],
            "gebuehr": None if t is None else t["gebuehr"],
            "abzuege_verkauf": None if t is None else t["abzuege_verkauf"],
        })
    buchungen = pd.DataFrame(rows, columns=["buchtag", "art", "stueck", "kurs", "kurswert", "konto", "gebuehr",
                                            "abzuege_verkauf"])
    k = d.konto
    ertraege = k[(k["isin"] == isin) & k["kategorie"].isin(["dividende", "ausschuettung", "steuer"])][
        ["buchtag", "kategorie", "betrag", "text"]].reset_index(drop=True)

    idx = pd.date_range(dep["buchtag"].min() if len(dep) else pd.Timestamp(d.von), pd.Timestamp(d.bis), freq="D")

    def taeglich(df: pd.DataFrame) -> pd.Series:
        if isin not in df.columns:
            return pd.Series(0.0, index=idx)
        s = df[isin]
        return s.reindex(s.index.union(idx)).ffill().reindex(idx).fillna(0.0)

    v = pd.DataFrame(index=idx)
    v["stueck"] = taeglich(b.stueck_tag)
    v["einstand"] = taeglich(b.einstand_isin_tag)
    v["kurs"] = preise[isin].reindex(preise.index.union(idx)).ffill().reindex(idx) if isin in preise else float("nan")
    v["marktwert"] = v["stueck"] * v["kurs"].fillna(0.0)
    cash = buchungen.dropna(subset=["konto"]).groupby("buchtag")["konto"].sum()
    v["investiert_netto"] = (-cash).reindex(idx, fill_value=0.0).cumsum()
    v.index.name = "datum"

    kaeufe = buchungen[buchungen["art"] == "kauf"]
    verkaeufe = buchungen[buchungen["art"] == "verkauf"]
    real = b.realisiert[b.realisiert["isin"] == isin]
    ende = v.iloc[-1]
    div = float(ertraege.loc[ertraege["kategorie"].isin(["dividende", "ausschuettung"]), "betrag"].sum())
    steuer = float(ertraege.loc[ertraege["kategorie"] == "steuer", "betrag"].sum())
    summe = {
        "stueck": float(ende["stueck"]),
        "einstand": float(ende["einstand"]),
        "marktwert": float(ende["marktwert"]),
        "unrealisiert": float(ende["marktwert"] - ende["einstand"]),
        "kurs": None if pd.isna(ende["kurs"]) else float(ende["kurs"]),
        "kaeufe": int(len(kaeufe)), "verkaeufe": int(len(verkaeufe)),
        "gekauft_eur": float(-kaeufe["konto"].sum()) if len(kaeufe) else 0.0,
        "verkauft_eur": float(verkaeufe["konto"].sum()) if len(verkaeufe) else 0.0,
        "gebuehren": float(kaeufe["gebuehr"].sum(skipna=True)) if len(kaeufe) else 0.0,
        "realisiert": float(real["kursgewinn"].sum()) if len(real) else 0.0,
        "ertraege": div,
        "steuer_thesaurierung": -steuer,
        # Gesamtergebnis: heutiger Wert + alles Zurückbekommene - alles Bezahlte
        "ergebnis": float(ende["marktwert"] - ende["investiert_netto"] + div + steuer),
    }
    summe["ergebnis_pct"] = summe["ergebnis"] / summe["gekauft_eur"] * 100 if summe["gekauft_eur"] else None
    return PositionDetail(isin, name, buchungen, ertraege, v, summe)


def ertraege_monatlich(d: Daten) -> pd.DataFrame:
    k = d.konto[d.konto["kategorie"].isin(["dividende", "ausschuettung", "zinsen"])].copy()
    k["monat"] = k["buchtag"].dt.to_period("M").dt.to_timestamp()
    p = k.pivot_table(index="monat", columns="kategorie", values="betrag", aggfunc="sum", fill_value=0)
    months = pd.date_range(pd.Timestamp(d.von).to_period("M").to_timestamp(),
                           pd.Timestamp(d.bis).to_period("M").to_timestamp(), freq="MS")
    p = p.reindex(months, fill_value=0)
    for c in ("dividende", "ausschuettung", "zinsen"):
        if c not in p:
            p[c] = 0.0
    return p[["dividende", "ausschuettung", "zinsen"]]


def handel_monatlich(d: Daten) -> pd.DataFrame:
    t = trades(d)
    t["monat"] = t["buchtag"].dt.to_period("M").dt.to_timestamp()
    p = t.pivot_table(index="monat", columns="art", values="kurswert", aggfunc="sum", fill_value=0)
    months = pd.date_range(pd.Timestamp(d.von).to_period("M").to_timestamp(),
                           pd.Timestamp(d.bis).to_period("M").to_timestamp(), freq="MS")
    p = p.reindex(months, fill_value=0)
    for c in ("kauf", "verkauf"):
        if c not in p:
            p[c] = 0.0
    return p[["kauf", "verkauf"]]


def kennzahlen(d: Daten) -> dict:
    k = d.konto
    s = lambda cat: float(k.loc[k["kategorie"] == cat, "betrag"].sum())  # noqa: E731
    tr = trades(d)
    offen, real = positionen(d)
    return {
        "einzahlungen": s("einlage"),
        "auszahlungen": -s("auszahlung"),
        "einzahlungen_netto": s("einlage") + s("auszahlung"),
        "kontostand": float(k["betrag"].sum()),
        "einstand_offen": float(offen["einstand"].sum()) if len(offen) else 0.0,
        "positionen": int(len(offen)),
        "kaeufe": int((tr["art"] == "kauf").sum()),
        "verkaeufe": int((tr["art"] == "verkauf").sum()),
        "kaufgebuehren": float(tr["gebuehr"].sum(skipna=True)),
        "abzuege_verkauf": float(tr["abzuege_verkauf"].sum(skipna=True)),
        "kursgewinn_realisiert": float(real["kursgewinn"].sum()) if len(real) else 0.0,
        "netto_realisiert": float(real["netto"].sum()) if len(real) else 0.0,
        "dividenden": s("dividende"),
        "ausschuettungen": s("ausschuettung"),
        "zinsen": s("zinsen"),
        "steuer_thesaurierung": -s("steuer"),
        "nicht_zugeordnet": int((k["kategorie"] == "sonstige").sum()),
    }
