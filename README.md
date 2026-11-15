# Flatex Terminal

**Dein flatex.at-Depot lokal auswerten:** Umsätze und Abrechnungen schonend abrufen, in einer
lokalen Datenbank speichern und in einer Web-App ansehen – Vermögen, Performance, Positionen,
Dividenden und Steuern.

> [!IMPORTANT]
> Inoffizielles Hobbyprojekt für den privaten Gebrauch mit dem **eigenen** Konto. Keine Verbindung
> zu flatex bzw. flatexDEGIRO. Keine Anlage- oder Steuerberatung – maßgeblich sind die Dokumente von
> flatex. Alle Daten bleiben auf deinem Rechner.

> [!NOTE]
> **Frühere Version:** Im Ordner [`legacy/`](legacy/) liegt der ursprüngliche Code dieses
> Repositorys. Er wird nicht mehr weiterentwickelt und ist nur zur Nachvollziehbarkeit erhalten –
> alles in diesem README bezieht sich auf die neue Version im Hauptverzeichnis.

---

## Inhalt

- [Was es kann](#was-es-kann)
- [Schnellstart mit Docker](#schnellstart-mit-docker)
- [Lokal ohne Docker](#lokal-ohne-docker)
- [Erste Schritte in der App](#erste-schritte-in-der-app)
- [Datenschutz und Sicherheit](#datenschutz-und-sicherheit)
- [Umgang mit flatex](#umgang-mit-flatex)
- [Wie es funktioniert](#wie-es-funktioniert)
- [Kommandozeile](#kommandozeile)
- [Konfiguration](#konfiguration)
- [Entwicklung](#entwicklung)
- [Grenzen](#grenzen)
- [Danksagung](#danksagung)

---

## Was es kann

| Bereich | Inhalt |
|---|---|
| **Übersicht** | Gesamtvermögen, Gewinn, zeitgewichtete Rendite (TWR), Interner Zinsfuß (IZF); Vermögen vs. Einzahlungen vs. Cash mit Zoom, Käufe/Verkäufe/Dividenden als Markierungen; Aufteilung Aktien/ETF/Derivate als Ring; Zeitraum 1W … seit Eröffnung |
| **Positionen** | aktive und geschlossene Positionen mit Wert, Einstand, Gewinn, Anzahl Transaktionen; Detailansicht mit Kursverlauf und allen Buchungen |
| **Transaktionen** | alle Bewegungen mit Filter, Suche, Sortierung, Summen und CSV-Export; Zeitstrahl je Wertpapier; Klick öffnet Details (Ausführungskurs, Kurs am Tag, Entwicklung seitdem) |
| **Dividenden** | pro Monat, Quartal, Jahr oder kumuliert; nach Wertpapier; Kalender mit erhaltenen und erwarteten Zahlungen |
| **Steuern** | KESt je Jahr nach österreichischem Recht mit Verlustausgleich, Verkäufe, Erträge, latente Steuer offener Positionen – exakt mit Abrechnungs-PDFs, sonst geschätzt und gekennzeichnet |
| **Dokumente** | Original-CSV-Exporte und PDFs ansehen und herunterladen |
| **Daten abrufen** | per Knopf in der App: neue Umsätze, Kurse, optional Postfach-PDFs – mit Live-Protokoll und Abbrechen |

Hell- und Dunkelmodus, Farben der Wertpapierklassen wählbar, Beträge immer in Euro mit Cent.

---

## Schnellstart mit Docker

Voraussetzung: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```powershell
git clone <repo-url> flatex-terminal
cd flatex-terminal
docker compose up -d --build
```

Dann **http://localhost:8600** öffnen und den [ersten Schritten](#erste-schritte-in-der-app) folgen.

```powershell
docker compose logs -f     # Protokoll ansehen
docker compose down        # stoppen – die Daten bleiben im Volume "flatex-data"
```

- Die Web-App ist nur auf diesem Rechner erreichbar (`127.0.0.1:8600`).
- Zugangsdaten, die du in der App eingibst, gelten im Container bis zum Neustart (nur im
  Arbeitsspeicher). Dauerhaft geht es über Docker-Secrets – siehe `docker-compose.yml`.
- Vorhandene lokale Daten übernehmen: `docker compose cp data/. flatex:/data/`

---

## Lokal ohne Docker

Voraussetzungen: **Python 3.12+** und **Node.js 20+** (für das Frontend). Beispiele für Windows
PowerShell.

```powershell
git clone <repo-url> flatex-terminal
cd flatex-terminal
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[web,dev]"
.\.venv\Scripts\python.exe -m flatex setup     # lädt den PDF-Leser (mit Prüfsumme), legt die Datenbank an
.\.venv\Scripts\python.exe -m flatex web       # baut beim ersten Start das Frontend, öffnet den Browser
```

Zugangsdaten werden lokal im **Windows Credential Manager** gespeichert (über die App oder
`python -m flatex login`).

Eigene Einstellungen: `config.example.toml` nach `config.toml` kopieren und anpassen (optional –
ohne `config.toml` gilt die Vorlage).

---

## Erste Schritte in der App

1. **Einstellungen** (Zahnrad oben rechts)
   - **Depoteröffnung** eintragen – ab hier wird abgerufen, „Seit Eröffnung“ beginnt hier.
   - **Eigene Namen und IBANs** eintragen. Daran erkennt das Tool Ein- und Auszahlungen
     (Buchungen, deren *Empfänger* bzw. *Zahlungspfl.* passt). Das ist die Grundlage für
     „Eingezahlt“, Rendite und IZF. Nach dem ersten Abruf schlägt die App die Gegenkonten aus
     deinen Umsätzen zum Anhaken vor.
2. **Daten** (oben rechts) → Zugang hinterlegen → **Jetzt abrufen**.
   Der erste Abruf lädt die ganze Historie ab Eröffnung in Jahresblöcken, danach nur Neues.
3. Optional **Postfach-PDFs** anhaken, wenn der Steuer-Reiter exakte Werte statt Schätzungen
   zeigen soll (die PDFs enthalten persönliche Dokumente – daher nur auf Wunsch).

---

## Datenschutz und Sicherheit

- **Alles lokal:** Datenbank, CSV-Exporte und PDFs liegen in `data/` (bzw. im Docker-Volume).
  Nach außen gehen nur Anfragen an flatex (dein Login) und an Yahoo Finance (nur ISINs/Ticker für
  Kurse und Dividenden, keine persönlichen Daten).
- **Nichts Persönliches im Repository:** `data/`, `config.toml`, `securities.toml`, `.env` und
  `secrets/` sind in `.gitignore` und `.dockerignore` ausgeschlossen.
- **Zugangsdaten** nur im Windows Credential Manager, als Docker-Secret oder im Arbeitsspeicher –
  nie in Dateien des Projekts.
- **Web-App nur für dich:** lauscht auf localhost, beantwortet nur Anfragen an `localhost`
  (Schutz gegen DNS-Rebinding) und nimmt auslösende Anfragen (Abruf, Einstellungen, Zugang) nur
  von der eigenen Oberfläche an. Rohdateien sind nur aus `data/raw/` abrufbar.
- Der Docker-Container läuft ohne Root-Rechte mit schreibgeschütztem Dateisystem.
- **Debug-Modus** (`--debug` bzw. in der App unter „Erweitert“) speichert Antworten von flatex in
  `data/erkunden/` – sie enthalten persönliche Daten; den Ordner danach löschen.

---

## Umgang mit flatex

**flatex bietet keine offizielle Schnittstelle (API).** Das Tool bedient deshalb das normale
Webportal (flatex next) so, wie es ein Browser tut – dieselben Anfragen und Formularfelder, nur
ohne Fenster. Wir wollen flatex keine Last und keine Probleme bereiten, deshalb gilt:

- **Tempo eines zügigen Menschen, nie parallel:** 0,6–1,4 s vor jeder Anfrage, 1,5–3 s zwischen
  zwei Aktionen, nach je 60 Aktionen 15–30 s Pause. Ein Login pro Lauf.
- **Nichts doppelt:** abgeschlossene Monate werden nie wieder angefragt, nur der laufende und der
  Vormonat werden aufgefrischt; bekannte Dokumente werden ohne Anfrage übersprungen.
- **Wenige Anfragen:** Umsätze in Jahresblöcken statt Monat für Monat; PDFs direkt aus der offenen
  Liste (2 Anfragen je Dokument).
- **Notbremse:** bei HTTP 403/429/503, einer Bot-Prüfung oder wiederholten Verbindungsabbrüchen
  bricht der Lauf sofort ab – ohne erneutes Anklopfen. Bereits Geladenes bleibt erhalten.

Die Werte stehen in `config.toml` unter `[pacing]`. Bitte nicht aggressiver einstellen.

---

## Wie es funktioniert

```
flatex.at (Webportal) ──► Abruf ──► data/raw/ (Original-CSV, PDFs) ──► SQLite (data/flatex.db)
Yahoo Finance ──────────► Kurse, Dividendenhistorie ───────────────────┘          │
                                                                                    ▼
                                         Auswertung (Python) ──► API (FastAPI) ──► Web-App (React)
```

- **Abgeschnittene Listen:** flatex kürzt lange Listen, ohne zu sagen, nach welcher Regel. Eine
  einmalige Kalibrierung vergleicht den Gesamtzeitraum mit der Summe der Jahre und beweist so ein
  Limit – oder, dass Antworten bis zu dieser Größe vollständig sind. Verdächtige Exporte werden
  halbiert, bis alles vollständig ist.
- **Kurse:** je ISIN ein Yahoo-Ticker, bevorzugt an einer Euro-Börse, sonst mit Tageswechselkurs
  umgerechnet. Jeder Kurs wird gegen die echten flatex-Ausführungskurse geprüft; bei Abweichungen
  über 10 % gibt es eine Warnung (dann in `securities.toml` korrigieren). Ohne Yahoo-Kurs (z. B.
  delistet) gilt der letzte flatex-Handelskurs.
- **Einstand:** tatsächlich bezahlt inkl. Gebühren (gleitender Durchschnitt). Der steuerliche
  Einstand enthält zusätzlich ausschüttungsgleiche Erträge thesaurierender Fonds.
- **Rendite:** TWR (zeitgewichtet, unabhängig von Ein-/Auszahlungen) und IZF (geldgewichtet, p.a.).
- **Steuern:** KESt 27,5 % (Zinsen 25 %), Verlustausgleich im Kalenderjahr, Gebühren nicht
  absetzbar. Mit Abrechnungs-PDFs exakt (Zuordnung über TA.-Nr., Ordernummer oder
  ISIN + Datum + Stück), sonst aus den Kontobuchungen geschätzt.
- **Dividendenprognose:** Ausschüttungen der letzten 12 Monate je Stück fortgeschrieben, mal
  aktuelle Stückzahl – klar als Prognose markiert und gegen erhaltene Zahlungen abgeglichen.

---

## Kommandozeile

Alles, was die App kann, geht auch im Terminal (`.\.venv\Scripts\python.exe -m flatex …`):

| Befehl | Zweck |
|---|---|
| `web` | Web-App starten (`--port`, `--build`, `--kein-browser`) |
| `sync` | Umsätze abrufen; `--nur postfach`, `--von`/`--bis`, `--postfach-neu`, `--geloeschte-neu-laden`, `--dry-run`, `--debug` |
| `kurse` | Kurse und Dividendenhistorie laden und prüfen (`--nur-pruefen`) |
| `status` | Stand der Daten |
| `login` | Zugangsdaten im Windows Credential Manager speichern |
| `setup` | PDF-Leser installieren, Datenbank anlegen |
| `startdatum` | Depoteröffnung aus dem Postfach ermitteln |
| `import <ordner>` | manuell exportierte CSV/XLSX übernehmen |
| `neu-einlesen` | Rohdateien neu einlesen (ohne flatex) |
| `pdfs [ordner]` | PDFs auswerten |
| `probe konto\|depot --von … --bis …` | einzelner Test-Export mit Debug-Ablage |

---

## Konfiguration

| Datei / Variable | Zweck |
|---|---|
| `config.toml` | eigene Einstellungen (Vorlage: `config.example.toml`) – nicht im Repository |
| `securities.toml` | Ticker- bzw. Klassen-Korrekturen je ISIN (Vorlage: `securities.example.toml`) |
| Einstellungen in der App | Depoteröffnung, eigene Namen/IBANs, Farben (in der Datenbank gespeichert) |
| `FLATEX_DEPOT_START` | Vorgabe für die Depoteröffnung |
| `FLATEX_EIGENE_NAMEN` | Vorgabe für eigene Namen/IBANs (durch Komma getrennt) |
| `FLATEX_USER`, `FLATEX_PASSWORD` | Zugangsdaten (oder Docker-Secrets `flatex_user`/`flatex_password`) |
| `FLATEX_DATA_DIR`, `FLATEX_CONFIG`, `FLATEX_PDF_CLI` | Pfade (im Container gesetzt) |

---

## Entwicklung

```powershell
.\.venv\Scripts\python.exe -m pytest      # Tests – laufen komplett offline, ohne flatex
cd web; npm run dev                       # Frontend mit Hot-Reload (Backend parallel: flatex web --kein-browser)
```

| Ordner | Inhalt |
|---|---|
| `flatex/` | Python: Abruf (`portal/`), Einlesen (`parse/`), Auswertung, Steuern, Dividenden, Kurse, API |
| `web/` | Frontend: React, TypeScript, Vite, Tailwind, Framer Motion, Recharts |
| `tests/` | Tests mit synthetischen Daten (u. a. nachgebautes flatex-Portal) |
| `legacy/` | frühere Version – nicht mehr gepflegt |

---

## Grenzen

- Getestet mit **flatex.at** und der Oberfläche **flatex next**. Klassische Oberfläche und
  flatex.de sind nicht umgesetzt.
- Ändert flatex das Webportal, kann der Abruf brechen – das Protokoll zeigt dann Warnungen.
- Der PDF-Leser kennt nicht jede Dokumentart; nicht lesbare Abrechnungen bleiben geschätzt
  (der Steuer-Reiter zeigt, welche).
- Fremdwährungs-Dividenden in der Prognose zum letzten Wechselkurs.

---

## Danksagung

- [welworx/flatex-fetch](https://github.com/welworx/flatex-fetch) (MIT) – Login und Postfach sind
  ein Python-Port dieses Projekts.
- [welworx/flatex-pdf-cli](https://github.com/welworx/flatex-pdf-cli) (MIT) – liest die
  Abrechnungs-PDFs; die Test-PDFs in `tests/fixtures/pdfs/` stammen von dort und enthalten nur
  synthetische Daten.
- Kurse und Dividendenhistorie über [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance).
