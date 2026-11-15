# Flatex Terminal

**Analyze your flatex.at brokerage account locally:** fetch transactions and statements gently,
store them in a local database and explore them in a web app – net worth, performance, positions,
dividends and taxes.

> [!IMPORTANT]
> Unofficial hobby project for private use with your **own** account. Not affiliated with flatex or
> flatexDEGIRO. Not investment or tax advice – the documents issued by flatex are authoritative.
> All data stays on your machine.

> [!NOTE]
> **Previous version:** the [`legacy/`](legacy/) folder contains the original code of this
> repository. It is no longer developed and is kept for reference only – everything in this README
> refers to the new version in the root directory.

> The app's user interface is in **German** (built for an Austrian flatex account). UI labels are
> quoted in German below, with an English explanation.

---

## Contents

- [Features](#features)
- [Quick start with Docker](#quick-start-with-docker)
- [Running locally without Docker](#running-locally-without-docker)
- [First steps in the app](#first-steps-in-the-app)
- [Privacy and security](#privacy-and-security)
- [Being a good citizen towards flatex](#being-a-good-citizen-towards-flatex)
- [How it works](#how-it-works)
- [Command line](#command-line)
- [Configuration](#configuration)
- [Development](#development)
- [Limitations](#limitations)
- [Acknowledgements](#acknowledgements)

---

## Features

| Tab | What you get |
|---|---|
| **Übersicht** (overview) | Net worth, total gain, time-weighted return (TWR), internal rate of return (IRR); net worth vs. deposits vs. cash with zoom and buy/sell/dividend markers; allocation stocks/ETFs/derivatives as a donut; periods from 1 week to "since opening" |
| **Positionen** (positions) | Open and closed positions with value, cost basis, gain and number of transactions; detail view with price history and every booking |
| **Transaktionen** (transactions) | All movements with filters, search, sorting, totals and CSV export; timeline per security; click for details (execution price, market price that day, change since) |
| **Dividenden** (dividends) | Per month, quarter, year or cumulative; per security; calendar of received and expected payments |
| **Steuern** (taxes) | Austrian capital gains tax (KESt) per year with loss offsetting, sales, income and latent tax on open positions – exact with statement PDFs, otherwise estimated and clearly marked |
| **Dokumente** (documents) | View and download the original CSV exports and PDFs |
| **Daten** (fetch data) | One click in the app: new transactions, prices and optionally mailbox PDFs – with live log and cancel |

Light and dark mode, selectable colors per asset class, amounts always in euros with cents.

---

## Quick start with Docker

Requirement: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```powershell
git clone https://github.com/kasbrot123/FlatexTerminal.git
cd FlatexTerminal
docker compose up -d --build
```

Then open **http://localhost:8600** and follow the [first steps](#first-steps-in-the-app).

```powershell
docker compose logs -f     # show the log
docker compose down        # stop – your data stays in the "flatex-data" volume
```

- The web app is only reachable from this machine (`127.0.0.1:8600`).
- Credentials entered in the app are kept in memory only and last until the container restarts.
  For a permanent setup use Docker secrets – see `docker-compose.yml`.
- Import existing local data: `docker compose cp data/. flatex:/data/`

---

## Running locally without Docker

Requirements: **Python 3.12+** and **Node.js 20+** (for the frontend). Examples use Windows
PowerShell.

```powershell
git clone https://github.com/kasbrot123/FlatexTerminal.git
cd FlatexTerminal
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[web,dev]"
.\.venv\Scripts\python.exe -m flatex setup     # downloads the PDF parser (checksum verified), creates the database
.\.venv\Scripts\python.exe -m flatex web       # builds the frontend on first start and opens the browser
```

Credentials are stored locally in the **Windows Credential Manager** (via the app or
`python -m flatex login`).

Personal settings: copy `config.example.toml` to `config.toml` and adjust it (optional – without a
`config.toml` the template is used).

---

## First steps in the app

1. **Einstellungen** (settings, gear icon top right)
   - Set the **Depoteröffnung** (account opening date) – data is fetched from here, and "seit
     Eröffnung" (since opening) starts here.
   - Add your **own names and IBANs**. This is how deposits and withdrawals are detected: bookings
     whose *Empfänger* (recipient) or *Zahlungspfl.* (payer) matches. It is the basis for
     "Eingezahlt" (paid in), returns and IRR. After the first fetch the app suggests the
     counterparties found in your transactions.
2. **Daten** (top right) → store your login → **Jetzt abrufen** (fetch now).
   The first run loads the full history since opening in yearly blocks; after that only new data.
3. Optionally tick **Postfach-PDFs** (mailbox PDFs) if the tax tab should show exact values instead
   of estimates. The PDFs contain personal documents, so they are only fetched on request.

---

## Privacy and security

- **Everything stays local:** database, CSV exports and PDFs live in `data/` (or the Docker
  volume). The only outbound requests go to flatex (your login) and to Yahoo Finance (ISINs/tickers
  for prices and dividends only, no personal data).
- **Nothing personal in the repository:** `data/`, `config.toml`, `securities.toml`, `.env` and
  `secrets/` are excluded via `.gitignore` and `.dockerignore`.
- **Credentials** live only in the Windows Credential Manager, a Docker secret or in memory – never
  in project files.
- **The web app is for you only:** it listens on localhost, answers only requests addressed to
  `localhost` (protection against DNS rebinding) and accepts state-changing requests (fetch,
  settings, credentials) only from its own UI. Raw files can only be served from `data/raw/`.
- The Docker container runs as a non-root user with a read-only file system.
- **Debug mode** (`--debug`, or "Erweitert" → "Debug-Modus" in the app) saves flatex responses to
  `data/erkunden/` – they contain personal data; delete the folder afterwards.

---

## Being a good citizen towards flatex

**flatex offers no official API.** The tool therefore drives the regular web portal (flatex next)
the way a browser does – the same requests and form fields, just without a window. We do not want
to put load on flatex or cause any trouble, so:

- **Human pace, never parallel:** 0.6–1.4 s before each request, 1.5–3 s between two actions, a
  15–30 s break after every 60 actions. One login per run.
- **Nothing twice:** completed months are never requested again; only the current and the previous
  month are refreshed; known documents are skipped without a request.
- **Few requests:** transactions are fetched in yearly blocks instead of month by month; PDFs are
  downloaded straight from the open list (2 requests per document).
- **Emergency brake:** on HTTP 403/429/503, a bot check or repeated dropped connections the run
  stops immediately – no retrying. Everything fetched so far is kept.

The values live in `config.toml` under `[pacing]`. Please do not make them more aggressive.

---

## How it works

```
flatex.at (web portal) ──► fetch ──► data/raw/ (original CSV, PDFs) ──► SQLite (data/flatex.db)
Yahoo Finance ───────────► prices, dividend history ─────────────────────┘          │
                                                                                      ▼
                                          analysis (Python) ──► API (FastAPI) ──► web app (React)
```

- **Truncated lists:** flatex silently truncates long lists without saying by which rule. A one-time
  calibration compares the full period with the sum of the individual years, which proves either a
  row limit or that responses up to that size are complete. Suspicious exports are split in half
  until everything is complete.
- **Prices:** one Yahoo ticker per ISIN, preferably on a euro exchange, otherwise converted with the
  daily exchange rate. Every price is checked against the actual flatex execution prices; deviations
  above 10 % raise a warning (fix them in `securities.toml`). Without a Yahoo price (e.g. delisted)
  the last flatex trade price is used.
- **Cost basis:** what you actually paid including fees (moving average). The tax cost basis also
  includes deemed distributions of accumulating funds (ausschüttungsgleiche Erträge).
- **Returns:** TWR (time-weighted, independent of deposits/withdrawals) and IRR (money-weighted,
  annualized).
- **Taxes:** KESt 27.5 % (interest 25 %), loss offsetting within the calendar year, fees not
  deductible. Exact with statement PDFs (matched via transaction number, order number or
  ISIN + date + quantity), otherwise estimated from the account bookings.
- **Dividend forecast:** the last 12 months of distributions per share rolled forward and multiplied
  by the current holding – clearly marked as a forecast and checked against received payments.

---

## Command line

Everything the app does is also available in the terminal (`.\.venv\Scripts\python.exe -m flatex …`):

| Command | Purpose |
|---|---|
| `web` | start the web app (`--port`, `--build`, `--kein-browser` = don't open a browser) |
| `sync` | fetch transactions; `--nur postfach`, `--von`/`--bis`, `--postfach-neu`, `--geloeschte-neu-laden`, `--dry-run`, `--debug` |
| `kurse` | fetch and verify prices and dividend history (`--nur-pruefen` = verify only) |
| `status` | show what has been loaded |
| `login` | store credentials in the Windows Credential Manager |
| `setup` | install the PDF parser, create the database |
| `startdatum` | determine the account opening date from the mailbox |
| `import <folder>` | import manually exported CSV/XLSX files |
| `neu-einlesen` | re-read raw files (without contacting flatex) |
| `pdfs [folder]` | parse PDFs |
| `probe konto\|depot --von … --bis …` | single test export with debug output |

---

## Configuration

| File / variable | Purpose |
|---|---|
| `config.toml` | personal settings (template: `config.example.toml`) – not in the repository |
| `securities.toml` | ticker or asset-class overrides per ISIN (template: `securities.example.toml`) |
| Settings in the app | account opening date, own names/IBANs, colors (stored in the database) |
| `FLATEX_DEPOT_START` | default account opening date |
| `FLATEX_EIGENE_NAMEN` | default own names/IBANs (comma-separated) |
| `FLATEX_USER`, `FLATEX_PASSWORD` | credentials (or Docker secrets `flatex_user`/`flatex_password`) |
| `FLATEX_DATA_DIR`, `FLATEX_CONFIG`, `FLATEX_PDF_CLI` | paths (set inside the container) |

---

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest      # tests run fully offline, never contact flatex
cd web; npm run dev                       # frontend with hot reload (run the backend alongside: flatex web --kein-browser)
```

| Folder | Contents |
|---|---|
| `flatex/` | Python: fetching (`portal/`), parsing (`parse/`), analysis, taxes, dividends, prices, API |
| `web/` | frontend: React, TypeScript, Vite, Tailwind, Framer Motion, Recharts |
| `tests/` | tests with synthetic data (including a simulated flatex portal) |
| `legacy/` | previous version – no longer maintained |

---

## Limitations

- Tested with **flatex.at** and the **flatex next** interface. The classic interface and flatex.de
  are not supported.
- If flatex changes its web portal, fetching may break – the log then shows warnings.
- The PDF parser does not know every document type; unreadable statements remain estimated (the
  tax tab shows which ones).
- Foreign-currency dividends in the forecast use the latest exchange rate.

---

## Acknowledgements

- [welworx/flatex-fetch](https://github.com/welworx/flatex-fetch) (MIT) – login and mailbox access
  are a Python port of this project.
- [welworx/flatex-pdf-cli](https://github.com/welworx/flatex-pdf-cli) (MIT) – parses the statement
  PDFs; the test PDFs in `tests/fixtures/pdfs/` come from there and contain only synthetic data.
- Prices and dividend history via [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance).
