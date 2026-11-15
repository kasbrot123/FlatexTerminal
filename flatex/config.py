"""Lädt config.toml aus dem Projektordner."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    domain: str
    depot_start: date
    request_delay: tuple[float, float]
    action_pause: tuple[float, float]
    max_actions_per_run: int
    closed_after_days: int
    suspect_min_rows: int
    edge_gap_days: int
    postfach_window_months: int
    postfach_overlap_days: int
    data_dir: Path
    pdf_cli: Path
    auswertung_von: date | None = None
    auswertung_bis: date | None = None
    burst_every: int = 60
    burst_pause: tuple[float, float] = (15.0, 30.0)
    block_monate: int = 12
    postfach_automatisch: bool = False
    securities: Path = ROOT / "securities.toml"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "flatex.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


def load(path: Path | None = None) -> Config:
    """Lädt die Konfiguration. Umgebungsvariablen (z. B. im Docker-Container) haben Vorrang:
    FLATEX_CONFIG (Pfad zur config.toml), FLATEX_DATA_DIR, FLATEX_PDF_CLI, FLATEX_SECURITIES,
    FLATEX_DEPOT_START."""
    if path is None:
        eigene = ROOT / "config.toml"            # persönlich, nicht im Repository
        path = Path(os.environ.get("FLATEX_CONFIG") or (eigene if eigene.exists() else ROOT / "config.example.toml"))
    with open(path, "rb") as f:
        c = tomllib.load(f)
    p, pace, s, paths = c["portal"], c["pacing"], c["sync"], c["paths"]

    def resolve(v: str) -> Path:
        q = Path(v)
        return q if q.is_absolute() else ROOT / q

    a = c.get("auswertung", {})

    def opt_date(v) -> date | None:
        return date.fromisoformat(str(v)) if v else None

    env = os.environ.get
    return Config(
        domain=p.get("domain", "flatex.at"),
        depot_start=date.fromisoformat(env("FLATEX_DEPOT_START") or str(p["depot_start"])),
        request_delay=tuple(pace["request_delay"]),
        action_pause=tuple(pace["action_pause"]),
        max_actions_per_run=int(pace["max_actions_per_run"]),
        closed_after_days=int(s["closed_after_days"]),
        suspect_min_rows=int(s["suspect_min_rows"]),
        edge_gap_days=int(s["edge_gap_days"]),
        postfach_window_months=int(s["postfach_window_months"]),
        postfach_overlap_days=int(s["postfach_overlap_days"]),
        data_dir=resolve(env("FLATEX_DATA_DIR") or paths["data"]),
        pdf_cli=resolve(env("FLATEX_PDF_CLI") or paths["pdf_cli"]),
        securities=resolve(env("FLATEX_SECURITIES") or paths.get("securities", "securities.toml")),
        auswertung_von=opt_date(a.get("von")),
        auswertung_bis=opt_date(a.get("bis")),
        burst_every=int(pace.get("burst_every", 60)),
        burst_pause=tuple(pace.get("burst_pause", (15.0, 30.0))),
        block_monate=int(s.get("block_monate", 12)),
        postfach_automatisch=bool(s.get("postfach_automatisch", False)),
    )
