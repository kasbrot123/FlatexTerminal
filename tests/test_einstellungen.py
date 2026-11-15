"""Einstellungen (Web-App), Zeitraumprüfung für den Abruf und Rohdaten-Zugriff."""

import importlib
import warnings
from datetime import date

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

H = {"X-Flatex-Terminal": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FLATEX_DATA_DIR", str(tmp_path / "data"))
    from flatex import api

    api = importlib.reload(api)
    (tmp_path / "data" / "raw" / "konto").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "konto" / "2023-05.csv").write_text("Buchungstag;Betrag;\r\n03.05.2023;1,00;EUR\r\n")
    (tmp_path / "geheim.txt").write_text("nicht ausliefern")
    return TestClient(api.app), api


def test_einstellungen_speichern_und_wirken(client):
    c, api = client
    assert c.post("/api/einstellungen", json={"depot_start": "2023-05-01"}).status_code == 403   # ohne Header
    r = c.post("/api/einstellungen", headers=H,
               json={"depot_start": "2023-05-01", "eigene_namen": [" Max Muster ", ""], "farben": {"ETF": "s3", "Aktie": "x"}})
    assert r.status_code == 200
    e = r.json()
    assert e["eigene_namen"] == ["Max Muster"] and e["farben"] == {"ETF": "s3"}     # ungültige Farbe verworfen
    assert c.get("/api/meta").json()["depot_start"] == "2023-05-01"
    assert c.post("/api/einstellungen", headers=H, json={"depot_start": "31.12.2023"}).status_code == 400


def test_zeitraum_pruefen():
    from flatex.api import zeitraum_pruefen

    heute = date(2026, 11, 14)
    assert zeitraum_pruefen(None, None, date(2023, 5, 1), heute) == (date(2023, 5, 1), None)
    assert zeitraum_pruefen("2023-05-01", "2023-10-31", date(2020, 1, 1), heute)[1] == date(2023, 10, 31)
    for von, bis in (("2027-01-01", None), ("1999-12-31", None), ("2024-01-01", "2023-01-01"), ("01.05.2023", None)):
        with pytest.raises(HTTPException):
            zeitraum_pruefen(von, bis, date(2023, 5, 1), heute)


def test_rohdaten_nur_unter_raw(client):
    c, _ = client
    liste = c.get("/api/rohdaten").json()
    assert liste["csv"][0]["name"] == "2023-05.csv" and liste["csv"][0]["von"] == "2023-05-01"
    v = c.get("/api/rohdaten/vorschau", params={"pfad": "raw/konto/2023-05.csv"}).json()
    assert v["kopf"][:2] == ["Buchungstag", "Betrag"] and v["gesamt"] == 1
    assert c.get("/api/rohdaten/datei", params={"pfad": "raw/konto/2023-05.csv", "download": True}).status_code == 200
    for boese in ("../geheim.txt", "raw/../../geheim.txt", "flatex.db"):
        assert c.get("/api/rohdaten/datei", params={"pfad": boese}).status_code == 404
