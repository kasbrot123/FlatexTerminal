"""Frischer Start ohne Daten (z. B. neuer Docker-Container): kein Endpunkt darf abstürzen."""

import importlib
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

ENDPUNKTE = ["/api/meta", "/api/overview", "/api/positions", "/api/transactions", "/api/dividends",
             "/api/taxes", "/api/sync/status"]


@pytest.fixture
def leer(tmp_path, monkeypatch):
    monkeypatch.setenv("FLATEX_DATA_DIR", str(tmp_path / "data"))
    from flatex import api

    api = importlib.reload(api)
    yield TestClient(api.app)


@pytest.mark.parametrize("url", ENDPUNKTE)
def test_leere_datenbank(leer, url):
    r = leer.get(url)
    assert r.status_code == 200, r.text[:500]
