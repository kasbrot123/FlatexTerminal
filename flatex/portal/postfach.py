"""Postfach (Dokumentenarchiv) in flatex next: auflisten und PDFs laden.

Port von welworx/flatex-fetch internal/portal/next.go (MIT-Lizenz).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import parse_qs, unquote, urlparse

from flatex.portal.session import PortalError, Session, commands, describe, replace_portions_html

# Präfix des Postfach-Dialogs. flatex next vergibt ihn je nach Darstellung unterschiedlich
# (z. B. "fullScreenSecondLevelWidgetList[0]" oder "secondLevelWidgetList[0]") – er wird daher
# aus jeder Antwort gelesen, nicht fest verdrahtet. Standard laut flatex-fetch:
STANDARD_PRAEFIX = "fullScreenSecondLevelWidgetList[0]"
F_OPEN_ARCHIVE = "headerAreaWidget.settingsButtonWidget.btnOpenDocumentArchive.clicked"
F_OVERVIEW_IDX = "selectedViewWidget.overviewEntryBlockSelectionWidget.selecteditemindex"
F_DATE_START = "thirdLevelWidgetList[0].dtStartDate.text"
F_DATE_END = "thirdLevelWidgetList[0].dtEndDate.text"
F_DATE_APPLY = "thirdLevelWidgetList[0].btnApply.clicked"
IDX_CUSTOM = "6"

SCROLL_STEP = 5000
MAX_SCROLL_PAGES = 100

RE_PRAEFIX = re.compile(
    r'data-widgetname="([^".]+)\.secondLevelContentWidget\.(?:documentReadStatusSelectionWidget|'
    r'dateRangeSelectionWidget|btnReload|children\[\d+\]\.btnOpenDocument)')
# Ein Listeneintrag: Element mit data-widgetname "...children[N].btnOpenDocument" – Attributreihenfolge egal.
RE_ENTRY = (
    r'<[a-zA-Z]+\b(?=[^>]*\bdata-widgetname="[^"]*\.secondLevelContentWidget\.children\[(\d+)\]\.btnOpenDocument")'
    r'(?:[^>]*\bclass="([^"]*)")?[^>]*>'
)
RE_DATE_HEADER = r'<div class="DocumentDate CategoryLabel">\s*(?:<!--[^>]*-->)?\s*(\d{2}\.\d{2}\.\d{4})'
RE_ANY = re.compile(RE_DATE_HEADER + "|" + RE_ENTRY)
RE_KNOPF = re.compile(r'\.secondLevelContentWidget\.children\[(\d+)\]\.btnOpenDocument"')
LEER_HINWEIS = "Keine Einträge"
RE_DESCRIPTION = re.compile(r'<div class="Description">(?:<!--[^>]*-->)?([^<]*)')
RE_DOWNLOAD_URL = re.compile(r'DocumentViewer\.display\("([^"]+)"')


@dataclass
class Document:
    index: int
    datum: date | None
    name: str
    gelesen: bool


def _fmt(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def parse_entries(rows_html: str) -> list[Document]:
    docs: list[Document] = []
    current: date | None = None
    matches = list(RE_ANY.finditer(rows_html))
    for i, m in enumerate(matches):
        if m.group(1):
            try:
                current = datetime.strptime(m.group(1), "%d.%m.%Y").date()
            except ValueError:
                pass
            continue
        idx, cls = int(m.group(2)), m.group(3) or ""
        end = matches[i + 1].start() if i + 1 < len(matches) else len(rows_html)
        chunk = rows_html[m.end(): min(end, m.end() + 2000)]
        name = ""
        if dm := RE_DESCRIPTION.search(chunk):
            name = html.unescape(dm.group(1).strip())
        docs.append(Document(index=idx, datum=current, name=name, gelesen="Unread" not in cls))
    # Ein Eintrag kann mehrere Knöpfe mit demselben Index haben -> je Index nur einmal
    eindeutig: dict[int, Document] = {}
    for d in docs:
        eindeutig.setdefault(d.index, d)
    return list(eindeutig.values())


def knopf_anzahl(rows_html: str) -> int:
    """Wie viele verschiedene Dokumente die Antwort enthält – zur Kontrolle des Parsers."""
    return len(set(RE_KNOPF.findall(rows_html)))


class Postfach:
    def __init__(self, session: Session):
        self.s = session
        self.path = session.path("overviewFormAction.do")
        self.w = STANDARD_PRAEFIX
        self.warnungen: list[str] = []

    # Formularfelder mit dem aktuell erkannten Präfix
    def _f(self, rest: str) -> str:
        return f"{self.w}.{rest}"

    @property
    def f_readstate(self) -> str:
        return self._f("secondLevelContentWidget.documentReadStatusSelectionWidget.selecteditemindex")

    @property
    def f_daterange(self) -> str:
        return self._f("secondLevelContentWidget.dateRangeSelectionWidget.cbxDateRange.selecteditemindex")

    def _antwort(self, body: str) -> str:
        """HTML einer Antwort; merkt sich dabei den Präfix des Postfach-Dialogs."""
        h = replace_portions_html(body) or body
        if m := RE_PRAEFIX.search(h):
            if m.group(1) != self.w:
                self.s.log(f"  Postfach-Dialog heißt hier „{m.group(1)}“ – Felder angepasst")
                self.w = m.group(1)
        return h

    def _eintraege(self, h: str, von: date, bis: date) -> list[Document]:
        docs = parse_entries(h)
        knoepfe = knopf_anzahl(h)
        if knoepfe > len(docs):
            msg = (f"WARNUNG Postfach {von}..{bis}: {knoepfe} Dokumente in der Antwort, aber nur {len(docs)} "
                   "erkannt – bitte mit Debug-Modus erneut versuchen")
            self.warnungen.append(msg)
            self.s.log("  " + msg)
        return docs

    def _open_with_range(self, von: date, bis: date) -> list[Document]:
        self._antwort(self.s.post_form(self.path, {F_OVERVIEW_IDX: "0", F_OPEN_ARCHIVE: "true"},
                                       label="postfach_oeffnen"))
        self._antwort(self.s.post_form(self.path, {
            self.f_readstate: "0", self.f_daterange: "0",
            self._f("secondLevelContentWidget.dateRangeSelectionWidget.children[7].link.clicked"): "true",
        }, label="postfach_zeitraum_oeffnen"))
        body = self.s.post_form(
            self.path, {F_DATE_START: _fmt(von), F_DATE_END: _fmt(bis), F_DATE_APPLY: "true"},
            label=f"postfach_{von}_{bis}_liste",
        )
        if self.s.debug_dir:
            self.s.log(f"  Postfach {von}..{bis}: {describe(body)}")
        h = self._antwort(body)
        docs = self._eintraege(h, von, bis)
        if not docs and LEER_HINWEIS not in h and "btnOpenDocument" not in h:
            msg = (f"WARNUNG Postfach {von}..{bis}: weder Dokumente noch „keine Einträge“ in der Antwort – "
                   "Seitenaufbau unbekannt, bitte mit Debug-Modus erneut versuchen")
            self.warnungen.append(msg)
            self.s.log("  " + msg)
        return docs

    def _scroll_all(self, docs: list[Document], stop=None, von: date | None = None,
                    bis: date | None = None) -> list[Document]:
        if stop and stop(docs):
            return docs
        pos = SCROLL_STEP
        for _ in range(MAX_SCROLL_PAGES):
            body = self.s.post_form(self.path, {
                self._f("scrollposition"): str(pos), self.f_readstate: "0", self.f_daterange: IDX_CUSTOM,
                self._f("secondLevelContentWidget.btnReload.clicked"): "true",
            }, label="postfach_blaettern")
            nxt = self._eintraege(self._antwort(body), von or date.min, bis or date.min)
            if not nxt and docs:
                return docs
            if len(nxt) < len(docs):
                raise PortalError(
                    f"Postfach-Blättern lieferte weniger Einträge ({len(nxt)} < {len(docs)}) – "
                    "Antworten sind evtl. nicht kumulativ; Zeitraum verkleinern."
                )
            if len(nxt) == len(docs):
                return docs
            docs = nxt
            if stop and stop(docs):
                return docs
            pos += SCROLL_STEP
        raise PortalError("Postfach-Blättern endet nicht – Zeitraum verkleinern.")

    def list(self, von: date, bis: date) -> list[Document]:
        return self._scroll_all(self._open_with_range(von, bis), von=von, bis=bis)

    def _click(self, index: int) -> str | None:
        body = self.s.post_form(self.path, {
            self.f_readstate: "0", self.f_daterange: IDX_CUSTOM,
            self._f(f"secondLevelContentWidget.children[{index}].btnOpenDocument.clicked"): "true",
        }, label=f"postfach_dokument_{index}")
        self._antwort(body)
        for cmd in commands(body):
            if cmd.get("command") == "execute" and (m := RE_DOWNLOAD_URL.search(cmd.get("script", ""))):
                return m.group(1)
        return None

    def download(self, von: date, bis: date, index: int, direkt: bool = False) -> tuple[str, bytes]:
        """Lädt Dokument `index` aus genau dem Fenster [von, bis]. Gibt (Dateiname, Bytes) zurück.

        direkt=True: die Liste dieses Fensters ist gerade offen – Dokument direkt anklicken
        (2 Anfragen). Klappt das nicht (Zustand verloren), wird die Liste neu geöffnet.
        """
        loc = self._click(index) if direkt else None
        if not loc:
            docs = self._open_with_range(von, bis)
            self._scroll_all(docs, stop=lambda d: any(x.index == index for x in d), von=von, bis=bis)
            loc = self._click(index)
        if not loc:
            raise PortalError(f"Kein Download-Link für Dokument {index}")
        resp = self.s.plain_get(loc)
        content = resp.content
        if not content.startswith(b"%PDF"):
            raise PortalError(f"Antwort ist kein PDF ({resp.headers.get('content-type')})")
        return _filename(resp, loc), content


def _filename(resp, loc: str) -> str:
    cd = resp.headers.get("content-disposition", "")
    if m := re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd):
        name = unquote(m.group(1))
    else:
        q = parse_qs(urlparse(loc).query)
        name = (q.get("filename") or q.get("file") or [urlparse(loc).path.rsplit("/", 1)[-1]])[0]
    name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "dokument.pdf"
    return name if name.lower().endswith(".pdf") else name + ".pdf"
