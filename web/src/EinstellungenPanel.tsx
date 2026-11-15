import { motion } from "framer-motion";
import { Check, Palette, Plus, Save, Settings2, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, Einstellungen, Typ } from "./api";
import { Colors, cx, datum, eurSigned, setFarbWahl, Slot, SLOTS, STANDARD_FARBEN } from "./lib";

const TYPEN: Typ[] = ["Aktie", "ETF", "Derivat", "Sonstige"];
// Paare aus der Palette, die nebeneinander schwer zu unterscheiden sind (geprüft mit dem Palettenvalidator)
const ZU_AEHNLICH: [Slot, Slot][] = [["s1", "s7"], ["s2", "s4"]];

export function EinstellungenPanel({ colors, onClose, onGespeichert }: {
  colors: Colors; onClose: () => void; onGespeichert: () => void;
}) {
  const [daten, setDaten] = useState<Einstellungen | null>(null);
  const [start, setStart] = useState("");
  const [namen, setNamen] = useState<string[]>([]);
  const [neu, setNeu] = useState("");
  const [farben, setFarben] = useState<Record<Typ, Slot>>({ ...STANDARD_FARBEN });
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.einstellungen().then((e) => {
      setDaten(e);
      setStart(e.depot_start ?? "");
      setNamen(e.eigene_namen);
      setFarben({ ...STANDARD_FARBEN, ...(e.farben as Record<Typ, Slot>) });
    }).catch((e) => setStatus({ ok: false, text: String(e) }));
    const on = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const passt = (g: string) => {
    if (!namen.length) return true;
    const n = (s: string) => s.toLowerCase().replace(/\s+/g, "");
    return namen.some((x) => n(x) && n(g).includes(n(x)));
  };
  const gegen = useMemo(() => daten?.gegenkonten ?? [], [daten]);

  const hinzufuegen = (s: string) => {
    const t = s.trim();
    if (t && !namen.includes(t)) setNamen([...namen, t]);
    setNeu("");
  };
  const speichern = async () => {
    setStatus(null);
    try {
      const e = await api.einstellungenSpeichern({ depot_start: start || null, eigene_namen: namen, farben });
      setDaten(e);
      setFarbWahl(e.farben);
      setStatus({ ok: true, text: "Gespeichert – alle Auswertungen werden neu berechnet." });
      onGespeichert();
    } catch (e) { setStatus({ ok: false, text: String((e as Error).message) }); }
  };

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.aside role="dialog" aria-modal="true" aria-label="Einstellungen"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-line bg-page shadow-2xl"
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 36 }}>
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Settings2 size={19} /> Einstellungen</h2>
          <button onClick={onClose} aria-label="Schließen"
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 hover:text-ink">
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5 text-sm">
          {/* Depotstart */}
          <section>
            <h3 className="font-semibold">Depoteröffnung</h3>
            <p className="mt-1 text-ink2">Ab diesem Datum werden Daten abgerufen; „Seit Eröffnung“ in den Auswertungen beginnt hier.</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} max={new Date().toISOString().slice(0, 10)}
                className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-accent" />
              {start && <button onClick={() => setStart("")} className="text-accent hover:underline">zurücksetzen</button>}
              {daten && <span className="text-muted">aktuell: {datum(daten.depot_start_wirksam)}
                {!daten.depot_start && " (aus config.toml)"}</span>}
            </div>
          </section>

          {/* Eigene Konten */}
          <section>
            <h3 className="flex items-center gap-2 font-semibold"><UserRound size={16} /> Eigene Namen und IBANs</h3>
            <p className="mt-1 text-ink2">
              Buchungen, deren <b>Empfänger</b> oder <b>Zahlungspflichtiger</b> hier passt, zählen als Ein- bzw.
              Auszahlung – wichtig für Rendite und „Eingezahlt“. Ohne Eintrag zählt jedes Gegenkonto.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {namen.map((n) => (
                <span key={n} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1">
                  {n}
                  <button onClick={() => setNamen(namen.filter((x) => x !== n))} aria-label={`${n} entfernen`}
                    className="text-muted hover:text-ink"><X size={13} /></button>
                </span>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); hinzufuegen(neu); }} className="mt-2 flex gap-2">
              <input value={neu} onChange={(e) => setNeu(e.target.value)} placeholder="Name oder IBAN hinzufügen"
                className="flex-1 rounded-lg border border-line bg-surface px-3 py-1.5 outline-none focus:border-accent" />
              <button className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-3 text-ink2 hover:text-ink">
                <Plus size={15} /> Hinzufügen
              </button>
            </form>
            {gegen.length > 0 && (
              <div className="mt-3 rounded-xl border border-line bg-surface">
                <div className="border-b border-line px-3 py-2 text-[13px] text-ink2">Gegenkonten in deinen Kontoumsätzen</div>
                {gegen.map((g) => {
                  const ok = passt(g.gegenkonto);
                  return (
                    <div key={g.gegenkonto} className="flex items-center justify-between gap-3 border-b border-line/60 px-3 py-2 last:border-0">
                      <div className="min-w-0">
                        <div className="truncate" title={g.gegenkonto}>{g.gegenkonto}</div>
                        <div className="text-xs text-muted">{g.anzahl} Buchung{g.anzahl === 1 ? "" : "en"} · {eurSigned(g.summe)}</div>
                      </div>
                      {ok ? (
                        <span className="inline-flex shrink-0 items-center gap-1 text-good"><Check size={15} /> Ein-/Auszahlung</span>
                      ) : (
                        <button onClick={() => hinzufuegen(g.gegenkonto.split(" | ")[0])}
                          className="shrink-0 rounded-full border border-line px-2.5 py-1 text-[13px] text-ink2 hover:text-ink">
                          gehört mir
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Farben */}
          <section>
            <h3 className="flex items-center gap-2 font-semibold"><Palette size={16} /> Farben der Wertpapierklassen</h3>
            <p className="mt-1 text-ink2">Aus einer geprüften Palette mit eigenen Stufen für den Dunkelmodus.</p>
            <div className="mt-3 space-y-2.5">
              {TYPEN.map((t) => (
                <div key={t} className="flex items-center gap-3">
                  <span className="w-20">{t}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {SLOTS.map(({ slot, name }) => {
                      const belegt = TYPEN.some((x) => x !== t && farben[x] === slot);
                      const aktiv = farben[t] === slot;
                      return (
                        <button key={slot} title={belegt ? `${name} – schon vergeben` : name} disabled={belegt}
                          onClick={() => setFarben({ ...farben, [t]: slot })} aria-label={`${t}: ${name}`}
                          className={cx("grid h-7 w-7 place-items-center rounded-full transition",
                            aktiv ? "ring-2 ring-ink ring-offset-2 ring-offset-page" : "hover:scale-110",
                            belegt && "cursor-not-allowed opacity-25")}
                          style={{ background: colors[slot] }}>
                          {aktiv && <Check size={14} className="text-white" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            {ZU_AEHNLICH.some(([a, b]) => Object.values(farben).includes(a) && Object.values(farben).includes(b)) && (
              <p className="mt-3 text-[13px] text-bad">
                Zwei gewählte Farben sind schwer zu unterscheiden (Blau/Violett bzw. Orange/Gelb) – vor allem bei
                Farbschwäche. Besser eine andere Kombination wählen.
              </p>
            )}
          </section>
        </div>

        <footer className="flex items-center gap-3 border-t border-line px-6 py-4">
          <motion.button whileTap={{ scale: 0.97 }} onClick={speichern}
            className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-white shadow-card hover:brightness-110">
            <Save size={16} /> Speichern
          </motion.button>
          {status && <span className={cx("text-sm", status.ok ? "text-good" : "text-bad")}>{status.text}</span>}
        </footer>
      </motion.aside>
    </>
  );
}
