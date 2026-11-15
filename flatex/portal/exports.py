"""Export von Konto- und Depotumsätzen (flatex next) für ein Datumsfenster.

Abfolge (aus den Bedienelementen der Umsatzseite abgeleitet):
  1. Kachel "Umsätze" öffnen         headerAreaWidget.headerAreaInfoButtons[N].linkOpenDetails
  2. Depot-/Kontoumsätze wählen       <P>.secondLevelContentWidget.categorySelectionWidget.items[0|1]
  3. Zeitraum "individuell" öffnen    <P>.secondLevelContentWidget.dateRangeSelectionWidget.children[7].link
  4. Von/Bis setzen + Übernehmen      thirdLevelWidgetList[0].dtStartDate/dtEndDate/btnApply
  5. "Export CSV" klicken             <P>.secondLevelContentWidget.btnDottedAction.children[1]
  6. Download-Link abrufen
<P> (z. B. "children[16]") wird bei jedem Lauf aus der Antwort gelesen, nicht fest verdrahtet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from flatex.parse.umsaetze import Row, parse_bytes
from flatex.portal.session import PortalError, Session, commands, describe, replace_portions_html

QUELLE_INDEX = {"depot": 0, "konto": 1}
IDX_CUSTOM_RANGE = "6"            # Eintrag "individuell" in der Zeitraum-Auswahl
CUSTOM_RANGE_CHILD = 7            # dateRangeSelectionWidget.children[7] = "individuell"
EXPORT_CSV_CHILD = 1              # btnDottedAction.children[1] = "Export CSV" ([0] = XLSX)

RE_HEADER_UMSAETZE = re.compile(
    r'class="[^"]*PostingsHeaderAreaInfoButton[^"]*" data-widgetname="(headerAreaWidget\.headerAreaInfoButtons\[\d+\]\.linkOpenDetails)"'
)
RE_HEADER_ANY = re.compile(r'data-widgetname="(headerAreaWidget\.headerAreaInfoButtons\[(\d+)\]\.linkOpenDetails)"')
RE_PREFIX = re.compile(r'data-widgetname="([^"]+?)\.secondLevelContentWidget\.categorySelectionWidget\.items\[\d+\]"')
RE_DOWNLOAD_URL = re.compile(r'(?:DocumentViewer\.display|window\.open|location\.href\s*=)\(?\s*"([^"]+)"')

# Fallback, falls die Kachel nicht in der Antwort gefunden wird (aus deiner HTML-Kopie).
DEFAULT_HEADER = "headerAreaWidget.headerAreaInfoButtons[3].linkOpenDetails"


@dataclass
class ExportResult:
    rows: list[Row]
    raw: bytes
    ext: str                      # "csv" oder "xlsx"
    truncated_hint: bool = False  # Portal hat selbst auf Kürzung hingewiesen
    notes: list[str] = field(default_factory=list)


TRUNCATION_HINTS = ("Es werden nur die ersten", "nur die ersten", "eingeschränkt")
EMPTY_HINT = "Keine Einträge im gewählten Zeitraum"


class UmsatzExporter:
    def __init__(self, session: Session):
        self.s = session
        self.path = session.path("overviewFormAction.do")
        self.prefix: str | None = None
        self.quelle: str | None = None
        self._resyncs_seen = -1

    # --- Navigation -----------------------------------------------------

    def _navigated(self, quelle: str) -> bool:
        return self.quelle == quelle and self.prefix is not None and self._resyncs_seen == self.s.resyncs

    def _open_umsaetze(self) -> str:
        page = self.s.last_page_html or ""
        m = RE_HEADER_UMSAETZE.search(page)
        header = m.group(1) if m else DEFAULT_HEADER
        body = self.s.post_form(self.path, {f"{header}.clicked": "true"}, label="umsaetze_oeffnen")
        html = replace_portions_html(body) or body
        pm = RE_PREFIX.search(html)
        if not pm:
            raise PortalError(
                f"Umsatzseite nicht erkannt ({describe(body)}). "
                "Mit --debug erneut starten und data/erkunden/ prüfen."
            )
        self.prefix = pm.group(1)
        self.s.log(f"  Umsatzseite offen (Widget-Präfix {self.prefix})")
        return html

    def _w(self, rest: str) -> str:
        return f"{self.prefix}.secondLevelContentWidget.{rest}"

    def _select_quelle(self, quelle: str) -> None:
        idx = QUELLE_INDEX[quelle]
        self.s.post_form(self.path, {
            self._w("categorySelectionWidget.selecteditemindex"): str(idx),
            self._w(f"categorySelectionWidget.items[{idx}].clicked"): "true",
        }, label=f"{quelle}_waehlen")

    def _ensure(self, quelle: str) -> None:
        if self._navigated(quelle):
            return
        if self.prefix is None or self._resyncs_seen != self.s.resyncs:
            self._open_umsaetze()
        self._select_quelle(quelle)
        self.quelle = quelle
        self._resyncs_seen = self.s.resyncs

    # --- Export ---------------------------------------------------------

    def export(self, quelle: str, von: date, bis: date) -> ExportResult:
        self._ensure(quelle)
        cbx = self._w("dateRangeSelectionWidget.cbxDateRange.selecteditemindex")
        self.s.post_form(self.path, {
            self._w(f"dateRangeSelectionWidget.children[{CUSTOM_RANGE_CHILD}].link.clicked"): "true",
            cbx: IDX_CUSTOM_RANGE,
        }, label=f"{quelle}_zeitraum_oeffnen")
        listing = self.s.post_form(self.path, {
            "thirdLevelWidgetList[0].dtStartDate.text": von.strftime("%d.%m.%Y"),
            "thirdLevelWidgetList[0].dtEndDate.text": bis.strftime("%d.%m.%Y"),
            "thirdLevelWidgetList[0].btnApply.clicked": "true",
        }, label=f"{quelle}_{von}_{bis}_liste")
        listing_html = replace_portions_html(listing) + listing
        hint = any(h in listing_html for h in TRUNCATION_HINTS)
        if EMPTY_HINT in listing_html:
            # flatex liefert bei leerer Liste keine Exportdatei – das ist kein Fehler.
            self.s.log(f"  {quelle} {von}..{bis}: keine Einträge")
            return ExportResult(rows=[], raw=b"", ext="csv", notes=["leer"])

        body = self.s.post_form(self.path, {
            cbx: IDX_CUSTOM_RANGE,
            self._w(f"btnDottedAction.children[{EXPORT_CSV_CHILD}].clicked"): "true",
        }, label=f"{quelle}_{von}_{bis}_export")
        raw, ext = self._fetch_export(body)
        rows = parse_bytes(raw, ext, quelle)
        return ExportResult(rows=rows, raw=raw, ext=ext, truncated_hint=hint)

    def _fetch_export(self, body: str) -> tuple[bytes, str]:
        loc = None
        for cmd in commands(body):
            name = cmd.get("command")
            if name == "download" and cmd.get("location"):
                loc = cmd["location"]
            elif name == "execute" and (m := RE_DOWNLOAD_URL.search(cmd.get("script", ""))):
                loc = m.group(1)
            if loc:
                break
        if not loc:
            raise PortalError(f"Kein Export-Download in der Antwort ({describe(body)}). Mit --debug prüfen.")
        resp = self.s.plain_get(loc, label="export_datei")
        content = resp.content
        cd = resp.headers.get("content-disposition", "").lower()
        if content[:2] == b"PK" or ".xlsx" in cd:
            return content, "xlsx"
        if content.lstrip()[:1] in (b"<",):
            raise PortalError("Export lieferte HTML statt einer Datei – mit --debug prüfen.")
        return content, "csv"
