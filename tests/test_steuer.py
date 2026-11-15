"""Steueranalyse – ohne PDFs (geschätzt) und mit den synthetischen Beispiel-PDFs aus flatex-pdf-cli."""

import json
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from flatex import analytics as a
from flatex import steuer
from flatex.config import load

FIX = Path(__file__).parent / "fixtures" / "pdfs"
SP500 = "IE00BFMXXD54"   # wie in verkauf_sample_1.pdf
VWRL = "IE00B3RBWM25"    # wie in dividend_sample_1.pdf
LOSER = "US0000000001"


def _daten():
    konto = pd.DataFrame([
        (1, "2024-01-02", 500000, "Einlage"),
        (2, "2024-01-10", -112590, f"Ausführung ORDER Kauf {SP500} 111"),
        (3, "2024-02-01", -50590, f"Ausführung ORDER Kauf {LOSER} 222"),
        (4, "2024-12-18", 150708, f"Ausführung ORDER Verkauf {SP500} 990000099"),
        (5, "2024-12-19", 30000, f"Ausführung ORDER Verkauf {LOSER} 333"),
        (6, "2025-10-01", 2243, f"Dividendenzahlung {VWRL}"),
    ], columns=["id", "buchtag", "betrag_cent", "text"])
    depot = pd.DataFrame([
        (1, "2024-01-10", SP500, "S&P 500", 14.0, 112000, f"Ausführung ORDER Kauf {SP500} 111"),
        (2, "2024-02-01", LOSER, "Verlierer", 10.0, 50000, f"Ausführung ORDER Kauf {LOSER} 222"),
        (3, "2024-12-18", SP500, "S&P 500", -14.0, -154000, f"Ausführung ORDER Verkauf {SP500} 990000099"),
        (4, "2024-12-19", LOSER, "Verlierer", -10.0, -30500, f"Ausführung ORDER Verkauf {LOSER} 333"),
    ], columns=["id", "buchtag", "isin", "bezeichnung", "stueck", "betrag_cent", "text"])
    depot["kurs"] = (depot["betrag_cent"] / 100 / depot["stueck"]).abs()
    return a.prepare(konto, depot, date(2024, 1, 1), date(2025, 12, 31))


def test_ohne_pdf_geschaetzt():
    d = _daten()
    vk = steuer.veraeusserungen(d)
    sp = vk[vk["isin"] == SP500].iloc[0]
    assert sp["gewinn"] == pytest.approx(1540 - 1120)          # Gebühren zählen steuerlich nicht
    assert sp["abzuege"] == pytest.approx(1540 - 1507.08)      # Gebühr + KESt gemeinsam
    assert sp["quelle"] == "geschätzt" and pd.isna(sp["kest_bezahlt"])
    # typische Gebühr = Median der Kaufgebühren (5,90 €) -> geschätzte KESt = Abzüge - 5,90
    assert steuer.typische_gebuehr(d) == pytest.approx(5.90)
    assert sp["kest_geschaetzt"] == pytest.approx(32.92 - 5.90)
    er = steuer.ertraege(d)
    assert er.iloc[0]["brutto"] == pytest.approx(22.43 / 0.725)
    j = {x.jahr: x for x in steuer.jahre(vk, er)}
    # 2024: Gewinn 420, Verlust -195 -> Bemessung 225
    assert j[2024].gewinne == pytest.approx(420) and j[2024].verluste == pytest.approx(-195)
    assert j[2024].bemessung == pytest.approx(225) and j[2024].kest_soll == pytest.approx(225 * 0.275)
    assert any("verrechnet" in h for h in j[2024].hinweise)


@pytest.mark.parametrize("weg", ["ta_nr", "order", "isin_datum_stueck"])
def test_pdf_zuordnung_drei_wege(weg):
    d = _daten()
    d.depot["ta_nr"] = None
    pdf_zeile = {"document_type": "TRADE", "type": "SELL", "isin": SP500, "quantity": 14, "trade_date": "2024-12-18",
                 "gain_loss": 403.97, "withholding_tax": 24.51, "costs": {"total": 8.41},
                 "order_number": "111111111/1", "transaction_number": "0000000000"}
    if weg == "ta_nr":                         # Ordernummer passt NICHT, TA.-Nr. schon
        d.depot.loc[d.depot["order_nr"] == "990000099", "ta_nr"] = "7000000042"
        pdf_zeile["transaction_number"] = "7000000042"
    elif weg == "order":
        pdf_zeile["order_number"] = "990000099/1"
    else:                                      # keine Nummer passt -> ISIN + Datum + Stück
        pdf_zeile["trade_date"] = "2024-12-17"
    vk = steuer.veraeusserungen(d, pd.DataFrame([pdf_zeile]))
    sp = vk[vk["isin"] == SP500].iloc[0]
    assert sp["quelle"] == "PDF" and sp["kest_bezahlt"] == pytest.approx(24.51)
    assert vk[vk["isin"] == LOSER].iloc[0]["quelle"] == "geschätzt"   # anderes Papier bleibt unberührt


