import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, CheckCircle2, CloudDownload, KeyRound, Loader2, ShieldCheck, Square, X, XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, SyncStatus } from "./api";
import { cx, datum } from "./lib";

/** Knopf in der Kopfzeile: zeigt den Zustand und öffnet das Daten-Panel. */
export function SyncButton({ status, onClick }: { status: SyncStatus | null; onClick: () => void }) {
  const laeuft = status?.laeuft;
  const fehler = status?.ergebnis && !["ok", "abgebrochen"].includes(status.ergebnis.status);
  return (
    <button onClick={onClick} aria-label="Daten abrufen"
      className="relative flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-sm text-ink2 transition hover:text-ink">
      {laeuft ? <Loader2 size={16} className="animate-spin text-accent" /> : <CloudDownload size={16} />}
      <span className="hidden sm:inline">{laeuft ? "Lädt …" : "Daten"}</span>
      {(laeuft || fehler) && (
        <span className={cx("absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-page",
          laeuft ? "bg-accent" : "bg-bad")} />
      )}
    </button>
  );
}

/** Hält den Sync-Status aktuell: schnell, solange ein Lauf aktiv ist, sonst gemächlich. */
export function useSyncStatus(onFertig: () => void) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const warLaufend = useRef(false);
  const laden = useCallback(async () => {
    try {
      const s = await api.syncStatus();
      setStatus(s);
      if (warLaufend.current && !s.laeuft) onFertig();
      warLaufend.current = s.laeuft;
    } catch { /* Backend kurz nicht erreichbar */ }
  }, [onFertig]);
  useEffect(() => {
    laden();
    const id = setInterval(laden, status?.laeuft ? 1000 : 15000);
    return () => clearInterval(id);
  }, [laden, status?.laeuft]);
  return { status, neuLaden: laden };
}

