from datetime import date, timedelta

import pytest

from flatex import db, sync
from flatex.config import load
from flatex.parse.umsaetze import Row
from flatex.portal.exports import ExportResult


def _rows(days: list[date]) -> list[Row]:
    rows = [Row(art="konto", buchtag=d, betrag_cent=100 * i, text=f"r{i}") for i, d in enumerate(days)]
    from flatex.parse.umsaetze import _assign_hashes

    _assign_hashes(rows)
    return rows


class FakePortal:
    """Simuliert ein Portal mit Item-Limit: liefert nur die neuesten `cap` Buchungen."""

    def __init__(self, bookings: list[date], cap: int):
        self.bookings, self.cap, self.calls = sorted(bookings), cap, []

    def __call__(self, von: date, bis: date) -> ExportResult:
        self.calls.append((von, bis))
        hits = [d for d in self.bookings if von <= d <= bis]
        hits = sorted(hits, reverse=True)[: self.cap]
        return ExportResult(rows=_rows(hits), raw=b"x", ext="csv")


def test_windows_months():
    w = list(sync.windows(date(2024, 11, 15), date(2025, 2, 10)))
    assert w == [
        (date(2024, 11, 1), date(2024, 11, 30)),
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 10)),
    ]


def test_start_for_months():
    today = date(2026, 11, 9)
    assert sync.start_for_months(today, 2, date(2023, 5, 1)) == date(2026, 10, 1)
    assert sync.start_for_months(date(2026, 1, 5), 3, date(2023, 5, 1)) == date(2025, 11, 1)
    assert sync.start_for_months(today, None, date(2023, 5, 1)) == date(2023, 5, 1)
    assert sync.start_for_months(today, 99, date(2023, 5, 1)) == date(2023, 5, 1)


def test_bloecke_nur_aufeinanderfolgende_monate():
    todo = [(date(2024, 5, 1), date(2024, 5, 31)), (date(2024, 3, 1), date(2024, 3, 31)),
            (date(2024, 2, 1), date(2024, 2, 29)), (date(2024, 1, 1), date(2024, 1, 31))]
    b = sync.bloecke(todo, 12)
    assert [len(x) for x in b] == [1, 3]                      # Mai allein (April fehlt), Jan–März zusammen
    assert [len(x) for x in sync.bloecke(todo, 2)] == [1, 1, 2]


def test_rohdatei_bereich():
    assert sync.rohdatei_bereich("2024-03") == (date(2024, 3, 1), date(2024, 3, 31))
    assert sync.rohdatei_bereich("2024-03_01-15") == (date(2024, 3, 1), date(2024, 3, 15))
    assert sync.rohdatei_bereich("2023-05-01_2024-04-30") == (date(2023, 5, 1), date(2024, 4, 30))
    assert sync.rohdatei_bereich("notizen") is None


@pytest.mark.parametrize("cap", [None, 40])
def test_erstdownload_in_bloecken(tmp_path, cap):
    cfg = load()
    object.__setattr__(cfg, "data_dir", tmp_path)
    object.__setattr__(cfg, "depot_start", date(2023, 5, 1))
    con = db.connect(cfg.db_path)
    today = date(2026, 6, 15)
    days = [date(2023, 5, 3) + timedelta(days=i * 4) for i in range(280)]   # ~ 3 Jahre, alle 4 Tage
    portal = FakePortal(days, cap=cap or 10_000)
    n = sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=lambda *a: None)
    assert n == 38                                            # Mai 2023 – Juni 2026
    got = sorted(r[0] for r in con.execute("SELECT buchtag FROM konto_umsaetze"))
    assert got == sorted(d.isoformat() for d in days if d <= today)
    if cap is None:
        assert len(portal.calls) <= 10                       # Kalibrierung (5) + 4 Jahresblöcke
    # zweiter Lauf: nur der offene Monat
    portal.calls.clear()
    sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=lambda *a: None)
    assert [c[0] for c in portal.calls] == [date(2026, 6, 1)]


def test_clamp_end():
    today = date(2026, 11, 9)
    assert sync.clamp_end(date(2023, 10, 15), today) == date(2023, 10, 31)
    assert sync.clamp_end(date(2026, 11, 1), today) is None
    assert sync.clamp_end(None, today) is None


def test_quarter_windows_aligned():
    w = list(sync.windows(date(2023, 5, 1), date(2023, 11, 9), 3))
    assert w[0] == (date(2023, 4, 1), date(2023, 6, 30))
    assert w[-1] == (date(2023, 10, 1), date(2023, 11, 9))


