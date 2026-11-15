"""Sync aus der Web-App: Schutz gegen fremde Aufrufer, Ablauf, Abbruch – ohne flatex-Kontakt."""

import threading
import time
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from flatex import api  # noqa: E402
from flatex.portal.session import SyncAbgebrochen, Throttle  # noqa: E402
from flatex.runner import Ergebnis  # noqa: E402

H = {"X-Flatex-Terminal": "1"}


@pytest.fixture
def client(monkeypatch):
    aufrufe = []
    freigabe = threading.Event()

    def fake_run_sync(cfg, quellen, start, ende, kurse_laden=False, log=print, cancel=None, fortschritt=None, **kw):
        aufrufe.append({"quellen": quellen, "ende": ende, "kurse": kurse_laden})
        log("Anmelden bei flatex …")
        while not freigabe.is_set():
            if cancel.wait(0.01):
                return Ergebnis("abgebrochen", "Vom Benutzer abgebrochen")
        return Ergebnis("ok", "Fertig.", 3, 9)

    monkeypatch.setattr("flatex.runner.run_sync", fake_run_sync)
    api._job.__init__()
    yield TestClient(api.app), aufrufe, freigabe
    freigabe.set()


def _warte(c, bis_fertig=True):
    for _ in range(300):
        s = c.get("/api/sync/status").json()
        if s["laeuft"] != bis_fertig:
            return s
        time.sleep(0.01)
    raise AssertionError("Zeitüberschreitung")


def test_ohne_header_oder_fremder_ursprung_verboten(client):
    c, aufrufe, _ = client
    assert c.post("/api/sync/start", json={}).status_code == 403
    assert c.post("/api/sync/start", json={}, headers={**H, "Origin": "https://boese.example"}).status_code == 403
    assert c.post("/api/credentials", json={"benutzer": "x", "passwort": "y"}).status_code == 403
    assert aufrufe == []


def test_fremder_host_wird_abgewiesen(client):
    c, _, _ = client
    assert c.get("/api/meta", headers={"Host": "evil.example"}).status_code == 403
    assert c.get("/api/sync/status", headers={"Host": "localhost:8600"}).status_code == 200


def test_start_status_und_nur_ein_lauf(client):
    c, aufrufe, freigabe = client
    r = c.post("/api/sync/start", json={"konto_depot": True, "kurse": True, "bis": "2023-10-15"}, headers=H)
    assert r.status_code == 200
    s = _warte(c, bis_fertig=False)
    assert s["laeuft"] and any("Anmelden" in z for z in s["log"])
    assert c.post("/api/sync/start", json={}, headers=H).status_code == 409   # zweiter Lauf abgelehnt
    freigabe.set()
    s = _warte(c)
    assert s["ergebnis"]["status"] == "ok"
    assert aufrufe[0]["quellen"] == ["konto", "depot"] and str(aufrufe[0]["ende"]) == "2023-10-31"


def test_postfach_nur_wenn_gewaehlt_und_abbruch(client):
    c, aufrufe, _ = client
    c.post("/api/sync/start", json={"konto_depot": False, "postfach": True, "kurse": False}, headers=H)
    _warte(c, bis_fertig=False)
    assert c.post("/api/sync/stop", headers=H).status_code == 200
    s = _warte(c)
    assert s["ergebnis"]["status"] == "abgebrochen"
    assert aufrufe[0]["quellen"] == ["postfach"]


def test_throttle_abbruch_weckt_aus_pause():
    ev = threading.Event()
    t = Throttle(action_pause=(30, 30), cancel=ev)
    t.action()                                 # erste Aktion ohne Pause
    threading.Timer(0.05, ev.set).start()
    start = time.monotonic()
    with pytest.raises(SyncAbgebrochen):
        t.action()                             # würde 30 s warten – bricht sofort ab
    assert time.monotonic() - start < 2