export function SyncPanel({ status, onClose, neuLaden }: {
  status: SyncStatus | null; onClose: () => void; neuLaden: () => void;
}) {
  const [kontoDepot, setKontoDepot] = useState(true);
  const [kurse, setKurse] = useState(true);
  const [postfach, setPostfach] = useState(false);
  const [postfachNeu, setPostfachNeu] = useState(false);
  const [debug, setDebug] = useState(false);
  const [modus, setModus] = useState<"alles" | "zeitraum">("alles");
  const [von, setVon] = useState(status?.depot_start ?? "");
  const [bis, setBis] = useState(status?.heute ?? "");
  const [fehler, setFehler] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); },
    [status?.log.length]);

  const starten = async () => {
    setFehler(null);
    try {
      const z = modus === "zeitraum";
      await api.syncStart({ konto_depot: kontoDepot, kurse, postfach, postfach_neu_pruefen: postfachNeu, debug,
        von: z && von ? von : null, bis: z && bis ? bis : null });
      neuLaden();
    } catch (e) { setFehler(String((e as Error).message)); }
  };
  const stoppen = async () => { try { await api.syncStop(); neuLaden(); } catch (e) { setFehler(String(e)); } };

  const laeuft = !!status?.laeuft;
  const erg = status?.ergebnis;

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.aside role="dialog" aria-modal="true" aria-label="Daten abrufen"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-line bg-page shadow-2xl"
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 36 }}>
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold">Daten abrufen</h2>
            <p className="text-sm text-muted">Neue Umsätze von flatex, Kurse von Yahoo Finance</p>
          </div>
          <button onClick={onClose} aria-label="Schließen"
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 hover:text-ink">
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {/* Stand */}
          <section className="grid grid-cols-2 gap-3 text-sm">
            <Stand label="Kontoumsätze" q={status?.quellen.konto} />
            <Stand label="Depotumsätze" q={status?.quellen.depot} />
            <div className="rounded-xl border border-line bg-surface p-3">
              <div className="text-ink2">Kurse</div>
              <div className="mt-0.5 font-medium">{status?.kurse_bis ? `bis ${datum(status.kurse_bis)}` : "–"}</div>
            </div>
            <Stand label="Postfach-PDFs" q={status?.quellen.postfach} />
          </section>

          {status && !status.zugangsdaten
            ? <Zugang onGespeichert={neuLaden} />
            : status && (
              <p className="flex items-center gap-2 text-[13px] text-ink2">
                <KeyRound size={14} className="text-muted" /> Zugang für {status.benutzer} · {status.zugang_quelle}
              </p>
            )}

          {/* Optionen */}
          <section className="space-y-2.5">
            <Option checked={kontoDepot} onChange={setKontoDepot} disabled={laeuft}
              titel="Konto- und Depotumsätze" text="Nur fehlende und noch offene Monate werden geladen." />
            <Option checked={kurse} onChange={setKurse} disabled={laeuft}
              titel="Kurse und Dividenden aktualisieren" text="Von Yahoo Finance, nur fehlende Tage." />
            <Option checked={postfach} onChange={setPostfach} disabled={laeuft}
              titel="Postfach-PDFs" text="Abrechnungen für exakte Steuerwerte – enthalten persönliche Daten."
              warnung={postfach} />
            {postfach && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="ml-7">
                <Option checked={postfachNeu} onChange={setPostfachNeu} disabled={laeuft}
                  titel="Postfach komplett neu prüfen"
                  text="Alle Zeiträume neu auflisten – geladen wird nur, was noch fehlt." />
              </motion.div>
            )}
            <details className="text-[13px] text-ink2">
              <summary className="cursor-pointer select-none">Erweitert</summary>
              <div className="mt-2">
                <Option checked={debug} onChange={setDebug} disabled={laeuft} titel="Debug-Modus"
                  text="Speichert die Antworten von flatex im Datenordner (erkunden/) zur Fehlersuche – enthalten persönliche Daten." />
              </div>
            </details>
            <div className="rounded-xl border border-line bg-surface p-3 text-sm">
              <div className="mb-2 font-medium">Zeitraum</div>
              <div className="space-y-2">
                <label className="flex items-center gap-2">
                  <input type="radio" checked={modus === "alles"} onChange={() => setModus("alles")} disabled={laeuft}
                    className="accent-[rgb(var(--s1))]" />
                  Seit Eröffnung ({status ? datum(status.depot_start) : "…"}) bis heute
                </label>
                <label className="flex flex-wrap items-center gap-2">
                  <input type="radio" checked={modus === "zeitraum"} onChange={() => setModus("zeitraum")} disabled={laeuft}
                    className="accent-[rgb(var(--s1))]" />
                  von
                  <input type="date" value={von} max={bis || status?.heute} onChange={(e) => { setVon(e.target.value); setModus("zeitraum"); }}
                    disabled={laeuft} className="rounded-lg border border-line bg-page px-2.5 py-1 text-ink outline-none focus:border-accent" />
                  bis
                  <input type="date" value={bis} min={von} max={status?.heute} onChange={(e) => { setBis(e.target.value); setModus("zeitraum"); }}
                    disabled={laeuft} className="rounded-lg border border-line bg-page px-2.5 py-1 text-ink outline-none focus:border-accent" />
                </label>
              </div>
              {modus === "zeitraum" && zeitraumFehler(von, bis, status?.heute) && (
                <p className="mt-2 text-bad">{zeitraumFehler(von, bis, status?.heute)}</p>
              )}
              <p className="mt-2 text-[12px] text-muted">Die Eröffnung stellst du in den Einstellungen (Zahnrad) ein.</p>
            </div>
          </section>

          <div className="flex items-center gap-3">
            {!laeuft ? (
              <motion.button whileTap={{ scale: 0.97 }} onClick={starten}
                disabled={(!status?.zugangsdaten && (kontoDepot || postfach)) ||
                  (modus === "zeitraum" && !!zeitraumFehler(von, bis, status?.heute))}
                className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-card transition hover:brightness-110 disabled:opacity-40">
                <CloudDownload size={17} /> Jetzt abrufen
              </motion.button>
            ) : (
              <motion.button whileTap={{ scale: 0.97 }} onClick={stoppen}
                className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-5 py-2.5 text-sm font-semibold text-ink">
                <Square size={15} /> Abbrechen
              </motion.button>
            )}
            {laeuft && (
              <span className="flex items-center gap-2 text-sm text-ink2">
                <Loader2 size={15} className="animate-spin text-accent" />
                {status?.schritt} · {status?.anfragen} Anfragen
              </span>
            )}
          </div>
          {fehler && <p className="text-sm text-bad">{fehler}</p>}

          <AnimatePresence>
            {erg && !laeuft && (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className={cx("flex gap-3 rounded-xl border p-3 text-sm",
                  erg.status === "ok" ? "border-line bg-surface" : "border-bad/40 bg-bad/5")}>
                {erg.status === "ok" ? <CheckCircle2 size={18} className="shrink-0 text-good" />
                  : erg.status === "abgebrochen" ? <XCircle size={18} className="shrink-0 text-muted" />
                    : <AlertTriangle size={18} className="shrink-0 text-bad" />}
                <div>
                  <div className="font-medium">{{
                    ok: "Abruf abgeschlossen", abgebrochen: "Abgebrochen", blockiert: "flatex hat gebremst – Abbruch",
                    fehler: "Fehler beim Abruf", keine_zugangsdaten: "Zugangsdaten fehlen",
                  }[erg.status]}</div>
                  <div className="text-ink2">{erg.nachricht}{erg.anfragen ? ` · ${erg.anfragen} Anfragen` : ""}</div>
                  {erg.status === "blockiert" && <div className="mt-1 text-ink2">Bitte später erneut versuchen.</div>}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Protokoll */}
          {!!status?.log.length && (
            <section>
              <div className="mb-1.5 text-[13px] font-medium text-ink2">Protokoll</div>
              <div ref={logRef}
                className="max-h-72 overflow-y-auto rounded-xl border border-line bg-surface p-3 font-mono text-[12px] leading-relaxed text-ink2">
                {status.log.map((z, i) => <div key={i} className="whitespace-pre-wrap">{z}</div>)}
              </div>
            </section>
          )}

          <p className="flex gap-2 text-[12px] leading-relaxed text-muted">
            <ShieldCheck size={14} className="mt-0.5 shrink-0" />
            flatex hat keine offizielle Schnittstelle. Der Abruf bedient das Webportal wie ein Browser – eine Anfrage
            nach der anderen, mit Pausen, ohne doppelte Downloads. Bei Sperrsignalen wird sofort abgebrochen.
          </p>
        </div>
      </motion.aside>
    </>
  );
}