def test_test_run_then_full_run_recalibrates(tmp_path):
    cfg = load()
    object.__setattr__(cfg, "data_dir", tmp_path)
    object.__setattr__(cfg, "depot_start", date(2023, 5, 1))
    con = db.connect(cfg.db_path)
    today = date(2026, 11, 9)
    days = [date(2023, 5, 1) + timedelta(days=i * 3) for i in range(400)]
    portal = FakePortal(days, cap=50)
    log = lambda *a: None  # noqa: E731

    start = sync.start_for_months(today, 2, cfg.depot_start)
    assert sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log, start=start) == 2
    assert {c[0] for c in portal.calls} >= {date(2026, 10, 1), date(2026, 11, 1)}
    assert all(c[0] >= start for c in portal.calls)  # nichts vor dem Testzeitraum angefragt

    # Älteste 6 Monate (--bis 2023-10-15 → bis Monatsende Oktober): keine Anfrage außerhalb
    portal.calls.clear()
    n = sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log, ende=date(2023, 10, 15))
    assert n == 6
    assert portal.calls and all(date(2023, 5, 1) <= v and b <= date(2023, 10, 31) for v, b in portal.calls)
    # erneuter Lauf mit gleichem Zeitraum: nichts mehr zu tun, keine Neukalibrierung
    portal.calls.clear()
    assert sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log, ende=date(2023, 10, 31)) == 0
    assert portal.calls == []

    # Voller Lauf: kalibriert über die ganze Historie neu und findet das Limit
    sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log)
    assert 50 in json_caps(con)
    got = sorted(r[0] for r in con.execute("SELECT buchtag FROM konto_umsaetze"))
    assert got == sorted(d.isoformat() for d in days if d <= today)


def json_caps(con):
    import json

    return json.loads(db.meta_get(con, "caps_konto", "[]"))


def test_item_cap_detected_by_bisecting():
    # 2 Buchungen täglich im März -> 62 Zeilen, Portal liefert max 30
    days = [date(2024, 3, 1) + timedelta(days=i) for i in range(31) for _ in range(2)]
    portal = FakePortal(days, cap=30)
    chk = sync.Checks(suspect_min_rows=20, edge_gap_days=3, known_caps=set())
    pieces = sync.fetch_complete(portal, date(2024, 3, 1), date(2024, 3, 31), chk, log=lambda *a: None)
    assert sum(len(p.res.rows) for p in pieces) == 62
    assert 30 in chk.known_caps


def test_random_caps_never_lose_rows():
    import random

    rnd = random.Random(42)
    start, today = date(2022, 1, 1), date(2024, 12, 31)
    span = (today - start).days
    for trial in range(200):
        cap = rnd.choice([7, 17, 23, 30, 37, 50, 64, 100, 10_000])
        days = [start + timedelta(days=rnd.randint(0, span)) for _ in range(rnd.randint(0, 600))]
        # Hotspot-Monat mit vielen Buchungen
        days += [date(2024, 3, rnd.randint(1, 31)) for _ in range(rnd.randint(0, 150))]
        # pro Tag weniger als cap Buchungen, sonst ist es prinzipiell nicht lösbar
        days = [d for d in days if days.count(d) < cap]
        portal = FakePortal(days, cap=cap)
        chk = sync.Checks(known_caps=set())
        sync.calibrate(portal, start, today, chk, log=lambda *a: None)
        got = []
        for von, bis in sync.windows(start, today):
            pieces = sync.fetch_complete(portal, von, bis, chk, log=lambda *a: None)
            got += [r.buchtag for p in pieces for r in p.res.rows]
        assert sorted(got) == sorted(days), f"trial {trial}, cap {cap}"


def test_sparse_month_not_split():
    portal = FakePortal([date(2024, 3, 15)], cap=30)
    chk = sync.Checks(known_caps=set())
    pieces = sync.fetch_complete(portal, date(2024, 3, 1), date(2024, 3, 31), chk, log=lambda *a: None)
    assert len(pieces) == 1 and len(portal.calls) == 1


def test_false_alarm_keeps_whole_window():
    # 25 Buchungen nur in der Monatsmitte: verdächtig, aber nicht abgeschnitten
    days = [date(2024, 3, 10) + timedelta(days=i % 10) for i in range(25)]
    portal = FakePortal(days, cap=100)
    chk = sync.Checks(known_caps=set())
    pieces = sync.fetch_complete(portal, date(2024, 3, 1), date(2024, 3, 31), chk, log=lambda *a: None)
    assert len(pieces) == 1 and len(pieces[0].res.rows) == 25
    assert not chk.known_caps


def test_sync_is_incremental(tmp_path):
    cfg = load()
    object.__setattr__(cfg, "data_dir", tmp_path)
    object.__setattr__(cfg, "depot_start", date(2024, 1, 1))
    con = db.connect(cfg.db_path)
    days = [date(2024, 1, 5), date(2024, 2, 7), date(2024, 3, 20)]
    portal = FakePortal(days, cap=100)
    today = date(2024, 3, 25)
    log = lambda *a: None  # noqa: E731

    assert sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log) == 3
    assert con.execute("SELECT COUNT(*) FROM konto_umsaetze").fetchone()[0] == 3

    # Zweiter Lauf am selben Tag: Jan+Feb abgeschlossen (>10 Tage vorbei), nur März offen
    portal.calls.clear()
    sync.sync_umsaetze(con, cfg, "konto", portal, today=today, log=log)
    assert [c[0].month for c in portal.calls] == [3]
    assert con.execute("SELECT COUNT(*) FROM konto_umsaetze").fetchone()[0] == 3

    # Einen Monat später: Februar wird abgeschlossen, danach nie mehr geladen
    later = date(2024, 4, 15)
    sync.sync_umsaetze(con, cfg, "konto", portal, today=later, log=log)
    portal.calls.clear()
    sync.sync_umsaetze(con, cfg, "konto", portal, today=later, log=log)
    assert [c[0].month for c in portal.calls] == [4]