def test_verlustueberhang_verfaellt():
    vk = pd.DataFrame([{"d": pd.Timestamp("2024-05-01"), "gewinn": -300.0, "kest_bezahlt": None, "abzuege": 5.0}])
    er = pd.DataFrame([{"d": pd.Timestamp("2024-06-01"), "art": "dividende", "brutto": 100.0, "steuer": 27.5,
                        "quellensteuer": None, "netto": 72.5, "quelle": "geschätzt"}])
    j = steuer.jahre(vk, er)[0]
    assert j.bemessung == 0 and j.kest_soll == 0
    assert any("verfällt" in h for h in j.hinweise)


@pytest.mark.skipif(not load().pdf_cli.exists(), reason="flatex-pdf-cli nicht installiert")
def test_mit_beispiel_pdfs_exakt():
    cli = str(load().pdf_cli)
    rows = []
    for f in ("verkauf_sample_1.pdf", "dividend_sample_1.pdf"):
        out = subprocess.run([cli, "-format", "json", "-quiet", str(FIX / f)], capture_output=True, text=True,
                             encoding="utf-8").stdout
        rows += json.loads(out)
    pdf = pd.DataFrame(rows)
    d = _daten()
    vk = steuer.veraeusserungen(d, pdf)
    sp = vk[vk["isin"] == SP500].iloc[0]
    assert sp["quelle"] == "PDF"
    assert sp["gewinn"] == pytest.approx(403.97) and sp["kest_bezahlt"] == pytest.approx(24.51)
    assert sp["gebuehren"] == pytest.approx(8.41)
    er = steuer.ertraege(d, pdf)
    div = er.iloc[0]
    assert div["quelle"] == "PDF"
    assert div["brutto"] == pytest.approx(31.47 / 1.1724, abs=0.01)    # USD -> EUR
    assert div["quellensteuer"] == pytest.approx(4.41)
    j = {x.jahr: x for x in steuer.jahre(vk, er)}
    assert j[2024].kest_bezahlt == pytest.approx(24.51)
    assert j[2025].davon_geschaetzt == 0


def test_age_aus_thesaurierung():
    etf = "IE00B4L5Y983"          # Beispiel-ETF, erfundene Beträge
    konto = pd.DataFrame([
        (1, "2023-06-13", -100500, f"Ausführung ORDER Kauf {etf} 1"),
        (2, "2023-07-05", -1375, f"Thesaurierung transparenterFonds {etf}"),
    ], columns=["id", "buchtag", "betrag_cent", "text"])
    depot = pd.DataFrame([
        (1, "2023-06-13", etf, "ETF", 10.0, 100000, f"Ausführung ORDER Kauf {etf} 1"),
        (2, "2023-07-05", etf, "ETF", -10.0, -100000, f"Thesaurierung transparenter Fonds {etf}"),
        (3, "2023-07-05", etf, "ETF", 10.0, 105000, f"Thesaurierung transparenter Fonds {etf}"),
    ], columns=["id", "buchtag", "isin", "bezeichnung", "stueck", "betrag_cent", "text"])
    depot["kurs"] = (depot["betrag_cent"] / 100 / depot["stueck"]).abs()
    d = a.prepare(konto, depot, date(2023, 5, 1), date(2023, 12, 31))
    er = steuer.ertraege(d)
    age = er[er["art"] == "age"].iloc[0]
    assert age["brutto"] == pytest.approx(50.0) and age["steuer"] == pytest.approx(13.75)
    # steuerliche Anschaffungskosten: Kurswert ohne Gebühr + AGE
    o = steuer.offene_steuerlast(d, {etf: 110.0}).iloc[0]
    assert o["anschaffung"] == pytest.approx(1000.0 + 50.0)


def test_offene_steuerlast():
    d = _daten()
    # nur der Kauf bleibt offen, wenn wir die Verkäufe weglassen
    d2 = a.Daten(d.konto, d.depot[d.depot["art"] == "kauf"], d.von, d.bis)
    o = steuer.offene_steuerlast(d2, {SP500: 100.0, LOSER: 40.0}).set_index("isin")
    assert o.loc[SP500, "anschaffung"] == pytest.approx(1120)
    assert o.loc[SP500, "kest_latent"] == pytest.approx((1400 - 1120) * 0.275)
    assert o.loc[LOSER, "kest_latent"] == 0
