"""Steueranalyse für ein österreichisches flatex-Depot (Privatvermögen, steuereinfach).

Regeln (vereinfacht, keine Steuerberatung):
- KESt 27,5 % auf Kursgewinne, Dividenden/Ausschüttungen und ausschüttungsgleiche Erträge (AGE);
  25 % auf Zinsen von Bankguthaben.
- Steuerliche Anschaffungskosten OHNE Gebühren (Nebenkosten sind nicht absetzbar), gleitender
  Durchschnitt je Wertpapier, erhöht um AGE thesaurierender Fonds.
- Verlustausgleich innerhalb eines Kalenderjahres über das Depot: Verluste mindern Gewinne und
  Dividenden; kein Verlustvortrag ins Folgejahr.

Datenquellen: Konto-/Depotumsätze (immer), Abrechnungs-PDFs (optional, über flatex-pdf-cli).
Wo ein PDF vorliegt, gelten dessen Werte (einbehaltene KESt, Quellensteuer, Bruttobeträge),
sonst wird geschätzt und als "geschätzt" markiert.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from flatex.analytics import Daten

KEST = 0.275
KEST_ZINSEN = 0.25


# --- PDF-Daten (optional) ------------------------------------------------------------------------

def pdf_daten(con: sqlite3.Connection) -> pd.DataFrame:
    rows = con.execute("SELECT document_type, json FROM pdf_transaktionen").fetchall()
    out = []
    for typ, j in rows:
        d = json.loads(j)
        d["document_type"] = typ
        out.append(d)
    return pd.DataFrame(out)


def _in_eur(betrag, waehrung, kurs) -> float | None:
    if betrag is None or (isinstance(betrag, float) and pd.isna(betrag)):
        return None
    if not waehrung or waehrung == "EUR" or not kurs:
        return float(betrag)
    return float(betrag) / float(kurs)


# --- Veräußerungen -----------------------------------------------------------------------------

def typische_gebuehr(d: Daten) -> float:
    """Median der eigenen Kaufgebühren – Schätzwert für die Gebühr eines Verkaufs ohne PDF."""
    from flatex.analytics import trades

    g = trades(d)["gebuehr"].dropna()
    return float(g.median()) if len(g) else 0.0


def _nr(x) -> str:
    """Nummer vergleichbar machen: ohne '/1'-Zusatz, ohne führende Nullen und Leerzeichen."""
    s = str(x or "").split("/")[0].strip().lstrip("0")
    return s if s and s.lower() not in ("nan", "none") else ""


def _pdf_verkauf_finder(pdf: pd.DataFrame | None):
    """Liefert eine Funktion, die zu einer Verkaufsbuchung im Depot das passende PDF findet:
    1. Transaktionsnummer (PDF) = TA.-Nr. (Depotexport)
    2. Ordernummer (PDF) = Ordernummer im Buchungstext
    3. ISIN + Handelstag (±3 Tage) + Stückzahl"""
    if pdf is None or not len(pdf) or "document_type" not in pdf:
        return lambda r, qs: None
    typ = pdf["type"] if "type" in pdf else pd.Series("", index=pdf.index)
    sells = [p for _, p in pdf[(pdf["document_type"] == "TRADE") & (typ == "SELL")].iterrows()]
    nach_ta = {_nr(p.get("transaction_number")): p for p in sells if _nr(p.get("transaction_number"))}
    nach_order = {_nr(p.get("order_number")): p for p in sells if _nr(p.get("order_number"))}

    def finde(r, qs: float):
        if (p := nach_ta.get(_nr(r.get("ta_nr")))) is not None:
            return p
        if (p := nach_order.get(_nr(r.get("order_nr")))) is not None:
            return p
        for p in sells:
            tag = p.get("trade_date") or p.get("value_date")
            if p.get("isin") == r["isin"] and tag and abs((pd.Timestamp(tag) - r["buchtag"]).days) <= 3 \
                    and abs(float(p.get("quantity") or 0) - qs) < 1e-6:
                return p
        return None

    return finde


def pdf_status(con: sqlite3.Connection, vk: pd.DataFrame, er: pd.DataFrame) -> dict:
    """Wie viele PDFs liegen vor, wie viele konnten gelesen und zugeordnet werden?"""
    docs = con.execute("SELECT name, pfad, geparst FROM dokumente WHERE pfad IS NOT NULL").fetchall()
    mit_tx = {p for (p,) in con.execute("SELECT DISTINCT pfad FROM pdf_transaktionen")}
    typen = dict(con.execute("SELECT document_type, COUNT(*) FROM pdf_transaktionen GROUP BY document_type").fetchall())
    ohne: dict[str, int] = {}
    for name, pfad, geparst in docs:
        if geparst and pfad not in mit_tx:
            ohne[name] = ohne.get(name, 0) + 1
    return {
        "dokumente": len(docs),
        "gelesen": len(mit_tx),
        "transaktionen": typen,
        "nicht_lesbar": sorted(({"name": n, "anzahl": a} for n, a in ohne.items()), key=lambda x: -x["anzahl"]),
        "verkaeufe": int(len(vk)),
        "verkaeufe_mit_pdf": int((vk["quelle"] == "PDF").sum()) if len(vk) else 0,
        "ertraege": int((er["art"] != "age").sum()) if len(er) else 0,
        "ertraege_mit_pdf": int((er["quelle"] == "PDF").sum()) if len(er) else 0,
    }


def veraeusserungen(d: Daten, pdf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Jeder Verkauf mit steuerlichem Gewinn/Verlust. Mit PDF: dessen gain_loss und KESt.
    Ohne PDF: KESt ≈ Abzüge (Kurswert − Gutschrift) − typische Gebühr."""
    gebuehr_schaetzung = typische_gebuehr(d)
    finde_pdf = _pdf_verkauf_finder(pdf)
    konto = d.konto.set_index("order_nr")["betrag"] if len(d.konto) else pd.Series(dtype=float)
    konto = konto[konto.index.notna()]
    konto = konto[~konto.index.duplicated()]

    state: dict[str, list[float]] = {}   # isin -> [stueck, anschaffungskosten]
    out = []
    for _, r in d.depot.sort_values(["buchtag", "id"]).iterrows():
        s = state.setdefault(r["isin"], [0.0, 0.0])
        q = float(r["stueck"] or 0)
        kw = abs(float(r["betrag"] or 0))
        if r["art"] == "kauf":
            s[0] += q
            s[1] += kw
        elif r["art"] == "thesaurierung":
            s[0] += q
            s[1] += float(r["betrag"] or 0)
        elif r["art"] == "verkauf":
            qs = abs(q)
            ak = s[1] / s[0] * qs if s[0] else 0.0
            s[0] -= qs
            s[1] -= ak
            if abs(s[0]) < 1e-9:
                s[0], s[1] = 0.0, 0.0
            gutschrift = konto.get(r["order_nr"]) if pd.notna(r["order_nr"]) else None
            p = finde_pdf(r, qs)
            gewinn = kw - ak
            kest_bezahlt, gebuehren, quelle = None, None, "geschätzt"
            if p is not None:
                gewinn = float(p.get("gain_loss", gewinn))
                kest_bezahlt = float(p.get("withholding_tax") or 0.0)
                c = p.get("costs")
                gebuehren = float(c.get("total", 0.0)) if isinstance(c, dict) else None
                quelle = "PDF"
            abzuege = kw - float(gutschrift) if gutschrift is not None and pd.notna(gutschrift) else None
            kest_geschaetzt = None
            if kest_bezahlt is None and abzuege is not None:
                kest_geschaetzt = max(abzuege - gebuehr_schaetzung, 0.0)
                gebuehren = min(gebuehr_schaetzung, abzuege)
            out.append({"d": r["buchtag"], "isin": r["isin"], "name": r["bezeichnung"], "stueck": qs,
                        "kurswert": kw, "anschaffung": ak, "gewinn": gewinn, "abzuege": abzuege,
                        "kest_bezahlt": kest_bezahlt, "kest_geschaetzt": kest_geschaetzt,
                        "gebuehren": gebuehren, "quelle": quelle})
        else:
            s[0] += q
    return pd.DataFrame(out, columns=["d", "isin", "name", "stueck", "kurswert", "anschaffung", "gewinn",
                                      "abzuege", "kest_bezahlt", "kest_geschaetzt", "gebuehren", "quelle"])


