"""Export-Ablauf gegen ein nachgebautes Portal (HTML-Ausschnitte aus der echten Umsatzseite)."""

import json
from datetime import date

from flatex.portal.exports import UmsatzExporter

CATEGORY_HTML = (
    '<a href="#" class="BlockSelectionItem Selected" '
    'data-widgetname="children[16].secondLevelContentWidget.categorySelectionWidget.items[0]">Depotumsätze</a>'
    '<a href="#" class="BlockSelectionItem" '
    'data-widgetname="children[16].secondLevelContentWidget.categorySelectionWidget.items[1]">Kontoumsätze</a>'
)
CSV = "Buchtag;Valuta;Buchungsinformationen;Betrag;Währung\r\n03.03.2024;03.03.2024;Einzahlung;100,00;EUR\r\n"


def _portions(html: str) -> str:
    return json.dumps({"commands": [{"command": "replacePortions", "deltasToApply": ["x", html]}]})


class Resp:
    def __init__(self, content: bytes, headers=None):
        self.content, self.headers = content, headers or {}


class FakeSession:
    def __init__(self):
        self.posts, self.resyncs, self.log = [], 0, lambda *a: None
        self.last_page_html = ('<div class="HeaderAreaInfoButton PostingsHeaderAreaInfoButton" '
                               'data-widgetname="headerAreaWidget.headerAreaInfoButtons[3].linkOpenDetails">')

    def path(self, a):
        return "/next-desktop.at/" + a

    def post_form(self, path, form, label=None):
        self.posts.append(form)
        if any("headerAreaInfoButtons" in k for k in form):
            return _portions(CATEGORY_HTML)
        if any("btnDottedAction" in k for k in form):
            return json.dumps({"commands": [{"command": "download", "location": "/next-desktop.at/downloadData/x.csv"}]})
        return _portions("<div>Liste</div>")

    def plain_get(self, loc, label=None):
        assert loc.endswith("x.csv")
        return Resp(CSV.encode("cp1252"), {"content-disposition": 'attachment; filename="umsaetze.csv"'})


def test_empty_month_is_not_an_error():
    s = FakeSession()
    orig = s.post_form

    def post_form(path, form, label=None):
        if "thirdLevelWidgetList[0].btnApply.clicked" in form:
            s.posts.append(form)
            return _portions("<div>Keine Einträge im gewählten Zeitraum vorhanden</div>")
        return orig(path, form, label)

    s.post_form = post_form
    res = UmsatzExporter(s).export("depot", date(2023, 5, 1), date(2023, 5, 31))
    assert res.rows == [] and res.raw == b""
    assert not any("btnDottedAction" in k for p in s.posts for k in p)  # kein Export-Klick


def test_export_flow():
    s = FakeSession()
    ex = UmsatzExporter(s)
    res = ex.export("konto", date(2024, 3, 1), date(2024, 3, 31))
    assert len(res.rows) == 1 and res.rows[0].betrag_cent == 10000 and res.ext == "csv"
    keys = [list(p) for p in s.posts]
    assert keys[0] == ["headerAreaWidget.headerAreaInfoButtons[3].linkOpenDetails.clicked"]
    assert "children[16].secondLevelContentWidget.categorySelectionWidget.items[1].clicked" in keys[1]
    assert s.posts[1]["children[16].secondLevelContentWidget.categorySelectionWidget.selecteditemindex"] == "1"
    assert "children[16].secondLevelContentWidget.dateRangeSelectionWidget.children[7].link.clicked" in keys[2]
    assert s.posts[3]["thirdLevelWidgetList[0].dtStartDate.text"] == "01.03.2024"
    assert s.posts[3]["thirdLevelWidgetList[0].dtEndDate.text"] == "31.03.2024"
    assert "children[16].secondLevelContentWidget.btnDottedAction.children[1].clicked" in keys[4]

    # Zweiter Export derselben Quelle: keine erneute Navigation
    n = len(s.posts)
    ex.export("konto", date(2024, 4, 1), date(2024, 4, 30))
    assert len(s.posts) - n == 3
