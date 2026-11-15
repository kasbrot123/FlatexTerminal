"""Kurstabelle und Prüfung – offline mit einer kleinen Test-Datenbank."""

from datetime import date

import pandas as pd
import pytest

from flatex import db, kurse


def _db(tmp_path):
    con = db.connect(tmp_path / "t.db")
    kurse.connect_schema(con)
    ins = ("INSERT INTO depot_umsaetze(row_hash, buchtag, isin, bezeichnung, stueck, kurs, kurs_waehrung, "
           "devisenkurs, betrag_cent, text, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,'{}')")
    con.execute(ins, ("a", "2023-06-05", "AAA", "Mit Kurs", 10, 50.0, "EUR", 1.0, 50000, "Ausführung ORDER Kauf AAA 1"))
    con.execute(ins, ("b", "2023-06-05", "BBB", "Delistet", 100, 2.0, "EUR", 1.0, 20000, "Ausführung ORDER Kauf BBB 2"))
    con.execute(ins, ("c", "2023-06-20", "BBB", "Delistet", -50, 1.5, "EUR", 1.0, -7500, "Ausführung ORDER Verkauf BBB 3"))
    for tag, close in (("2023-06-02", 49.0), ("2023-06-05", 50.5), ("2023-06-06", 51.0)):
        con.execute("INSERT INTO kurse VALUES ('AAA', ?, ?, ?)", (tag, close, close))
    con.commit()
    return con


def test_preis_tabelle_mit_ersatzkurs(tmp_path):
    con = _db(tmp_path)
    p, ersatz = kurse.preis_tabelle(con, date(2023, 6, 30))
    assert ersatz == {"BBB"}
    assert p.loc[pd.Timestamp("2023-06-10"), "AAA"] == pytest.approx(51.0)  # Wochenende/Lücke: letzter Kurs
    assert p.loc[pd.Timestamp("2023-06-10"), "BBB"] == pytest.approx(2.0)   # flatex-Kaufkurs
    assert p.loc[pd.Timestamp("2023-06-30"), "BBB"] == pytest.approx(1.5)   # letzter flatex-Verkaufskurs


def test_pruefung_erkennt_falsche_einheit(tmp_path):
    con = _db(tmp_path)
    con.execute("INSERT INTO wertpapiere(isin, ticker, quelle) VALUES ('AAA','AAA.DE','auto')")
    res = kurse.pruefen(con, log=lambda *a: None)
    assert res.set_index("isin").loc["AAA", "abweichung"] == pytest.approx(0.01, abs=0.001)
    # Kurse in Cent statt Euro (Faktor 100) -> deutliche Abweichung
    con.execute("UPDATE kurse SET close_eur = close_eur * 100")
    meldungen = []
    res = kurse.pruefen(con, log=meldungen.append)
    assert res.set_index("isin").loc["AAA", "abweichung"] > kurse.WARN_ABWEICHUNG
    assert any("WARNUNG AAA" in m for m in meldungen)