/** Gleiche Prüfung wie im Backend – Fehler sofort zeigen statt erst bei flatex. */
function zeitraumFehler(von: string, bis: string, heute?: string): string | null {
  if (!von) return "Bitte ein „Von“-Datum wählen.";
  if (von < "2000-01-01") return "„Von“ vor 2000 nimmt flatex nicht an.";
  if (heute && von > heute) return "„Von“ liegt in der Zukunft.";
  if (bis && bis < von) return "„Bis“ liegt vor „Von“.";
  return null;
}

function Stand({ label, q }: { label: string; q?: { zuletzt: string; bis: string; von: string } }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="text-ink2">{label}</div>
      <div className="mt-0.5 font-medium">{q ? `${datum(q.von)} – ${datum(q.bis)}` : "noch nicht geladen"}</div>
      {q && <div className="text-xs text-muted">abgerufen {datum(q.zuletzt)} {q.zuletzt.slice(11, 16)}</div>}
    </div>
  );
}

function Option({ checked, onChange, titel, text, disabled, warnung }: {
  checked: boolean; onChange: (v: boolean) => void; titel: string; text: string; disabled?: boolean; warnung?: boolean;
}) {
  return (
    <label className={cx("flex cursor-pointer gap-3 rounded-xl border p-3 text-sm transition-colors",
      checked ? "border-accent/60 bg-accent/5" : "border-line bg-surface", disabled && "cursor-default opacity-60")}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled}
        className="mt-0.5 h-4 w-4 accent-[rgb(var(--s1))]" />
      <span>
        <span className="font-medium">{titel}</span>
        <span className={cx("block", warnung ? "text-bad" : "text-ink2")}>{text}</span>
      </span>
    </label>
  );
}

function Zugang({ onGespeichert }: { onGespeichert: () => void }) {
  const [benutzer, setBenutzer] = useState("");
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const speichern = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.zugangSpeichern(benutzer, passwort);
      setPasswort("");
      onGespeichert();
    } catch (err) { setFehler(String((err as Error).message)); }
  };
  return (
    <form onSubmit={speichern} className="space-y-2.5 rounded-xl border border-line bg-surface p-4 text-sm">
      <div className="flex items-center gap-2 font-medium"><KeyRound size={15} /> flatex-Zugang hinterlegen</div>
      <input value={benutzer} onChange={(e) => setBenutzer(e.target.value)} placeholder="Kundennummer / Benutzer"
        autoComplete="username" className="w-full rounded-lg border border-line bg-page px-3 py-2 outline-none focus:border-accent" />
      <input value={passwort} onChange={(e) => setPasswort(e.target.value)} placeholder="Passwort" type="password"
        autoComplete="current-password" className="w-full rounded-lg border border-line bg-page px-3 py-2 outline-none focus:border-accent" />
      <button disabled={!benutzer || !passwort}
        className="rounded-full bg-accent px-4 py-2 font-semibold text-white disabled:opacity-40">Speichern</button>
      {fehler && <p className="text-bad">{fehler}</p>}
      <p className="text-[12px] text-muted">Wird nur lokal gespeichert: unter Windows im Credential Manager, im
        Docker-Container nur im Arbeitsspeicher (bis zum Neustart).</p>
    </form>
  );
}
