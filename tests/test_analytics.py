"""Auswertung mit einem nachrechenbaren Beispiel (Texte wie in echten flatex-Exporten)."""

from datetime import date

import pandas as pd
import pytest

from flatex import analytics as a

ISIN = "IE00B4L5Y983"


def _daten():
    konto = pd.DataFrame([
        (1, "2023-05-02", 100000, "Einlage"),
        (2, "2023-05-05", -50100, f"Ausführung ORDER Kauf {ISIN} 111"),
        (3, "2023-06-30", -550, f"Thesaurierung transparenterFonds {ISIN}"),
        (4, "2023-07-10", 29500, f"Ausführung ORDER Verkauf {ISIN} 222"),
        (5, "2023-07-20", 300, "Dividendenzahlung US0378331005"),
        (6, "2023-07-31", 0, "Zinsabschluss  01.07.2023 -30.09.2023"),
    ], columns=["id", "buchtag", "betrag_cent", "text"])
    depot = pd.DataFrame([
        (1, "2023-05-05", ISIN, "ETF", 10.0, 50000, f"Ausführung ORDER Kauf {ISIN} 111"),
        (2, "2023-06-30", ISIN, "ETF", -10.0, -50000, f"Thesaurierung transparenter Fonds {ISIN}"),
        (3, "2023-06-30", ISIN, "ETF", 10.0, 52000, f"Thesaurierung transparenter Fonds {ISIN}"),
        (4, "2023-07-10", ISIN, "ETF", -5.0, -30000, f"Ausführung ORDER Verkauf {ISIN} 222"),
    ], columns=["id", "buchtag", "isin", "bezeichnung", "stueck", "betrag_cent", "text"])
    depot["kurs"] = (depot["betrag_cent"] / 100 / depot["stueck"]).abs()
    return a.prepare(konto, depot, date(2023, 5, 1), date(2023, 7, 31))


def test_einzahlung_am_gegenkonto_erkannt():
    namen = ["Max Muster", "AT61 1904 3002 3457 3201"]
    # Text unbekannt, aber Gegenkonto = eigener Name/IBAN -> Ein-/Auszahlung nach Vorzeichen
    assert a.kategorie("Neuer Text", 50000, "MAX  MUSTER", namen) == "einlage"
    assert a.kategorie("SEPA", -20000, "BIC/AT611904300234573201", namen) == "auszahlung"   # IBAN ohne Leerzeichen
    assert a.kategorie("Neuer Text", 50000, "Fremde Firma GmbH", namen) == "sonstige"      # fremdes Konto sichtbar
    assert a.kategorie("Neuer Text", 50000, "Fremde Firma GmbH", []) == "einlage"           # ohne Liste: jedes Gegenkonto
    assert a.kategorie("Irgendein neuer Text", 50000) == "sonstige"                         # ohne Gegenkonto: kein Raten
    assert a.kategorie("Einlage", 50000) == "einlage"                                        # Rückfall über Text
    konto = pd.DataFrame([
        (1, "2023-05-02", 100000, "Mein neuer Buchungstext", "Max Muster", '{"Zahlungspfl.": "AT00 1234"}'),
        (2, "2023-05-03", 5000, f"Dividendenzahlung {ISIN}", None, '{"Zahlungspfl.": ""}'),
    ], columns=["id", "buchtag", "betrag_cent", "text", "empfaenger", "raw_json"])
    depot = pd.DataFrame(columns=["id", "buchtag", "isin", "bezeichnung", "stueck", "betrag_cent", "text", "kurs"])
    d = a.prepare(konto, depot, date(2023, 5, 1), date(2023, 5, 31), namen)
    assert list(d.konto["kategorie"]) == ["einlage", "dividende"]


def test_xirr_known_value():
    assert a.xirr([(date(2023, 1, 1), -1000), (date(2024, 1, 1), 1100)]) == pytest.approx(0.10, abs=1e-4)
    assert a.xirr([(date(2023, 1, 1), -1000)]) is None


def _preise(werte: dict[str, float]):
    idx = pd.date_range("2023-04-25", "2023-07-31", freq="D")
    p = pd.DataFrame({ISIN: 50.0}, index=idx)
    for tag, preis in werte.items():
        p.loc[pd.Timestamp(tag):, ISIN] = preis
    return p


def test_marktwert_und_twr():
    d = _daten()
    v = a.verlauf_markt(d, _preise({"2023-06-01": 60.0}))
    assert v.loc["2023-05-05", "depotwert"] == pytest.approx(500)       # 10 Stück x 50
    assert v.loc["2023-06-01", "depotwert"] == pytest.approx(600)       # Kurs steigt auf 60
    assert v.loc["2023-07-31", "depotwert"] == pytest.approx(300)       # 5 Stück x 60
    assert v.loc["2023-07-31", "vermoegen"] == pytest.approx(v.loc["2023-07-31", "kontostand"] + 300)
    # Mai: nur die Kaufgebühr (1 €) kostet Rendite: 999/1000
    assert a.rendite_zeitraum(v, date(2023, 5, 1), date(2023, 5, 31)) == pytest.approx(-0.001, abs=1e-6)
    # Juni: Kurssprung +100 € auf 999 € Vermögen
    assert a.rendite_zeitraum(v, date(2023, 6, 1), date(2023, 6, 1)) == pytest.approx(100 / 999, abs=1e-6)


