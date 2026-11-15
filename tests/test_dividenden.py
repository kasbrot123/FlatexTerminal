"""Dividenden: Abgleich mit Konto und Prognose – offline mit kleiner Test-Datenbank."""

from datetime import date

import pandas as pd
import pytest

from flatex import analytics as a
from flatex import db, dividenden, kurse

ISIN = "US0378331005"


def _setup(tmp_path):
    con = db.connect(tmp_path / "t.db")
    kurse.connect_schema(con)
    con.execute("INSERT INTO wertpapiere(isin, bezeichnung, ticker, waehrung, quelle) VALUES (?,?,?,?,?)",
                (ISIN, "APPLE", "AAPL", "USD", "auto"))
    con.execute("INSERT INTO fx VALUES ('USD', '2023-12-29', 1.10)")
    for ex, betrag in (("2023-02-10", 0.23), ("2023-05-12", 0.24), ("2023-08-11", 0.24), ("2023-11-10", 0.24)):
        con.execute("INSERT INTO dividenden_yahoo VALUES (?,?,?)", (ISIN, ex, betrag))
    con.commit()
    konto = pd.DataFrame([
        (1, "2023-01-02", -55000, f"Ausführung ORDER Kauf {ISIN} 1"),
        (2, "2023-08-18", round(10 * 0.24 / 1.10 * 0.725 * 100), f"Dividendenzahlung {ISIN}"),
    ], columns=["id", "buchtag", "betrag_cent", "text"])
    depot = pd.DataFrame([(1, "2023-01-02", ISIN, "APPLE", 10.0, 54500, f"Ausführung ORDER Kauf {ISIN} 1")],
                         columns=["id", "buchtag", "isin", "bezeichnung", "stueck", "betrag_cent", "text"])
    depot["kurs"] = 54.5
    d = a.prepare(konto, depot, date(2023, 1, 1), date(2023, 12, 31))
    return con, d, a.bestand(d)


def test_abgleich_mit_kontogutschrift(tmp_path):
    con, d, b = _setup(tmp_path)
    ab = dividenden.abgleich(con, d, b)
    assert len(ab) == 1
    r = ab.iloc[0]
    assert r["stueck"] == 10 and r["versatz_tage"] == 7
    assert abs(r["abweichung"]) < 0.01                    # Yahoo-Brutto ≈ Konto-Netto / 0,725


def test_prognose_naechste_12_monate(tmp_path):
    con, d, b = _setup(tmp_path)
    e = dividenden.erwartet(con, d, b, date(2023, 12, 31), 12, {ISIN: "APPLE"})
    assert len(e) == 4                                    # Quartalsrhythmus fortgeschrieben
    assert e["brutto"].iloc[0] == pytest.approx(10 * 0.23 / 1.10)
    assert (e["d"] - e["ex"]).dt.days.iloc[0] == 7         # Zahltag-Versatz aus der eigenen Historie
    assert e["netto"].sum() == pytest.approx(e["brutto"].sum() * 0.725)
    assert set(e["quelle"]) == {"Prognose"}
