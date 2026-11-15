# Flatex Terminal – Web-App im Container. Enthält KEINE persönlichen Daten:
# Datenbank, Rohdateien und Zugangsdaten liegen außerhalb (Volume /data, Umgebung/Secrets).

# --- 1) Frontend bauen -----------------------------------------------------------------------
FROM node:20.18-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- 2) flatex-pdf-cli (Linux) mit Prüfsumme laden ------------------------------------------
FROM debian:bookworm-slim AS pdfcli
ARG PDF_CLI_VERSION=v0.8.2
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /dl
RUN set -eux; \
    base="https://github.com/welworx/flatex-pdf-cli/releases/download/${PDF_CLI_VERSION}"; \
    asset="flatex-pdf-cli_linux_${TARGETARCH}"; \
    curl -fsSLO "${base}/${asset}"; curl -fsSLO "${base}/SHA256SUMS.txt"; \
    grep " ${asset}\$" SHA256SUMS.txt | sha256sum -c -; \
    install -m 0755 "${asset}" /usr/local/bin/flatex-pdf-cli

# --- 3) Laufzeit -----------------------------------------------------------------------------
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FLATEX_CONFIG=/app/config.toml \
    FLATEX_DATA_DIR=/data \
    FLATEX_PDF_CLI=/usr/local/bin/flatex-pdf-cli \
    FLATEX_SECURITIES=/app/securities.toml
WORKDIR /app

COPY pyproject.toml ./
COPY flatex/ ./flatex/
RUN pip install -e ".[web]"

COPY --from=pdfcli /usr/local/bin/flatex-pdf-cli /usr/local/bin/flatex-pdf-cli
COPY --from=web /web/dist ./web/dist
# neutrale Vorlagen; eigene Dateien per Volume darüberlegen (siehe docker-compose.yml)
COPY config.example.toml ./config.toml
COPY securities.example.toml ./securities.toml

RUN useradd --create-home --uid 10001 flatex && mkdir -p /data && chown flatex:flatex /data
USER flatex
VOLUME ["/data"]
EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8600/api/meta', timeout=4)" || exit 1

# Im Container auf allen Schnittstellen lauschen; nach außen nur über 127.0.0.1 freigeben.
CMD ["python", "-m", "flatex", "web", "--host", "0.0.0.0", "--port", "8600", "--kein-browser"]
