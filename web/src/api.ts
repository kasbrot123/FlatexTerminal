// Typen und Abrufe für die lokale Python-API (/api/...)

export type Typ = "Aktie" | "ETF" | "Derivat" | "Sonstige";

export interface Meta {
  depot_start: string; bis_default: string; daten_bis: string; kurse_bis: string | null; heute: string;
  hat_daten: boolean;
  sync: Record<string, { fenster: number; zuletzt: string }>;
}

export interface SeriePunkt {
  d: string; vermoegen: number; eingezahlt: number; depotwert: number; cash: number; gewinn: number; rendite: number;
}

export interface Overview {
  von: string; bis: string;
  kpi: {
    vermoegen: number; cash: number; depotwert: number; nach_typ: Record<Typ, number>;
    eingezahlt: number; gewinn_gesamt: number; einstand: number; unrealisiert: number;
    gewinn_zeitraum: number; rendite_zeitraum: number; xirr: number | null; izf_gesamt: number | null; realisiert: number;
    dividenden: number; zinsen: number; gebuehren: number; abzuege_verkauf: number; steuer_thesaurierung: number;
    kaeufe: number; verkaeufe: number; positionen: number;
  };
  serie: SeriePunkt[];
  aufteilung: { typ: Typ; wert: number; anteil: number }[];
  positionen: { isin: string; name: string; typ: Typ; wert: number; anteil: number }[];
  ersatzkurse: string[];
}

export interface AktivePosition {
  isin: string; name: string; typ: Typ; stueck: number; kurs: number | null; durchschnitt: number;
  einstand: number; einstand_steuer: number; wert: number; gewinn: number; gewinn_pct: number;
  anteil: number; ersatzkurs: boolean; spark: number[];
  kaeufe: number; verkaeufe: number; ertraege: number; transaktionen: number;
}
export interface GeschlossenePosition {
  isin: string; name: string; typ: Typ; gekauft: number; verkauft: number; ergebnis: number;
  ergebnis_pct: number | null; letzte: string;
  kaeufe: number; verkaeufe: number; ertraege: number; transaktionen: number;
}

export interface Einstellungen {
  depot_start: string | null; depot_start_wirksam: string; depot_start_config: string;
  eigene_namen: string[]; farben: Partial<Record<Typ, string>>;
  gegenkonten: { gegenkonto: string; anzahl: number; summe: number; erkannt: boolean }[];
}
export interface Rohdaten {
  csv: { quelle: string; pfad: string; name: string; groesse: number; von: string | null; bis: string | null }[];
  pdf: { datum: string; name: string; pfad: string; groesse: number; geladen: string | null }[];
}
export interface Positions { bis: string; aktiv: AktivePosition[]; geschlossen: GeschlossenePosition[] }

export interface PositionDetail {
  isin: string; name: string; typ: Typ; ticker: string | null; waehrung: string | null;
  kurs_abweichung: number | null; ersatzkurs: boolean;
  summe: {
    stueck: number; einstand: number; marktwert: number; unrealisiert: number; kurs: number | null;
    kaeufe: number; verkaeufe: number; gekauft_eur: number; verkauft_eur: number; gebuehren: number;
    realisiert: number; ertraege: number; steuer_thesaurierung: number; ergebnis: number; ergebnis_pct: number | null;
  };
  verlauf: { d: string; kurs: number | null; wert: number; investiert: number; stueck: number }[];
  buchungen: { d: string; art: string; stueck: number; kurs: number | null; kurswert: number; konto: number | null;
    gebuehr: number | null; abzuege_verkauf: number | null }[];
  ertraege: { d: string; kategorie: string; betrag: number; text: string }[];
}

export interface Transaktion {
  id: string; d: string; valuta: string | null; kategorie: string; isin: string | null; name: string | null;
  typ: Typ | null; stueck: number | null; kurs: number | null; betrag: number | null; gebuehr: number | null;
  text: string; geldfluss: boolean;
}

export interface KalenderEintrag {
  d: string; ex?: string; isin: string; name: string | null; netto: number; brutto: number;
  stueck?: number; je_stueck?: number; status: "erhalten" | "erwartet"; quelle?: string;
}
export interface Dividends {
  bis: string;
  kpi: { gesamt: number; anzahl: number; ttm: number; rendite_ttm: number | null; erwartet_brutto: number;
    erwartet_netto: number; rendite_erwartet: number | null; abgleich_abweichung: number | null; abgleich_anzahl: number };
  pro_monat: { m: string; netto: number }[];
  pro_jahr: { jahr: number; netto: number }[];
  pro_titel: { isin: string; name: string | null; netto: number; anzahl: number }[];
  kalender: KalenderEintrag[];
}

