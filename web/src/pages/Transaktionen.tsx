import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronDown, Download, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api, Meta, Transaktion } from "../api";
import { Colors, cx, datum, eur, eurSigned, monatKurz, num, typFarbe, useLoad } from "../lib";
import { Card, Hinweis, Kpi, Legend } from "../ui";
import { PositionDetail, SuchFeld } from "./Positionen";

type SortKey = "d" | "kategorie" | "name" | "betrag";
const SEITE = 50;

export default function Transaktionen({ meta, colors }: { meta: Meta; colors: Colors }) {
  const { data, error } = useLoad(() => api.transactions(meta.bis_default), [meta.bis_default]);
  const [kat, setKat] = useState<Set<string>>(new Set());
  const [suche, setSuche] = useState("");
  const [von, setVon] = useState("");
  const [bis, setBis] = useState("");
  const [nurGeld, setNurGeld] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "d", desc: true });
  const [anzahl, setAnzahl] = useState(SEITE);
  const [offen, setOffen] = useState<Transaktion | null>(null);

  const kategorien = useMemo(() => {
    const m = new Map<string, number>();
    data?.transaktionen.forEach((t) => m.set(t.kategorie, (m.get(t.kategorie) ?? 0) + 1));
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [data]);

  const liste = useMemo(() => {
    if (!data) return [];
    const s = suche.trim().toLowerCase();
    return data.transaktionen
      .filter((t) => !kat.size || kat.has(t.kategorie))
      .filter((t) => !nurGeld || t.geldfluss)
      .filter((t) => (!von || t.d >= von) && (!bis || t.d <= bis))
      .filter((t) => !s || [t.name, t.isin, t.text, t.kategorie].some((x) => x?.toLowerCase().includes(s)))
      .sort((a, b) => {
        const va = a[sort.key] ?? "", vb = b[sort.key] ?? "";
        const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
        return sort.desc ? -c : c;
      });
  }, [data, kat, suche, von, bis, nurGeld, sort]);

  if (error) return <Card>Fehler: {error}</Card>;
  if (!data) return null;

  const summe = liste.reduce((s, t) => s + (t.betrag ?? 0), 0);
  const zufluss = liste.reduce((s, t) => s + Math.max(t.betrag ?? 0, 0), 0);
  const abfluss = liste.reduce((s, t) => s + Math.min(t.betrag ?? 0, 0), 0);
  const gebuehren = liste.reduce((s, t) => s + (t.gebuehr ?? 0), 0);

  const toggle = (k: string) => {
    const n = new Set(kat);
    n.has(k) ? n.delete(k) : n.add(k);
    setKat(n);
    setAnzahl(SEITE);
  };
  const th = (key: SortKey, label: string, right = false) => (
    <th className={cx("px-3 py-2.5 font-medium", right && "text-right")}>
      <button onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : key !== "name" })}
        className={cx("inline-flex items-center gap-1 hover:text-ink", sort.key === key && "text-ink")}>
        {label}{sort.key === key && (sort.desc ? <ArrowDown size={13} /> : <ArrowUp size={13} />)}
      </button>
    </th>
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Transaktionen" value={liste.length} format={(x) => String(Math.round(x))}
          sub={<span className="text-ink2">von {data.transaktionen.length} gesamt</span>} />
        <Kpi label="Summe (netto)" value={summe} format={(x) => eurSigned(x)} delay={0.05}
          hint="Summe aller Kontobeträge der gefilterten Transaktionen" />
        <Kpi label="Zuflüsse / Abflüsse" value={zufluss} format={(x) => eur(x)} delay={0.1}
          sub={<span className="text-ink2">Abflüsse {eur(abfluss)}</span>} />
        <Kpi label="Gebühren (+ KESt bei Verkauf)" value={gebuehren} format={(x) => eur(x)} delay={0.15} />
      </div>

      <Zeitstrahl liste={liste} colors={colors} onSelect={setOffen} />

      <Card delay={0.1}
        title="Alle Bewegungen"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <input type="date" value={von} onChange={(e) => setVon(e.target.value)} aria-label="Von"
              className="rounded-full border border-line bg-page px-3 py-1.5 text-sm text-ink outline-none focus:border-accent" />
            <input type="date" value={bis} onChange={(e) => setBis(e.target.value)} aria-label="Bis"
              className="rounded-full border border-line bg-page px-3 py-1.5 text-sm text-ink outline-none focus:border-accent" />
            <SuchFeld value={suche} onChange={(v) => { setSuche(v); setAnzahl(SEITE); }} />
            <button onClick={() => exportCsv(liste)}
              className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink2 hover:text-ink">
              <Download size={15} /> CSV
            </button>
          </div>
        }>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {kategorien.map(([k, n]) => (
            <motion.button key={k} onClick={() => toggle(k)} whileTap={{ scale: 0.95 }}
              className={cx("rounded-full border px-3 py-1 text-[13px] transition-colors",
                kat.has(k) ? "border-accent bg-accent/10 text-ink" : "border-line text-ink2 hover:text-ink")}>
              {k} <span className="text-muted">{n}</span>
            </motion.button>
          ))}
          <label className="ml-auto flex items-center gap-2 text-[13px] text-ink2">
            <input type="checkbox" checked={nurGeld} onChange={(e) => setNurGeld(e.target.checked)} className="accent-[rgb(var(--s1))]" />
            nur Geldbewegungen
          </label>
          {(kat.size > 0 || suche || von || bis || nurGeld) && (
            <button onClick={() => { setKat(new Set()); setSuche(""); setVon(""); setBis(""); setNurGeld(false); }}
              className="text-[13px] text-accent hover:underline">Filter zurücksetzen</button>
          )}
        </div>

        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="border-b border-line text-left text-[13px] text-ink2">
              <tr>
                {th("d", "Datum")}
                {th("kategorie", "Kategorie")}
                {th("name", "Wertpapier / Text")}
                <th className="px-3 py-2.5 text-right font-medium">Stück</th>
                <th className="px-3 py-2.5 text-right font-medium">Kurs</th>
                <th className="px-3 py-2.5 text-right font-medium">Gebühr</th>
                {th("betrag", "Betrag", true)}
              </tr>
            </thead>
            <tbody>
              <AnimatePresence initial={false}>
                {liste.slice(0, anzahl).map((t) => (
                  <motion.tr key={t.id} layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    onClick={() => setOffen(t)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setOffen(t)}
                    className="cursor-pointer border-b border-line/70 last:border-0 hover:bg-page focus:bg-page focus:outline-none">
                    <td className="tnum whitespace-nowrap px-3 py-2.5 text-ink2">{datum(t.d)}</td>
                    <td className="px-3 py-2.5"><KategorieChip k={t.kategorie} /></td>
                    <td className="max-w-[340px] px-3 py-2.5">
                      {t.name ? (
                        <div className="flex items-center gap-2">
                          {t.typ && <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: typFarbe(colors, t.typ) }} />}
                          <span className="truncate font-medium" title={t.text}>{t.name}</span>
                        </div>
                      ) : <span className="truncate text-ink2" title={t.text}>{t.text}</span>}
                    </td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{t.stueck == null ? "" : num(t.stueck)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{t.kurs == null ? "" : eur(t.kurs)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{t.gebuehr == null ? "" : eur(t.gebuehr)}</td>
                    <td className={cx("tnum whitespace-nowrap px-3 py-2.5 text-right font-medium",
                      t.betrag == null ? "text-muted" : t.betrag > 0 ? "text-good" : "text-ink")}>
                      {t.betrag == null ? "ohne Geldfluss" : eurSigned(t.betrag)}
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
            </tbody>
          </table>
        </div>
        {liste.length > anzahl && (
          <div className="mt-4 text-center">
            <button onClick={() => setAnzahl(anzahl + SEITE)}
              className="rounded-full border border-line bg-surface px-4 py-2 text-sm text-ink2 hover:text-ink">
              Weitere {Math.min(SEITE, liste.length - anzahl)} anzeigen
            </button>
          </div>
        )}
        <Hinweis>Jede Kontobuchung ist eine Zeile; Käufe und Verkäufe sind mit Stückzahl und Kurs aus dem Depot ergänzt.
          „Ohne Geldfluss" sind reine Depotbuchungen (z. B. die Umbuchung bei thesaurierenden Fonds). Zeile anklicken für Details.</Hinweis>
      </Card>

      <AnimatePresence>
        {offen?.isin && (
          <PositionDetail key={offen.id} isin={offen.isin} bis={data.bis} colors={colors} transaktion={offen}
            onClose={() => setOffen(null)} />
        )}
        {offen && !offen.isin && <BuchungInfo key={offen.id} t={offen} onClose={() => setOffen(null)} />}
      </AnimatePresence>
    </div>
  );
}

// --- Zeitstrahl: wann wurde welches Wertpapier gekauft/verkauft --------------------------------
const ARTEN = [
  { kat: ["Kauf"], name: "Kauf", farbe: "s2", form: "triangle" },
  { kat: ["Verkauf"], name: "Verkauf", farbe: "s3", form: "diamond" },
  { kat: ["Dividende", "Ausschüttung"], name: "Dividende", farbe: "s1", form: "circle" },
] as const;

function Zeitstrahl({ liste, colors, onSelect }: {
  liste: Transaktion[]; colors: Colors; onSelect: (t: Transaktion) => void;
}) {
  const [offen, setOffen] = useState<boolean>(() => {
    try { return localStorage.getItem("zeitstrahl-zu") !== "1"; } catch { return true; }
  });
  const umschalten = () => {
    setOffen(!offen);
    try { localStorage.setItem("zeitstrahl-zu", offen ? "1" : "0"); } catch { /* privates Fenster */ }
  };
  const punkte = liste.filter((t) => t.name && ARTEN.some((a) => (a.kat as readonly string[]).includes(t.kategorie)));
  if (!punkte.length) return null;
  // Zeilen: Wertpapiere in der Reihenfolge des ersten Kaufs
  const namen = Array.from(new Set([...punkte].sort((a, b) => a.d.localeCompare(b.d)).map((t) => t.name!)));
  const zeile = new Map(namen.map((n, i) => [n, i]));
  const reihen = ARTEN.map((a) => ({
    ...a,
    daten: punkte.filter((t) => (a.kat as readonly string[]).includes(t.kategorie)).map((t) => ({
      x: new Date(t.d + "T00:00:00").getTime(), y: zeile.get(t.name!)!, z: Math.abs(t.betrag ?? 0), t,
    })),
  })).filter((r) => r.daten.length);
  const hoehe = Math.max(200, namen.length * 30 + 70);
  return (
    <Card title="Zeitstrahl: Käufe, Verkäufe und Dividenden" delay={0.08}
      right={
        <button onClick={umschalten} aria-expanded={offen}
          className="inline-flex items-center gap-1 rounded-full border border-line bg-page px-3 py-1 text-[13px] text-ink2 hover:text-ink">
          {offen ? "Einklappen" : `Ausklappen (${punkte.length})`}
          <motion.span animate={{ rotate: offen ? 180 : 0 }} transition={{ duration: 0.25 }}><ChevronDown size={15} /></motion.span>
        </button>
      }>
      <AnimatePresence initial={false}>
        {offen && (
          <motion.div key="inhalt" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden">
      <Legend items={reihen.map((r) => ({ label: r.name, color: colors[r.farbe] }))} />
      <div className="mt-3" style={{ height: hoehe }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid stroke={colors.line} horizontal vertical={false} />
            <XAxis type="number" dataKey="x" domain={["dataMin - 864000000", "dataMax + 864000000"]} scale="time"
              tickFormatter={(v) => monatKurz(new Date(v).toISOString().slice(0, 10))} axisLine={{ stroke: colors.axis }}
              tickLine={false} minTickGap={30} />
            <YAxis type="number" dataKey="y" domain={[-0.5, namen.length - 0.5]} ticks={namen.map((_, i) => i)} reversed
              tickFormatter={(i) => kurz(namen[i] ?? "")} width={150} axisLine={false} tickLine={false} interval={0} />
            <ZAxis type="number" dataKey="z" range={[40, 360]} />
            <Tooltip cursor={{ stroke: colors.axis, strokeDasharray: "0" }} content={<PunktTooltip />} />
            {reihen.map((r) => (
              <Scatter key={r.name} name={r.name} data={r.daten} fill={colors[r.farbe]} shape={r.form}
                stroke={colors.surface} strokeWidth={1.5} animationDuration={600}
                onClick={(p: { payload?: { t: Transaktion } }) => p?.payload?.t && onSelect(p.payload.t)}
                style={{ cursor: "pointer" }} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <Hinweis>Eine Zeile je Wertpapier; Größe der Markierung = Betrag. Punkt anklicken für Details. Folgt den Filtern unten.</Hinweis>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}

const kurz = (s: string) => (s.length > 22 ? s.slice(0, 21) + "…" : s);

function PunktTooltip({ active, payload }: { active?: boolean; payload?: { payload: { t: Transaktion } }[] }) {
  const t = active ? payload?.[0]?.payload?.t : null;
  if (!t) return null;
  return (
    <div className="rounded-xl border border-line bg-raised/95 px-3 py-2 text-sm shadow-card backdrop-blur">
      <div className="font-medium">{t.name}</div>
      <div className="text-ink2">{t.kategorie} am {datum(t.d)}</div>
      <div className="tnum">
        {t.stueck != null && <>{num(t.stueck)} Stk. {t.kurs != null && <>zu {eur(t.kurs)} · </>}</>}
        {t.betrag != null && eurSigned(t.betrag)}
      </div>
    </div>
  );
}

// --- Detail für Buchungen ohne Wertpapier (Einzahlung, Zinsen, …) --------------------------------
function BuchungInfo({ t, onClose }: { t: Transaktion; onClose: () => void }) {
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.div role="dialog" aria-modal="true" aria-label="Buchungsdetails"
        className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-xl2 border border-line bg-page p-6 shadow-2xl"
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <KategorieChip k={t.kategorie} />
            <div className={cx("tnum mt-2 text-2xl font-semibold", (t.betrag ?? 0) > 0 && "text-good")}>
              {t.betrag == null ? "ohne Geldfluss" : eurSigned(t.betrag)}
            </div>
          </div>
          <button onClick={onClose} aria-label="Schließen"
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 hover:text-ink"><X size={18} /></button>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-ink2">Buchungstag</dt><dd className="font-medium">{datum(t.d)}</dd></div>
          <div><dt className="text-ink2">Valuta</dt><dd className="font-medium">{datum(t.valuta)}</dd></div>
        </dl>
        <div className="mt-4 text-sm">
          <div className="text-ink2">Buchungstext</div>
          <p className="mt-1 break-words rounded-lg border border-line bg-surface p-3">{t.text}</p>
        </div>
        {(t.kategorie === "Einzahlung" || t.kategorie === "Auszahlung" || t.kategorie === "Sonstiges") && (
          <Hinweis>Ob eine Buchung als Ein-/Auszahlung zählt, hängt von den eigenen Namen/IBANs in den Einstellungen ab.</Hinweis>
        )}
      </motion.div>
    </>
  );
}

function KategorieChip({ k }: { k: string }) {
  return <span className="whitespace-nowrap rounded-full bg-page px-2.5 py-0.5 text-[12px] text-ink2 ring-1 ring-line">{k}</span>;
}

function exportCsv(liste: Transaktion[]) {
  const kopf = ["Datum", "Valuta", "Kategorie", "ISIN", "Wertpapier", "Stück", "Kurs", "Gebühr", "Betrag", "Text"];
  const zahl = (x: number | null) => (x == null ? "" : String(x).replace(".", ","));
  const esc = (s: string | null) => `"${(s ?? "").replace(/"/g, '""')}"`;
  const zeilen = liste.map((t) => [datum(t.d), t.valuta ? datum(t.valuta) : "", t.kategorie, t.isin ?? "", esc(t.name),
    zahl(t.stueck), zahl(t.kurs), zahl(t.gebuehr), zahl(t.betrag), esc(t.text)].join(";"));
  const blob = new Blob(["﻿" + [kopf.join(";"), ...zeilen].join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `transaktionen_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