def offene_steuerlast(d: Daten, kurse_letzt: dict[str, float]) -> pd.DataFrame:
    """Steuerliche Anschaffungskosten offener Positionen und latente KESt bei Verkauf zum letzten Kurs."""
    state: dict[str, list] = {}
    for _, r in d.depot.sort_values(["buchtag", "id"]).iterrows():
        s = state.setdefault(r["isin"], [0.0, 0.0, r["bezeichnung"]])
        q = float(r["stueck"] or 0)
        if r["art"] == "kauf":
            s[0] += q
            s[1] += abs(float(r["betrag"] or 0))
        elif r["art"] == "thesaurierung":
            s[0] += q
            s[1] += float(r["betrag"] or 0)
        elif r["art"] == "verkauf":
            qs = abs(q)
            s[1] -= s[1] / s[0] * qs if s[0] else 0.0
            s[0] -= qs
        else:
            s[0] += q
    out = []
    for isin, (st, ak, name) in state.items():
        if st <= 1e-9:
            continue
        kurs = kurse_letzt.get(isin)
        wert = st * kurs if kurs is not None and pd.notna(kurs) else None
        g = None if wert is None else wert - ak
        out.append({"isin": isin, "name": name, "stueck": st, "anschaffung": ak, "wert": wert, "gewinn": g,
                    "kest_latent": None if g is None else max(g, 0.0) * KEST})
    return pd.DataFrame(out, columns=["isin", "name", "stueck", "anschaffung", "wert", "gewinn", "kest_latent"])