def test_einzahlung_ist_kein_gewinn():
    d = _daten()
    konto = d.konto.copy()
    extra = konto.iloc[[0]].copy()
    extra["id"], extra["buchtag"], extra["betrag"], extra["betrag_cent"] = 99, pd.Timestamp("2023-05-20"), 5000.0, 500000
    d2 = a.Daten(pd.concat([konto, extra]).sort_values("buchtag"), d.depot, d.von, d.bis)
    v1 = a.verlauf_markt(d, _preise({}))
    v2 = a.verlauf_markt(d2, _preise({}))
    assert a.rendite_zeitraum(v2, date(2023, 5, 1), date(2023, 5, 31)) == \
        pytest.approx(a.rendite_zeitraum(v1, date(2023, 5, 1), date(2023, 5, 31)), abs=1e-6)
    assert v2.iloc[-1]["gewinn"] == pytest.approx(v1.iloc[-1]["gewinn"])


def test_positionen_markt():
    offen = a.positionen_markt(_daten(), _preise({"2023-06-01": 60.0}))
    assert offen.loc[0, "marktwert"] == pytest.approx(300)
    assert offen.loc[0, "unrealisiert"] == pytest.approx(300 - 250.5)


def test_trades_fees_and_deductions():
    t = a.trades(_daten())
    assert list(t["art"]) == ["kauf", "verkauf"]
    assert t.loc[0, "gebuehr"] == pytest.approx(1.0)          # 501 Konto - 500 Kurswert
    assert t.loc[1, "abzuege_verkauf"] == pytest.approx(5.0)  # 300 Kurswert - 295 Gutschrift


def test_positions_moving_average_with_thesaurierung():
    offen, real = a.positionen(_daten())
    # Bezahlt 501 für 10 Stück; Thesaurierung erhöht nur den steuerlichen Einstand (+20 -> 521).
    # Verkauf 5 Stück -> Anteil 250,50 (steuerlich 260,50)
    assert offen.loc[0, "stueck"] == pytest.approx(5)
    assert offen.loc[0, "einstand"] == pytest.approx(250.5)
    assert offen.loc[0, "einstand_steuer"] == pytest.approx(260.5)
    assert real.loc[0, "kursgewinn"] == pytest.approx(49.5)
    assert real.loc[0, "kursgewinn_steuerlich"] == pytest.approx(39.5)
    assert real.loc[0, "netto"] == pytest.approx(44.5)


def test_position_detail_ergebnis_stimmt_mit_gesamtgewinn():
    d = _daten()
    preise = _preise({"2023-06-01": 60.0})
    p = a.position_detail(d, ISIN, preise)
    s = p.summe
    assert list(p.buchungen["art"]) == ["kauf", "thesaurierung", "thesaurierung", "verkauf"]
    assert p.buchungen.loc[0, "gebuehr"] == pytest.approx(1.0)
    assert (s["stueck"], s["marktwert"], s["einstand"]) == (pytest.approx(5), pytest.approx(300), pytest.approx(250.5))
    assert s["steuer_thesaurierung"] == pytest.approx(5.5)
    # Wert 300 - (501 bezahlt - 295 zurück) - 5,50 KESt = 88,50
    assert s["ergebnis"] == pytest.approx(88.5)
    assert p.verlauf.loc["2023-06-15", "investiert_netto"] == pytest.approx(501)
    # Gegenprobe: Positionsergebnis + Dividende eines anderen Papiers = Gesamtgewinn des Depots
    v = a.verlauf_markt(d, preise)
    assert s["ergebnis"] + 3.0 == pytest.approx(v.iloc[-1]["gewinn"])


def test_kennzahlen_und_verlauf():
    d = _daten()
    k = a.kennzahlen(d)
    assert k["einzahlungen_netto"] == pytest.approx(1000)
    assert k["kontostand"] == pytest.approx(1000 - 501 - 5.5 + 295 + 3)
    assert k["kaufgebuehren"] == pytest.approx(1.0)
    assert k["steuer_thesaurierung"] == pytest.approx(5.5)
    assert k["dividenden"] == pytest.approx(3.0)
    assert k["nicht_zugeordnet"] == 0
    v = a.verlauf(d)
    assert v.index[0] == pd.Timestamp("2023-05-01") and v.index[-1] == pd.Timestamp("2023-07-31")
    assert v.loc["2023-05-05", "einstand"] == pytest.approx(501)
    assert v.loc["2023-06-30", "einstand"] == pytest.approx(501)   # Thesaurierung ändert bezahltes Geld nicht
    assert v.iloc[-1]["vermoegen_einstand"] == pytest.approx(k["kontostand"] + 250.5)
    e = a.ertraege_monatlich(d)
    assert e.loc["2023-07-01", "dividende"] == pytest.approx(3.0)
