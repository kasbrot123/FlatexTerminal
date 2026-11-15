"""Tempo-Regeln und direkter Postfach-Download – offline mit nachgebautem Portal."""

import json
from datetime import date

import pytest

from flatex.portal.postfach import Postfach
from flatex.portal.session import ActionBudgetExhausted, Throttle


def test_throttle_pausen_und_limit():
    pausen = []
    t = Throttle(request_delay=(1, 1), action_pause=(2, 2), max_actions=130, burst_every=60,
                 burst_pause=(20, 20), sleep=pausen.append)
    for _ in range(130):
        t.action()
    assert pausen.count(20) == 2                 # nach Aktion 60 und 120 eine Verschnaufpause
    assert pausen.count(2) == 127                # sonst normale Aktionspause (erste Aktion ohne)
    with pytest.raises(ActionBudgetExhausted):
        t.action()
    t.request()
    assert t.requests_done == 1 and pausen[-1] == 1


def _session_mit_server(antworten):
    """Session gegen einen nachgebauten Server: Liste aus 'trennen' oder (status, text)."""
    import httpx

    from flatex.portal import session as sm

    folge = iter(antworten)

    def handler(request):
        a = next(folge)
        if a == "trennen":
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=request)
        return httpx.Response(a[0], text=a[1])

    sm.Session._transport = httpx.MockTransport(handler)
    try:
        s = sm.Session(throttle=Throttle(enabled=False), log=lambda *a: None)
    finally:
        sm.Session._transport = None
    s._transport = httpx.MockTransport(handler)   # auch für neu aufgebaute Verbindungen
    s.http = s._neuer_client()
    return s


def test_verbindungsabbruch_wird_einmal_wiederholt():
    s = _session_mit_server(["trennen", (200, "ok")])
    assert s.get_ajax("/x") == "ok"
    assert s.verbindungsabbrueche == 1


def test_wiederholte_abbrueche_sind_notbremse():
    from flatex.portal.session import PortalBlocked

    s = _session_mit_server(["trennen", (200, "a"), "trennen", (200, "b"), "trennen"])
    assert s.get_ajax("/1") == "a" and s.get_ajax("/2") == "b"
    with pytest.raises(PortalBlocked):
        s.get_ajax("/3")


class FakeSession:
    """Liefert für einen Dokument-Klick einen Download-Link – außer `kaputt` ist gesetzt
    (simuliert verlorenen Seitenzustand beim direkten Klick)."""

    debug_dir = None

    def __init__(self, kaputt: bool = False):
        self.posts, self.gets, self.kaputt = [], [], kaputt
        self.log = lambda *a: None

    def path(self, a):
        return "/next-desktop.at/" + a

    def post_form(self, path, form, label=None):
        self.posts.append(form)
        if any(k.endswith("btnOpenDocument.clicked") for k in form):
            if self.kaputt:
                self.kaputt = False
                return json.dumps({"commands": [{"command": "replacePortions", "deltasToApply": []}]})
            return json.dumps({"commands": [{"command": "execute",
                                             "script": 'DocumentViewer.display("/next-desktop.at/downloadData/1/a.pdf", "application/pdf")'}]})
        return json.dumps({"commands": [{"command": "replacePortions", "deltasToApply": ["x", ""]}]})

    def plain_get(self, loc, label=None):
        self.gets.append(loc)

        class R:
            content = b"%PDF-1.4 test"
            headers = {"content-disposition": 'attachment; filename="Abrechnung.pdf"'}
        return R()


def test_direkter_download_braucht_nur_zwei_anfragen():
    s = FakeSession()
    name, data = Postfach(s).download(date(2023, 7, 1), date(2023, 9, 30), 4, direkt=True)
    assert name == "Abrechnung.pdf" and data.startswith(b"%PDF")
    assert len(s.posts) == 1 and len(s.gets) == 1        # Klick + Datei


def test_direkter_download_faellt_bei_verlorenem_zustand_zurueck():
    s = FakeSession(kaputt=True)
    _, data = Postfach(s).download(date(2023, 7, 1), date(2023, 9, 30), 4, direkt=True)
    assert data.startswith(b"%PDF")
    assert len(s.posts) > 3                               # Liste neu geöffnet, dann erneut geklickt