# --- Erträge -----------------------------------------------------------------------------------

def ertraege(d: Daten, pdf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Dividenden, Ausschüttungen, Zinsen und AGE mit Brutto, Steuer und Netto.

    Netto kommt aus dem Konto. Brutto/Quellensteuer aus dem PDF; ohne PDF wird angenommen,
    dass flatex die volle KESt einbehalten hat (Brutto = Netto / (1 − Satz))."""
    k = d.konto
    pdf_div = pdf[pdf["document_type"] == "DIVIDEND"] if pdf is not None and len(pdf) else pd.DataFrame()
    out = []
    for _, r in k[k["kategorie"].isin(["dividende", "ausschuettung", "zinsen"])].iterrows():
        netto = float(r["betrag"])
        if abs(netto) < 1e-9:
            continue
        satz = KEST_ZINSEN if r["kategorie"] == "zinsen" else KEST
        brutto, steuer, quelle, qst = netto / (1 - satz), None, "geschätzt", None
        if len(pdf_div) and pd.notna(r["isin"]):
            kand = pdf_div[pdf_div["isin"] == r["isin"]]
            if len(kand):
                diff = (pd.to_datetime(kand["value_date"]) - r["buchtag"]).abs()
                best = kand.loc[diff.idxmin()] if diff.min() <= pd.Timedelta(days=7) else None
                if best is not None:
                    b = _in_eur(best.get("gross_amount"), best.get("gross_currency"), best.get("exchange_rate"))
                    brutto = b if b is not None else brutto
                    qst = _in_eur(best.get("withholding_tax"), best.get("withholding_tax_currency"),
                                  best.get("exchange_rate"))
                    quelle = "PDF"
        steuer = brutto - netto
        out.append({"d": r["buchtag"], "art": r["kategorie"], "isin": r["isin"] if pd.notna(r["isin"]) else None,
                    "brutto": brutto, "steuer": steuer, "quellensteuer": qst, "netto": netto, "quelle": quelle})
    # Ausschüttungsgleiche Erträge thesaurierender Fonds (Depot-Umbuchung) + bezahlte KESt (Konto)
    dep = d.depot[d.depot["art"] == "thesaurierung"]
    for (tag, isin), g in dep.groupby(["buchtag", "isin"]):
        age = float(g["betrag"].sum())
        if abs(age) < 1e-9:
            continue
        kest = k[(k["kategorie"] == "steuer") & (k["isin"] == isin) & (k["buchtag"] == tag)]["betrag"].sum()
        out.append({"d": tag, "art": "age", "isin": isin, "brutto": age, "steuer": -float(kest),
                    "quellensteuer": None, "netto": 0.0, "quelle": "Konto"})
    return pd.DataFrame(out, columns=["d", "art", "isin", "brutto", "steuer", "quellensteuer", "netto", "quelle"])


# --- Jahresübersicht ---------------------------------------------------------------------------

@dataclass
class Jahr:
    jahr: int
    gewinne: float = 0.0
    verluste: float = 0.0
    dividenden: float = 0.0          # brutto inkl. Ausschüttungen
    age: float = 0.0
    zinsen: float = 0.0
    bemessung: float = 0.0           # nach Verlustausgleich (ohne Zinsen)
    kest_soll: float = 0.0
    kest_bezahlt: float = 0.0        # bekannt (Konto/PDF) + geschätzt
    davon_geschaetzt: float = 0.0
    quellensteuer: float = 0.0
    abzuege_verkauf_unbekannt: float = 0.0   # Verkaufsabzüge ohne PDF (Gebühr + KESt gemischt)
    hinweise: list[str] = field(default_factory=list)


def jahre(vk: pd.DataFrame, er: pd.DataFrame) -> list[Jahr]:
    alle = sorted(set(pd.to_datetime(vk["d"]).dt.year) | set(pd.to_datetime(er["d"]).dt.year))
    out = []
    for y in alle:
        j = Jahr(int(y))
        v = vk[pd.to_datetime(vk["d"]).dt.year == y]
        e = er[pd.to_datetime(er["d"]).dt.year == y]
        j.gewinne = float(v.loc[v["gewinn"] > 0, "gewinn"].sum())
        j.verluste = float(v.loc[v["gewinn"] < 0, "gewinn"].sum())
        j.dividenden = float(e.loc[e["art"].isin(["dividende", "ausschuettung"]), "brutto"].sum())
        j.age = float(e.loc[e["art"] == "age", "brutto"].sum())
        j.zinsen = float(e.loc[e["art"] == "zinsen", "brutto"].sum())
        j.bemessung = max(0.0, j.gewinne + j.verluste + j.dividenden + j.age)
        j.kest_soll = j.bemessung * KEST + max(j.zinsen, 0.0) * KEST_ZINSEN
        # bezahlt: Erträge (Konto/PDF bzw. geschätzt) + Verkäufe mit PDF
        e_bek = e[e["quelle"] != "geschätzt"]["steuer"].sum()
        e_ges = e[e["quelle"] == "geschätzt"]["steuer"].sum()
        v_pdf = v["kest_bezahlt"].dropna().sum()
        v_ges = v["kest_geschaetzt"].dropna().sum() if "kest_geschaetzt" in v else 0.0
        j.quellensteuer = float(e["quellensteuer"].dropna().sum())
        j.abzuege_verkauf_unbekannt = float(v.loc[v["kest_bezahlt"].isna(), "abzuege"].dropna().sum())
        j.kest_bezahlt = float(e_bek + e_ges + v_pdf + v_ges)
        j.davon_geschaetzt = float(e_ges + v_ges)
        if j.verluste < 0 and j.gewinne + j.dividenden + j.age > 0:
            j.hinweise.append("Verluste wurden mit Gewinnen und Erträgen desselben Jahres verrechnet.")
        if j.gewinne + j.verluste + j.dividenden + j.age < 0:
            j.hinweise.append("Das Jahr endet mit einem Verlustüberhang – er verfällt (kein Vortrag).")
        if j.abzuege_verkauf_unbekannt > 0:
            j.hinweise.append("Verkäufe ohne Abrechnungs-PDF: KESt = Abzüge minus typische Gebühr (geschätzt).")
        out.append(j)
    return out
