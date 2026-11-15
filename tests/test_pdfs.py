"""PDF-Import über flatex-pdf-cli. Die Beispiel-PDFs stammen aus welworx/flatex-pdf-cli (synthetische Daten)."""

import shutil
from pathlib import Path

import pytest

from flatex import db, pdfs
from flatex.config import load

FIX = Path(__file__).parent / "fixtures" / "pdfs"
cfg0 = load()
pytestmark = pytest.mark.skipif(not cfg0.pdf_cli.exists(), reason="flatex-pdf-cli nicht installiert (flatex setup)")


def test_ingest_samples(tmp_path):
    cfg = load()
    object.__setattr__(cfg, "data_dir", tmp_path)
    con = db.connect(cfg.db_path)
    target = tmp_path / "raw" / "pdfs"
    shutil.copytree(FIX, target)
    for f in sorted(target.glob("*.pdf")):
        con.execute("INSERT INTO dokumente(datum, name, nr, pfad) VALUES ('2025-01-01', ?, 1, ?)",
                    (f.name, str(f.relative_to(tmp_path))))
    total = pdfs.ingest_pending(con, cfg, log=lambda *a: None)
    assert total > 0
    types = {r[0] for r in con.execute("SELECT DISTINCT document_type FROM pdf_transaktionen")}
    assert {"TRADE", "DIVIDEND"} <= types
    assert con.execute("SELECT COUNT(*) FROM dokumente WHERE geparst = 0").fetchone()[0] == 0
    # erneutes Auswerten erzeugt keine Duplikate
    n = con.execute("SELECT COUNT(*) FROM pdf_transaktionen").fetchone()[0]
    pdfs.ingest_pdf(con, cfg, target / "trade_sample_1.pdf")
    assert con.execute("SELECT COUNT(*) FROM pdf_transaktionen").fetchone()[0] == n
    # vom Nutzer gelöschtes PDF: Daten verschwinden, Dokument bleibt als "geladen" vermerkt
    rel = str((target / "trade_sample_1.pdf").relative_to(tmp_path))
    assert con.execute("SELECT COUNT(*) FROM pdf_transaktionen WHERE pfad=?", (rel,)).fetchone()[0] > 0
    (target / "trade_sample_1.pdf").unlink()
    pdfs.ingest_pending(con, cfg, log=lambda *a: None)
    assert con.execute("SELECT COUNT(*) FROM pdf_transaktionen WHERE pfad=?", (rel,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM dokumente WHERE pfad=?", (rel,)).fetchone()[0] == 1