export interface SteuerJahr {
  jahr: number; gewinne: number; verluste: number; dividenden: number; age: number; zinsen: number;
  bemessung: number; kest_soll: number; kest_bezahlt: number; davon_geschaetzt: number; quellensteuer: number;
  abzuege_verkauf_unbekannt: number; hinweise: string[];
}
export interface PdfStatus {
  dokumente: number; gelesen: number; transaktionen: Record<string, number>;
  nicht_lesbar: { name: string; anzahl: number }[];
  verkaeufe: number; verkaeufe_mit_pdf: number; ertraege: number; ertraege_mit_pdf: number;
}
export interface Taxes {
  bis: string; satz: number; pdf_anzahl: number; pdf_status: PdfStatus; jahre: SteuerJahr[];
  verkaeufe: { d: string; isin: string; name: string; stueck: number; kurswert: number; anschaffung: number;
    gewinn: number; abzuege: number | null; kest_bezahlt: number | null; kest_geschaetzt: number | null;
    gebuehren: number | null; quelle: string }[];
  ertraege: { d: string; art: string; isin: string | null; name: string | null; brutto: number; steuer: number;
    quellensteuer: number | null; netto: number; quelle: string }[];
  offen: { isin: string; name: string; stueck: number; anschaffung: number; wert: number | null;
    gewinn: number | null; kest_latent: number | null }[];
  kest_latent: number; verlust_offen: number;
}

export interface SyncStatus {
  laeuft: boolean; gestartet: string | null; beendet: string | null;
  optionen: { konto_depot?: boolean; kurse?: boolean; postfach?: boolean; bis?: string | null };
  schritt: string | null; aktionen: number; anfragen: number; log: string[];
  ergebnis: { status: "ok" | "blockiert" | "fehler" | "abgebrochen" | "keine_zugangsdaten"; nachricht: string;
    aktionen: number; anfragen: number } | null;
  quellen: Record<string, { fenster: number; zuletzt: string; von: string; bis: string }>;
  kurse_bis: string | null; zugangsdaten: boolean; benutzer: string | null; zugang_quelle: string; depot_start: string;
  heute: string;
  postfach_automatisch: boolean;
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    // eigener Header: das Backend nimmt auslösende Anfragen nur aus dieser Oberfläche an
    headers: { "Content-Type": "application/json", "X-Flatex-Terminal": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* kein JSON */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} – ${url}`);
  return r.json() as Promise<T>;
}

const q = (p: Record<string, string | undefined>) =>
  "?" + Object.entries(p).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`).join("&");

export const api = {
  meta: () => get<Meta>("/api/meta"),
  overview: (von?: string, bis?: string) => get<Overview>("/api/overview" + q({ von, bis })),
  positions: (bis?: string) => get<Positions>("/api/positions" + q({ bis })),
  position: (isin: string, bis?: string) => get<PositionDetail>(`/api/positions/${isin}` + q({ bis })),
  transactions: (bis?: string) => get<{ bis: string; transaktionen: Transaktion[] }>("/api/transactions" + q({ bis })),
  dividends: (bis?: string) => get<Dividends>("/api/dividends" + q({ bis })),
  taxes: (bis?: string) => get<Taxes>("/api/taxes" + q({ bis })),
  syncStatus: () => get<SyncStatus>("/api/sync/status"),
  syncStart: (o: { konto_depot: boolean; kurse: boolean; postfach: boolean; postfach_neu_pruefen: boolean; debug: boolean;
    von: string | null; bis: string | null }) =>
    post<{ gestartet: boolean }>("/api/sync/start", o),
  syncStop: () => post<{ laeuft: boolean }>("/api/sync/stop"),
  zugangSpeichern: (benutzer: string, passwort: string) =>
    post<{ gespeichert: boolean; benutzer: string }>("/api/credentials", { benutzer, passwort }),
  einstellungen: () => get<Einstellungen>("/api/einstellungen"),
  einstellungenSpeichern: (e: { depot_start: string | null; eigene_namen: string[]; farben: Record<string, string> }) =>
    post<Einstellungen>("/api/einstellungen", e),
  rohdaten: () => get<Rohdaten>("/api/rohdaten"),
  rohVorschau: (pfad: string) =>
    get<{ kopf: string[]; zeilen: string[][]; hinweis: string | null; gesamt?: number }>("/api/rohdaten/vorschau" + q({ pfad })),
};

export const rohUrl = (pfad: string, download = false) =>
  `/api/rohdaten/datei?pfad=${encodeURIComponent(pfad)}${download ? "&download=true" : ""}`;
