from datetime import date

from flatex import db, store
from flatex.parse.umsaetze import parse_bytes, parse_number
from flatex.portal.postfach import parse_entries
from flatex.portal.session import replace_portions_html

# Echtes flatex.at-Format des Kontoexports (Werte erfunden): Währungsspalte ohne Überschrift, cp1252.
KONTO_CSV = (
    "Buchungstag;Valuta;Empfänger;Zahlungspfl.;TA.Nr.;Buchungsinformationen;Betrag;\r\n"
    "03.03.2024;03.03.2024;Max Muster;BIC/AT000000000000000000;100001;Investment Sparplan;1.000,00;EUR\r\n"
    "05.03.2024;07.03.2024;;;100002;Ausführung ORDER Kauf IE00B4L5Y983 123;-250,50;EUR\r\n"
    "05.03.2024;07.03.2024;;;100002;Ausführung ORDER Kauf IE00B4L5Y983 123;-250,50;EUR\r\n"
).encode("cp1252")

# Echtes flatex.at-Format des Depotexports (Werte erfunden): drei Spalten ohne Überschrift.
DEPOT_CSV = (
    "Buchungstag;Valuta;Bezeichnung;ISIN;Nominal (Stk.);;Betrag;;Kurs;;Devisenkurs;TA.-Nr.;Buchungsinformation\r\n"
    "05.03.2024;07.03.2024;ISHSIII-CORE MSCI WLD;IE00B4L5Y983;3,123;Stück;250,50;EUR;80,21;USD;1,085;100002;"
    "Ausführung ORDER Kauf IE00B4L5Y983 123\r\n"
).encode("cp1252")


def test_numbers():
    assert str(parse_number("1.234,56")) == "1234.56"
    assert str(parse_number("-0,5")) == "-0.5"
    assert parse_number("") is None


def test_konto_csv():
    rows = parse_bytes(KONTO_CSV, "csv")
    assert [r.art for r in rows] == ["konto"] * 3
    assert rows[0].buchtag == date(2024, 3, 3) and rows[0].betrag_cent == 100000
    assert rows[1].valuta == date(2024, 3, 7) and rows[1].betrag_cent == -25050
    assert rows[0].waehrung == "EUR" and rows[0].ta_nr == "100001" and rows[0].empfaenger == "Max Muster"
    assert rows[1].text.startswith("Ausführung ORDER Kauf")
    # zwei identische Zeilen bleiben zwei Zeilen
    assert rows[1].row_hash != rows[2].row_hash


def test_depot_csv_and_dedupe(tmp_path):
    rows = parse_bytes(DEPOT_CSV, "csv")
    r = rows[0]
    assert r.art == "depot" and r.isin == "IE00B4L5Y983" and r.stueck == 3.123
    assert (r.betrag_cent, r.waehrung, r.kurs, r.kurs_waehrung, r.devisenkurs, r.ta_nr) == \
        (25050, "EUR", 80.21, "USD", 1.085, "100002")
    assert r.raw["Einheit"] == "Stück"
    con = db.connect(tmp_path / "t.db")
    assert store.upsert(con, rows, "a.csv") == 1
    assert store.upsert(con, rows, "a.csv") == 0  # erneuter Import ändert nichts


def test_postfach_anderer_praefix_und_attributreihenfolge():
    from flatex.portal.postfach import knopf_anzahl

    w = "secondLevelWidgetList[0].secondLevelContentWidget"
    html_ = (
        '<div class="DocumentDate CategoryLabel"><!-- a -->02.10.2023</div>'
        f'<div data-widgetname="{w}.children[0].btnOpenDocument" role="button" class="DocumentArchiveListEntryWidget">'
        '<div class="Description">Sammelabrechnung</div></div>'
        f'<a data-widgetname="{w}.children[0].btnOpenDocument" href="#">PDF</a>'          # zweiter Knopf, gleicher Index
        f'<div class="Irgendwas Unread" data-widgetname="{w}.children[1].btnOpenDocument">'
        '<div class="Description">Dividende ausländische WP</div></div>'
    )
    docs = parse_entries(html_)
    assert [(d.index, d.name, d.gelesen) for d in docs] == [
        (0, "Sammelabrechnung", True), (1, "Dividende ausländische WP", False)]
    assert all(d.datum == date(2023, 10, 2) for d in docs)
    assert knopf_anzahl(html_) == 2


def test_postfach_entries():
    html_ = (
        '<div class="DocumentDate CategoryLabel">16.07.2026</div>'
        '<div class="DocumentArchiveListEntryWidget EntryWidget Unread" data-widgetname='
        '"fullScreenSecondLevelWidgetList[0].secondLevelContentWidget.children[4].btnOpenDocument">'
        '<div class="DocumentArchiveListEntryWidgetEntryRow"><div class="Description">Wertpapierabrechnung Kauf'
        "</div></div></div>"
    )
    body = '{"commands":[{"command":"replacePortions","deltasToApply":["id1", %s]}]}' % __import__("json").dumps(html_)
    docs = parse_entries(replace_portions_html(body))
    assert len(docs) == 1
    d = docs[0]
    assert (d.index, d.datum, d.name, d.gelesen) == (4, date(2026, 7, 16), "Wertpapierabrechnung Kauf", False)
