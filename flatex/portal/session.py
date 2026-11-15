"""flatex.at Portal-Session ohne Browser.

Python-Port des Protokolls aus welworx/flatex-fetch (MIT-Lizenz,
internal/portal/portal.go + markup.go). Unterstützt wird die Oberfläche
"flatex next" (next-desktop.at).

Wichtig für die Schonung des Portals:
- vor jeder Anfrage eine kleine Zufallspause (Throttle.request)
- zwischen fachlichen Aktionen eine längere Pause (Throttle.action)
- bei Sperr-/Bot-Signalen sofort abbrechen, nie wiederholen
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

HOST_PREFIX = "konto."
LOGIN_PAGE_ACTION = "loginIFrameFormAction.do"
SSO_ACTION = "sso"
AJAX_COMMAND_ACTION = "ajaxCommandServlet"
NEXT_OVERVIEW_ACTION = "overviewFormAction.do"
LOGIN_PROGRESS_ACTION = "loginProgressFormAction.do"
CMD_ENGINE_STARTUP = "engineStartUp"
CMD_RESUME_LOGIN = "resumeLogin"

RE_TOKEN_ID = re.compile(r"""setTokenId\(\s*["']([A-Za-z0-9_-]+)["']""")


class PortalError(RuntimeError):
    pass


class PortalBlocked(PortalError):
    """Das Portal hat gedrosselt oder eine Bot-Prüfung gezeigt. Sofort aufhören."""


# Einzelne Verbindungsabbrüche (z. B. nach Pausen) werden einmal wiederholt; ab dem dritten im
# selben Lauf wird abgebrochen, weil das eher nach Drosselung aussieht.
MAX_VERBINDUNGSABBRUECHE = 2


@dataclass
class Throttle:
    """Tempo wie ein zügiger Mensch: kurze Pause vor jeder Anfrage, etwas längere zwischen
    Aktionen, und nach je `burst_every` Aktionen eine Verschnaufpause. Nie parallel."""
    request_delay: tuple[float, float] = (0.6, 1.4)
    action_pause: tuple[float, float] = (1.5, 3.0)
    max_actions: int = 500
    burst_every: int = 60
    burst_pause: tuple[float, float] = (15.0, 30.0)
    actions_done: int = 0
    requests_done: int = 0
    enabled: bool = True
    sleep: object = time.sleep   # austauschbar für Tests
    cancel: object = None        # threading.Event: gesetzt = Lauf sofort beenden
    on_change: object = None     # Callback(throttle) nach jeder Anfrage/Aktion (Fortschrittsanzeige)

    def _pause(self, sekunden: float) -> None:
        if self.cancel is not None:
            if self.cancel.wait(sekunden):   # wacht sofort auf, wenn abgebrochen wird
                raise SyncAbgebrochen()
        else:
            self.sleep(sekunden)

    def _check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise SyncAbgebrochen()

    def request(self) -> None:
        self._check()
        self.requests_done += 1
        if self.enabled:
            self._pause(random.uniform(*self.request_delay))
        if self.on_change:
            self.on_change(self)

    def action(self) -> None:
        """Vor jeder fachlichen Aktion aufrufen (Export, Liste, Download)."""
        self._check()
        if self.actions_done >= self.max_actions:
            raise ActionBudgetExhausted()
        if self.enabled and self.actions_done > 0:
            if self.burst_every and self.actions_done % self.burst_every == 0:
                self._pause(random.uniform(*self.burst_pause))
            else:
                self._pause(random.uniform(*self.action_pause))
        self.actions_done += 1
        if self.on_change:
            self.on_change(self)

    @property
    def budget_left(self) -> int:
        return self.max_actions - self.actions_done


class ActionBudgetExhausted(Exception):
    """Aktionslimit für diesen Lauf erreicht – beim nächsten Lauf geht es weiter."""


class SyncAbgebrochen(Exception):
    """Der Benutzer hat den Lauf abgebrochen."""


def _device_data() -> str:
    return json.dumps(
        {
            "windowWidth": 1470, "windowHeight": 801, "screenWidth": 1470, "screenHeight": 956,
            "userAgent": USER_AGENT, "browserName": "chrome", "browserVersion": "126.0.0.0",
            "platform": "Win32", "touchDevice": False, "pdfSupport": True,
            "time": int(time.time() * 1000),
        },
        separators=(",", ":"),
    )


def commands(body: str) -> list[dict]:
    try:
        return json.loads(body).get("commands", [])
    except (ValueError, AttributeError):
        return []


def replace_portions_html(body: str) -> str:
    """Alle HTML-Teile aus 'replacePortions'-Kommandos aneinandergehängt."""
    out = []
    for cmd in commands(body):
        if cmd.get("command") == "replacePortions":
            deltas = cmd.get("deltasToApply") or []
            out.extend(deltas[1::2])
    return "".join(out)


def full_page_replace_location(body: str) -> str | None:
    for cmd in commands(body):
        if cmd.get("command") == "fullPageReplace" and cmd.get("fetchLocation"):
            return cmd["fetchLocation"]
    return None


def describe(body: str) -> str:
    names = [c.get("command", "?") for c in commands(body)]
    return f"{len(names)} Kommando(s): {', '.join(names)}" if names else f"{len(body)} Bytes"


class Session:
    """Eine eingeloggte Portal-Session (nicht threadsicher)."""

    def __init__(self, domain: str = "flatex.at", throttle: Throttle | None = None, log=print,
                 debug_dir=None):
        if domain != "flatex.at":
            raise PortalError("Nur flatex.at (flatex next) ist umgesetzt.")
        self.base = f"https://{HOST_PREFIX}{domain}"
        self.next_segment = domain.replace("flatex", "next-desktop", 1)
        self.login_segment = "login.at"
        self.throttle = throttle or Throttle()
        self.log = log
        self.token_id = ""
        self.window_id = f"W{random.randint(100000, 999999)}"
        self.resyncs = 0                 # zählt fullPageReplace-Neustarts (Seitenzustand geht dabei verloren)
        self.last_page_html = ""         # zuletzt geladene Vollseite (für Widget-Suche)
        self.debug_dir = debug_dir       # wenn gesetzt: jede Antwort dort ablegen
        self._n = 0
        self.verbindungsabbrueche = 0
        self.http = self._neuer_client()

    # --- Grundbausteine -------------------------------------------------

    def _check_destination(self, request: httpx.Request) -> None:
        base = urlparse(self.base)
        if request.url.scheme != base.scheme or request.url.host != base.hostname:
            raise PortalError("Anfrage außerhalb des flatex-Portals blockiert")

    def path(self, action: str) -> str:
        return f"/{self.next_segment}/{action}"

    def _dump(self, label: str | None, method: str, resp: httpx.Response, form: dict | None) -> None:
        if not self.debug_dir:
            return
        self._n += 1
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label or resp.request.url.path.rsplit("/", 1)[-1])
        base = self.debug_dir / f"{self._n:03d}_{safe}"
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        fields = {k: ("<geschwärzt>" if k in ("userId", "password") else v) for k, v in (form or {}).items()}
        info = [f"{method} {resp.request.url.path}", f"HTTP {resp.status_code} {resp.headers.get('content-type')}",
                f"content-disposition: {resp.headers.get('content-disposition')}", "", *[f"{k} = {v}" for k, v in fields.items()]]
        base.with_suffix(".txt").write_text("\n".join(info), encoding="utf-8")
        body = resp.content
        if _is_text(resp):
            text = RE_TOKEN_ID.sub("setTokenId('<token>'", resp.text)
            try:  # replacePortions-HTML lesbar mit ablegen
                html = replace_portions_html(text)
            except Exception:
                html = ""
            base.with_suffix(".body").write_text(text, encoding="utf-8")
            if html:
                base.with_suffix(".html").write_text(html, encoding="utf-8")
        else:
            base.with_suffix(".bin").write_bytes(body)

    def _mit_neuverbindung(self, method: str, url: str, headers: dict, kw: dict) -> httpx.Response:
        """Trennt der Server eine (meist nach einer Pause stillgelegte) Verbindung, einmal kurz warten
        und über eine frische Verbindung wiederholen. Passiert das wiederholt, ist es eher Drosselung:
        dann abbrechen statt weiter anzuklopfen."""
        try:
            return self.http.request(method, url, headers=headers, **kw)
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.WriteError) as e:
            self.verbindungsabbrueche += 1
            if self.verbindungsabbrueche > MAX_VERBINDUNGSABBRUECHE:
                raise PortalBlocked(
                    f"flatex hat die Verbindung {self.verbindungsabbrueche}× getrennt – vermutlich Drosselung. "
                    "Abbruch; bitte später erneut versuchen (bereits Geladenes bleibt erhalten).") from e
            self.log(f"  Verbindung von flatex getrennt ({type(e).__name__}) – neuer Versuch in Kürze")
            cookies = self.http.cookies          # Anmeldung bleibt erhalten
            self.http.close()
            self.http = self._neuer_client(cookies=cookies)
            if self.throttle.enabled:
                self.throttle._pause(random.uniform(5.0, 10.0))
            try:
                return self.http.request(method, url, headers=headers, **kw)
            except httpx.TransportError as e2:
                raise PortalError(f"Keine Verbindung zu flatex ({type(e2).__name__}). Bitte später erneut versuchen.") from e2
        except httpx.TimeoutException as e:
            raise PortalError("flatex antwortet nicht (Zeitüberschreitung). Bitte später erneut versuchen.") from e

    _transport = None   # nur für Tests (httpx.MockTransport)

    def _neuer_client(self, cookies=None) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de-AT,de;q=0.9"},
            follow_redirects=True, timeout=60, cookies=cookies, transport=self._transport,
            event_hooks={"request": [self._check_destination]},
        )

    def _send(self, method: str, url: str, *, ajax: bool, label: str | None = None,
              form_log: dict | None = None, **kw) -> httpx.Response:
        self.throttle.request()
        headers = kw.pop("headers", {})
        if ajax:
            headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "X-AJAX": "true",
                "Accept": "application/json",
                "X-windowId": self.window_id,
            })
            if self.token_id:
                headers["X-tokenId"] = self.token_id
        resp = self._mit_neuverbindung(method, urljoin(self.base, url), headers, kw)
        self._dump(label, method, resp, form_log if form_log is not None else kw.get("data"))
        head = resp.content[:512].decode("latin-1").lower()
        if resp.status_code in (403, 429, 503) or "myracloud" in head:
            raise PortalBlocked(f"Portal blockiert ({resp.status_code}) – Abbruch, bitte später erneut.")
        if resp.status_code != 200:
            raise PortalError(f"{method} {resp.request.url.path}: HTTP {resp.status_code}")
        if m := RE_TOKEN_ID.search(resp.text if _is_text(resp) else ""):
            self.token_id = m.group(1)
        return resp

    def get_ajax(self, path: str, label: str | None = None) -> str:
        return self._send("GET", path, ajax=True, label=label).text

    def plain_get(self, location: str, label: str | None = None) -> httpx.Response:
        return self._send("GET", location, ajax=False, label=label)

    def post_ajax_command(self, command: str, extra: dict | None = None) -> str:
        data = {"command": command, **(extra or {})}
        return self._send("POST", self.path(AJAX_COMMAND_ACTION), ajax=True, data=data, label=command).text

    def post_form(self, path: str, form: dict[str, str], label: str | None = None) -> str:
        """Multipart-POST wie ajaxEngine.submitForm(); folgt einmal einem fullPageReplace."""
        body = self._post_form_once(path, form, label)
        if loc := full_page_replace_location(body):
            self._resync(loc)
            body = self._post_form_once(path, form, label)
            if full_page_replace_location(body):
                raise PortalError("Session wird vom Portal nicht mehr erkannt (fullPageReplace).")
        return body

    def _post_form_once(self, path: str, form: dict[str, str], label: str | None = None) -> str:
        files = [(k, (None, v)) for k, v in form.items()]
        return self._send("POST", path, ajax=True, files=files, label=label, form_log=form).text

    def _resync(self, location: str) -> None:
        wid = parse_qs(urlparse(location).query).get("windowId", [""])[0]
        if wid:
            self.window_id = wid
        page = self.plain_get(location, label="resync")
        self.last_page_html = page.text if _is_text(page) else ""
        self.resyncs += 1
        self.engine_startup()

    def engine_startup(self) -> None:
        self.post_ajax_command(
            CMD_ENGINE_STARTUP,
            {"windowIdPreviouslyUsed": self.window_id, "deviceData": _device_data()},
        )

    def get_ajax_following_replace(self, path: str) -> str:
        body = self.get_ajax(path)
        if loc := full_page_replace_location(body):
            self._resync(loc)
            body = self.get_ajax(path)
        return body

    # --- Login / Logout -------------------------------------------------

    def login(self, username: str, password: str) -> None:
        self.log("Login …")
        self.get_ajax(f"/{self.login_segment}/{LOGIN_PAGE_ACTION}")
        form = {
            "userId": username,
            "password": password,
            "deviceDetails": _device_data(),
            "windowWidth": "1470",
            "windowHeight": "956",
        }
        resp = self._send("POST", f"/{self.login_segment}/{SSO_ACTION}", ajax=False, data=form, label="login")
        self.last_page_html = resp.text if _is_text(resp) else ""
        if not self.http.cookies:
            raise PortalError("Login fehlgeschlagen: keine Session (Zugangsdaten falsch?)")
        if f"/{self.next_segment}/" not in resp.url.path:
            raise PortalError(
                "Login landete nicht in flatex next "
                f"({resp.url.path}). Klassische Oberfläche wird nicht unterstützt."
            )
        self.engine_startup()
        progress = self.get_ajax_following_replace(self.path(LOGIN_PROGRESS_ACTION))
        self.last_page_html += replace_portions_html(progress) or progress
        if not self.token_id:
            raise PortalError("Login fehlgeschlagen: kein tokenId erhalten")
        resumed = self.post_ajax_command(CMD_RESUME_LOGIN)
        self.last_page_html += replace_portions_html(resumed)
        self.log("Login ok.")

    def close(self) -> None:
        # Ein expliziter Logout-Endpunkt ist noch nicht bekannt (kommt aus der HAR-Aufzeichnung).
        self.http.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _is_text(resp: httpx.Response) -> bool:
    ct = resp.headers.get("content-type", "")
    return "text" in ct or "json" in ct or "javascript" in ct or not ct
