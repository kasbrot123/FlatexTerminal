"""flatex-Zugangsdaten.

Reihenfolge:
1. Umgebungsvariablen FLATEX_USER / FLATEX_PASSWORD bzw. Docker-Secrets
   (/run/secrets/flatex_user, /run/secrets/flatex_password) – für den Container.
2. Systemschlüsselbund über keyring (unter Windows: Credential Manager).
3. Nur im Arbeitsspeicher (wenn es keinen Schlüsselbund gibt, z. B. im Container und über die
   Web-App eingegeben) – gilt bis zum Neustart, landet nie auf der Platte.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "flatex-terminal"
_USER_KEY = "__username__"
_SECRETS = Path(os.environ.get("FLATEX_SECRETS_DIR", "/run/secrets"))
_speicher: dict[str, str] = {}


def _aus_umgebung() -> tuple[str, str] | None:
    user, pw = os.environ.get("FLATEX_USER"), os.environ.get("FLATEX_PASSWORD")
    if not (user and pw):
        try:
            u, p = _SECRETS / "flatex_user", _SECRETS / "flatex_password"
            if u.is_file() and p.is_file():
                user, pw = u.read_text().strip(), p.read_text().strip()
        except OSError:
            pass
    return (user, pw) if user and pw else None


def _keyring_nutzbar() -> bool:
    try:
        return keyring.get_keyring().priority > 0
    except Exception:  # noqa: BLE001
        return False


def quelle() -> str:
    if _aus_umgebung():
        return "Umgebung/Docker-Secret"
    if _speicher:
        return "Arbeitsspeicher (bis zum Neustart)"
    return "Windows Credential Manager" if os.name == "nt" else "Schlüsselbund"


def store(user: str, pw: str) -> None:
    if not _keyring_nutzbar():
        _speicher.clear()
        _speicher.update(user=user, pw=pw)
        return
    try:
        alt = keyring.get_password(SERVICE, _USER_KEY)
        if alt and alt != user:
            try:
                keyring.delete_password(SERVICE, alt)
            except PasswordDeleteError:
                pass
        keyring.set_password(SERVICE, _USER_KEY, user)
        keyring.set_password(SERVICE, user, pw)
    except KeyringError:
        _speicher.clear()
        _speicher.update(user=user, pw=pw)


def store_interactive() -> None:
    user = input("flatex Kundennummer / Benutzer: ").strip()
    pw = getpass.getpass("Passwort (wird nicht angezeigt): ")
    store(user, pw)
    print(f"Gespeichert: {quelle()}.")


def _laden() -> tuple[str, str] | None:
    if env := _aus_umgebung():
        return env
    if _speicher:
        return _speicher["user"], _speicher["pw"]
    if not _keyring_nutzbar():
        return None
    try:
        user = keyring.get_password(SERVICE, _USER_KEY)
        pw = keyring.get_password(SERVICE, user) if user else None
    except KeyringError:
        return None
    return (user, pw) if user and pw else None


def vorhanden() -> bool:
    return _laden() is not None


def benutzer_maskiert() -> str | None:
    """Benutzername teilweise verdeckt, z. B. '12••••78' – für die Anzeige."""
    z = _laden()
    if not z:
        return None
    u = z[0]
    return u[:2] + "•" * max(len(u) - 4, 2) + u[-2:] if len(u) > 4 else "•" * len(u)


def load() -> tuple[str, str]:
    z = _laden()
    if not z:
        raise SystemExit("Keine Login-Daten gespeichert. Bitte zuerst: python -m flatex login")
    return z
