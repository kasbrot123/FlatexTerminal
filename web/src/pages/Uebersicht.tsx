import { motion } from "framer-motion";
import { CalendarRange, ChevronRight, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Area, AreaChart, Brush, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, Meta, Transaktion, Typ } from "../api";
import {
  addDays, addMonths, Colors, cx, datum, eur, eurAchse, eurSigned, monatKurz, pct, typFarbe, useLoad,
} from "../lib";
import { Card, ChartTooltip, Delta, Hinweis, Kpi, Segmented } from "../ui";

type Range = "1W" | "1M" | "1J" | "3J" | "5J" | "MAX" | "CUSTOM";
const RANGES: { value: Range; label: ReactNode }[] = [
  { value: "1W", label: "1W" }, { value: "1M", label: "1M" }, { value: "1J", label: "1J" },
  { value: "3J", label: "3J" }, { value: "5J", label: "5J" }, { value: "MAX", label: "Seit Eröffnung" },
  { value: "CUSTOM", label: <CalendarRange size={15} aria-label="Benutzerdefiniert" /> },
];

function vonFuer(r: Range, bis: string, start: string): string {
  const v = { "1W": addDays(bis, -7), "1M": addMonths(bis, -1), "1J": addMonths(bis, -12),
    "3J": addMonths(bis, -36), "5J": addMonths(bis, -60), MAX: start, CUSTOM: start }[r];
  return v < start ? start : v;
}

export default function Uebersicht({ meta, colors, onOpenPositions }: {
  meta: Meta; colors: Colors; onOpenPositions: () => void;
}) {
  const [range, setRange] = useState<Range>("MAX");
  const [custom, setCustom] = useState({ von: meta.depot_start, bis: meta.bis_default });
  const [modus, setModus] = useState<"wert" | "performance">("wert");

  const bis = range === "CUSTOM" ? custom.bis : meta.bis_default;
  const von = range === "CUSTOM" ? custom.von : vonFuer(range, bis, meta.depot_start);
  const { data, loading, error } = useLoad(() => api.overview(von, bis), [von, bis]);
  const { data: tx } = useLoad(() => api.transactions(meta.bis_default), [meta.bis_default]);

  if (error) return <Card>Fehler beim Laden: {error}</Card>;
  if (!data) return <LadeZustand />;
  const k = data.kpi;
  const anteilGewinn = k.eingezahlt ? (k.gewinn_gesamt / k.eingezahlt) * 100 : null;

  return (
    <div className={cx("space-y-5 transition-opacity", loading && "opacity-60")}>
      {/* Filterzeile – gilt für alles auf dieser Seite */}
      <div className="flex flex-wrap items-center gap-3">
        <Segmented options={RANGES} value={range} onChange={setRange} />
        {range === "CUSTOM" && (
          <motion.div initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2 text-sm">
            <DateInput value={custom.von} min={meta.depot_start} max={custom.bis} onChange={(v) => setCustom({ ...custom, von: v })} />
            <span className="text-muted">bis</span>
            <DateInput value={custom.bis} min={custom.von} max={meta.heute} onChange={(v) => setCustom({ ...custom, bis: v })} />
          </motion.div>
        )}
        <span className="text-sm text-muted">{datum(data.von)} – {datum(data.bis)}</span>
      </div>

      {/* Kennzahlen links, Aufteilung als Ring rechts */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-5">
        <Kpi big label="Gesamtvermögen" value={k.vermoegen} format={(x) => eur(x)}
          sub={<span className="text-ink2">Depot {eur(k.depotwert)} · Cash {eur(k.cash)}</span>} />
        <Kpi big label="Gewinn gesamt" value={k.gewinn_gesamt} format={(x) => eurSigned(x)} delay={0.05}
          sub={<Delta value={anteilGewinn} kind="pct" />}
          hint="Vermögen minus eingezahltes Geld, seit Depotstart, nach Gebühren und Steuern" />
        <Kpi big label="Rendite im Zeitraum" value={k.rendite_zeitraum} format={(x) => pct(x)} delay={0.1}
          sub={<span className="text-ink2">zeitgewichtet (TWR)</span>}
          hint="Zeitgewichtete Rendite (TWR): unabhängig von Ein- und Auszahlungen, vergleichbar mit einem Index" />
        <Kpi big label="Interner Zinsfuß (IZF)" value={k.xirr} format={(x) => `${pct(x)} p.a.`} delay={0.12}
          sub={<span className="text-ink2">seit Eröffnung: {k.izf_gesamt == null ? "–" : `${pct(k.izf_gesamt)} p.a.`}</span>}
          hint="Interner Zinsfuß (IZF, auch XIRR): die jährliche Verzinsung deines eingesetzten Geldes – berücksichtigt, wann wie viel ein- und ausgezahlt wurde. Bei Zeiträumen unter einem Jahr hochgerechnet und daher stark schwankend." />
        <Kpi big label="Gewinn im Zeitraum" value={k.gewinn_zeitraum} format={(x) => eurSigned(x)} delay={0.15}
          sub={<span className="text-ink2">Eingezahlt gesamt {eur(k.eingezahlt)}</span>} />
      </div>
      {/* Aktien/ETFs/Derivate stehen jetzt im Ring */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Kpi label="Kursgewinn realisiert" value={k.realisiert} format={(x) => eurSigned(x)} delay={0.2}
          hint="Verkaufskurswert minus anteiliger Einstand, im Zeitraum" />
        <Kpi label="Nicht realisiert" value={k.unrealisiert} format={(x) => eurSigned(x)} delay={0.22}
          hint="Marktwert minus bezahlter Einstand der offenen Positionen" />
        <Kpi label="Dividenden & Zinsen" value={k.dividenden + k.zinsen} format={(x) => eur(x)} delay={0.24} />
      </div>
      </div>

        <Card title="Aufteilung" delay={0.15}
          right={<button onClick={onOpenPositions} className="flex items-center text-sm text-ink2 hover:text-ink">
            Positionen <ChevronRight size={16} /></button>}>
          <Aufteilung data={data.aufteilung} depotwert={k.depotwert} anzahl={data.positionen.length} colors={colors} />
        </Card>
      </div>

      <div>
        <Card delay={0.1}
          title={modus === "wert" ? "Vermögen und Einzahlungen" : "Performance (zeitgewichtet)"}
          right={<Segmented size="sm" value={modus} onChange={setModus}
            options={[{ value: "wert", label: "Wert" }, { value: "performance", label: "Performance" }]} />}>
          {modus === "wert"
            ? <WertChart data={data.serie} colors={colors} transaktionen={tx?.transaktionen ?? []} />
            : <PerfChart data={data.serie} colors={colors} />}
          {modus === "wert"
            ? <Hinweis>Vermögen = Depotwert zu Marktkursen + Cash. Der Abstand zur Einzahlungslinie ist dein Gewinn bzw. Verlust.</Hinweis>
            : <Hinweis>Kumulierte Wertentwicklung ohne den Effekt von Ein- und Auszahlungen.</Hinweis>}
        </Card>
      </div>

      <Card title="Im Zeitraum" delay={0.2}>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
          <Fakt label="Käufe / Verkäufe" value={`${k.kaeufe} / ${k.verkaeufe}`} />
          <Fakt label="Kaufgebühren" value={eur(k.gebuehren)} />
          <Fakt label="Gebühren + KESt bei Verkäufen" value={eur(k.abzuege_verkauf)} />
          <Fakt label="KESt Thesaurierung" value={eur(k.steuer_thesaurierung)} />
          <Fakt label="Dividenden" value={eur(k.dividenden)} />
          <Fakt label="Zinsen" value={eur(k.zinsen)} />
        </dl>
        {data.ersatzkurse.length > 0 && (
          <Hinweis>Ohne Börsenkurs, bewertet mit dem letzten flatex-Handelskurs: {data.ersatzkurse.join(", ")}.</Hinweis>
        )}
      </Card>
    </div>
  );
}

function Fakt({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-ink2">{label}</dt>
      <dd className="tnum mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  );
}

function DateInput({ value, min, max, onChange }: { value: string; min: string; max: string; onChange: (v: string) => void }) {
  return (
    <input type="date" value={value} min={min} max={max} onChange={(e) => e.target.value && onChange(e.target.value)}
      className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-ink outline-none focus:border-accent" />
  );
}

function tickFormat(data: { d: string }[]) {
  const tage = data.length;
  return (d: string) => (tage <= 45 ? datum(d).slice(0, 5) : monatKurz(d));
}

type Linie = "vermoegen" | "eingezahlt" | "cash";
type Marke = "kauf" | "verkauf" | "dividende";
// Gleiche Farben und Formen wie im Zeitstrahl (Reiter Transaktionen)
const MARKEN: { key: Marke; label: string; kat: string[]; farbe: "s1" | "s2" | "s3" }[] = [
  { key: "kauf", label: "Käufe", kat: ["Kauf"], farbe: "s2" },
  { key: "verkauf", label: "Verkäufe", kat: ["Verkauf"], farbe: "s3" },
  { key: "dividende", label: "Dividenden", kat: ["Dividende", "Ausschüttung"], farbe: "s1" },
];
const markenFarbe = (c: Colors, art: Marke) => c[MARKEN.find((m) => m.key === art)!.farbe];

/** Kauf ▲, Verkauf ◆, Dividende ● – wie im Zeitstrahl; die Form unterscheidet zusätzlich zur Farbe. */
function MarkenForm({ art, cx: x, cy: y, r, fill, stroke }: {
  art: Marke; cx: number; cy: number; r: number; fill: string; stroke: string;
}) {
  if (art === "dividende") return <circle cx={x} cy={y} r={r * 0.8} fill={fill} stroke={stroke} strokeWidth={1.5} />;
  const h = r * 1.15;
  const d = art === "kauf"
    ? `M${x},${y - h} L${x + h},${y + h * 0.75} L${x - h},${y + h * 0.75} Z`
    : `M${x},${y - h} L${x + h},${y} L${x},${y + h} L${x - h},${y} Z`;
  return <path d={d} fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />;
}

function MarkenSymbol({ art, color }: { art: Marke; color: string }) {
  return (
    <svg width={12} height={12} aria-hidden><MarkenForm art={art} cx={6} cy={6} r={4.6} fill={color} stroke="none" /></svg>
  );
}

function WertChart({ data, colors, transaktionen }: {
  data: { d: string; vermoegen: number; eingezahlt: number; cash: number; depotwert: number }[]; colors: Colors;
  transaktionen: Transaktion[];
}) {
  const fmtTick = useMemo(() => tickFormat(data), [data]);
  const [markenAus, setMarkenAus] = useState<Set<Marke>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem("marken-aus") ?? "[]")); } catch { return new Set(); }
  });
  const markeUmschalten = (k: Marke) => {
    const n = new Set(markenAus);
    if (n.has(k)) n.delete(k); else n.add(k);
    setMarkenAus(n);
    try { localStorage.setItem("marken-aus", JSON.stringify([...n])); } catch { /* privates Fenster */ }
  };
  // Transaktionen je Tag (nur im sichtbaren Zeitraum) und Markierungen auf der Vermögenslinie
  const { punkte, proTag } = useMemo(() => {
    const von = data[0]?.d ?? "", bis = data[data.length - 1]?.d ?? "";
    const tag = new Map<string, Transaktion[]>();
    for (const t of transaktionen) {
      if (t.d < von || t.d > bis || !MARKEN.some((m) => m.kat.includes(t.kategorie))) continue;
      tag.set(t.d, [...(tag.get(t.d) ?? []), t]);
    }
    const p = data.map((z) => {
      const liste = tag.get(z.d) ?? [];
      const hat = (m: Marke) => liste.some((t) => MARKEN.find((x) => x.key === m)!.kat.includes(t.kategorie));
      return { ...z, kauf: hat("kauf") ? z.vermoegen : null, verkauf: hat("verkauf") ? z.vermoegen : null,
        dividende: hat("dividende") ? z.vermoegen : null };
    });
    return { punkte: p, proTag: tag };
  }, [data, transaktionen]);
  const anzahl = (m: Marke) => punkte.filter((p) => p[m] != null).length;

  // --- Zoom & Verschieben: sichtbarer Ausschnitt als Index-Fenster über alle Tage --------------
  const n = punkte.length;
  const MIN_TAGE = Math.min(7, n);
  const [fenster, setFenster] = useState<[number, number] | null>(null);
  useEffect(() => setFenster(null), [data]);                // neuer Zeitraum oben -> Zoom zurücksetzen
  const [s, e] = fenster ?? [0, Math.max(n - 1, 0)];
  const gezoomt = fenster != null && (s > 0 || e < n - 1);
  const setzen = (start: number, laenge: number) => {
    const l = Math.max(MIN_TAGE, Math.min(n, Math.round(laenge)));
    const a = Math.max(0, Math.min(n - l, Math.round(start)));
    setFenster(l >= n ? null : [a, a + l - 1]);
  };
  const zoom = (faktor: number, anteil = 0.5) => {
    const len = e - s + 1;
    const mitte = s + anteil * len;
    const neu = len * faktor;
    setzen(mitte - anteil * neu, neu);
  };
  const wrapRef = useRef<HTMLDivElement>(null);
  const PLOT_LINKS = 64, PLOT_RECHTS = 8;                 // wie YAxis-Breite und Rand rechts
  const anteilBei = (clientX: number) => {
    const r = wrapRef.current!.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - r.left - PLOT_LINKS) / (r.width - PLOT_LINKS - PLOT_RECHTS)));
  };
  // Strg/⌘ + Mausrad (und Touchpad-Zoomgeste) zoomt um die Stelle unter dem Mauszeiger
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const rad = (ev: WheelEvent) => {
      if (!(ev.ctrlKey || ev.metaKey)) return;              // normales Scrollen der Seite nicht kapern
      ev.preventDefault();
      zoom(ev.deltaY > 0 ? 1.2 : 1 / 1.2, anteilBei(ev.clientX));
    };
    el.addEventListener("wheel", rad, { passive: false });
    return () => el.removeEventListener("wheel", rad);
  });
  // Ziehen verschiebt den Ausschnitt
  const zug = useRef<{ x: number; s: number; breite: number } | null>(null);
  const runter = (ev: React.PointerEvent) => {
    if (!gezoomt || ev.button !== 0) return;
    if ((ev.target as Element).closest?.(".recharts-brush")) return;   // die Übersichtsleiste regelt sich selbst
    const r = wrapRef.current!.getBoundingClientRect();
    zug.current = { x: ev.clientX, s, breite: r.width - PLOT_LINKS - PLOT_RECHTS };
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
  };
  const bewegen = (ev: React.PointerEvent) => {
    if (!zug.current) return;
    const len = e - s + 1;
    const versatz = -((ev.clientX - zug.current.x) / zug.current.breite) * len;
    setzen(zug.current.s + versatz, len);
  };
  const los = () => { zug.current = null; };
  // Drei Linien = die drei paarweise geprüften Palettenfarben; Depotwert steht im Tooltip
  const linien: { key: Linie; label: string; color: string }[] = [
    { key: "vermoegen", label: "Vermögen", color: colors.s1 },
    { key: "eingezahlt", label: "Eingezahlt (netto)", color: colors.s2 },
    { key: "cash", label: "Cash", color: colors.s3 },
  ];
  const [aus, setAus] = useState<Set<Linie>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem("linien-aus") ?? "[]")); } catch { return new Set(); }
  });
  const umschalten = (k: Linie) => {
    const n = new Set(aus);
    if (n.has(k)) n.delete(k); else n.add(k);
    if (n.size === linien.length) return;            // mindestens eine Linie bleibt sichtbar
    setAus(n);
    try { localStorage.setItem("linien-aus", JSON.stringify([...n])); } catch { /* privates Fenster */ }
  };
  const tooltipFmt = (v: number) => eur(v);
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {linien.map((l) => (
          <button key={l.key} onClick={() => umschalten(l.key)} aria-pressed={!aus.has(l.key)}
            className={cx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px] transition",
              aus.has(l.key) ? "border-line text-muted line-through" : "border-line bg-page text-ink2 hover:text-ink")}>
            <span className="h-2.5 w-2.5 rounded-full transition-opacity" style={{ background: l.color, opacity: aus.has(l.key) ? 0.3 : 1 }} />
            {l.label}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-line" aria-hidden />
        {MARKEN.map((m) => (
          <button key={m.key} onClick={() => markeUmschalten(m.key)} aria-pressed={!markenAus.has(m.key)}
            className={cx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px] transition",
              markenAus.has(m.key) ? "border-line text-muted line-through" : "border-line bg-page text-ink2 hover:text-ink")}>
            <span style={{ opacity: markenAus.has(m.key) ? 0.3 : 1 }}><MarkenSymbol art={m.key} color={markenFarbe(colors, m.key)} /></span>
            {m.label} <span className="text-muted">{anzahl(m.key)}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-ink2">
        <div className="inline-flex overflow-hidden rounded-full border border-line bg-page">
          <button onClick={() => zoom(1 / 1.5)} disabled={e - s + 1 <= MIN_TAGE} aria-label="Hineinzoomen"
            className="grid h-8 w-8 place-items-center hover:text-ink disabled:opacity-30"><ZoomIn size={15} /></button>
          <button onClick={() => zoom(1.5)} disabled={!gezoomt} aria-label="Herauszoomen"
            className="grid h-8 w-8 place-items-center border-l border-line hover:text-ink disabled:opacity-30"><ZoomOut size={15} /></button>
          <button onClick={() => setFenster(null)} disabled={!gezoomt} aria-label="Zoom zurücksetzen"
            className="grid h-8 w-8 place-items-center border-l border-line hover:text-ink disabled:opacity-30"><Maximize2 size={14} /></button>
        </div>
        {gezoomt
          ? <span>{datum(punkte[s]?.d)} – {datum(punkte[e]?.d)} · ziehen zum Verschieben</span>
          : <span className="text-muted">Strg + Mausrad zoomt · Ausschnitt unten verschieben oder an den Rändern ziehen</span>}
      </div>
      <div ref={wrapRef} className={cx("mt-2 h-[380px] select-none", gezoomt && "cursor-grab active:cursor-grabbing")}
        onPointerDown={runter} onPointerMove={bewegen} onPointerUp={los} onPointerCancel={los}>
        <ResponsiveContainer>
          <ComposedChart data={punkte} margin={{ top: 12, right: PLOT_RECHTS, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fillWert" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors.s1} stopOpacity={0.28} />
                <stop offset="100%" stopColor={colors.s1} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={colors.line} />
            <XAxis dataKey="d" tickFormatter={fmtTick} axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={28} />
            <YAxis tickFormatter={eurAchse} axisLine={false} tickLine={false} width={64} domain={[0, "auto"]} />
            <Tooltip cursor={{ stroke: colors.axis, strokeWidth: 1 }}
              content={<WertTooltip fmt={tooltipFmt} proTag={proTag} markenAus={markenAus} colors={colors} />} />
            {!aus.has("vermoegen") && (
              <Area type="monotone" dataKey="vermoegen" name="Vermögen" stroke={colors.s1} strokeWidth={2}
                fill="url(#fillWert)" animationDuration={700} activeDot={{ r: 4, strokeWidth: 2, stroke: colors.surface }} />
            )}
            {!aus.has("eingezahlt") && (
              <Line type="stepAfter" dataKey="eingezahlt" name="Eingezahlt (netto)" stroke={colors.s2} strokeWidth={2} dot={false}
                animationDuration={700} activeDot={{ r: 4, strokeWidth: 2, stroke: colors.surface }} />
            )}
            {!aus.has("cash") && (
              <Line type="stepAfter" dataKey="cash" name="Cash" stroke={colors.s3} strokeWidth={2} dot={false}
                animationDuration={700} activeDot={{ r: 4, strokeWidth: 2, stroke: colors.surface }} />
            )}
            {n > MIN_TAGE && (
              <Brush dataKey="d" height={40} startIndex={s} endIndex={e} travellerWidth={10} tickFormatter={fmtTick}
                stroke={colors.axis} fill={colors.surface}
                onChange={(r: { startIndex?: number; endIndex?: number }) => {
                  if (r.startIndex == null || r.endIndex == null) return;
                  setFenster(r.startIndex === 0 && r.endIndex === n - 1 ? null : [r.startIndex, r.endIndex]);
                }}>
                <AreaChart data={punkte}>
                  <Area dataKey="vermoegen" stroke={colors.s1} fill={colors.s1} fillOpacity={0.15} strokeWidth={1}
                    isAnimationActive={false} />
                </AreaChart>
              </Brush>
            )}
            {/* Transaktionen als Markierungen: unsichtbare Linie, nur Punkte an Tagen mit Transaktion */}
            {MARKEN.filter((m) => !markenAus.has(m.key)).map((m) => (
              <Line key={m.key} dataKey={m.key} name={m.label} stroke="none" isAnimationActive={false} activeDot={false}
                legendType="none" connectNulls={false}
                dot={(p: { cx?: number; cy?: number; value?: number | null; index?: number }) =>
                  p.value == null || p.cx == null || p.cy == null
                    ? <g key={`${m.key}-${p.index}`} />
                    : <MarkenForm key={`${m.key}-${p.index}`} art={m.key} cx={p.cx} cy={p.cy} r={6}
                      fill={markenFarbe(colors, m.key)} stroke={colors.surface} />} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

/** Tooltip mit allen Werten des Tages – inkl. Depotwert, auch wenn Linien ausgeblendet sind. */
function WertTooltip({ active, payload, label, fmt, proTag, markenAus, colors }: {
  active?: boolean; label?: string; fmt: (v: number) => string; colors?: Colors;
  payload?: { payload: { vermoegen: number; eingezahlt: number; cash: number; depotwert: number } }[];
  proTag?: Map<string, Transaktion[]>; markenAus?: Set<Marke>;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const zeilen: [string, number][] = [["Vermögen", p.vermoegen], ["davon Depot", p.depotwert], ["davon Cash", p.cash],
    ["Eingezahlt (netto)", p.eingezahlt], ["Gewinn", p.vermoegen - p.eingezahlt]];
  const sichtbar = MARKEN.filter((m) => !markenAus?.has(m.key)).flatMap((m) => m.kat);
  const tx = (label ? proTag?.get(label) ?? [] : []).filter((t) => sichtbar.includes(t.kategorie));
  return (
    <div className="max-w-xs rounded-xl border border-line bg-raised/95 px-3 py-2 text-sm shadow-card backdrop-blur">
      <div className="mb-1 text-xs text-ink2">{label ? datum(label) : ""}</div>
      {zeilen.map(([n, v]) => (
        <div key={n} className="flex justify-between gap-6">
          <span className="text-ink2">{n}</span><span className="tnum font-medium text-ink">{n === "Gewinn" ? eurSigned(v) : fmt(v)}</span>
        </div>
      ))}
      {tx.length > 0 && (
        <div className="mt-2 space-y-1 border-t border-line pt-2">
          {tx.slice(0, 6).map((t) => {
            const art = MARKEN.find((m) => m.kat.includes(t.kategorie))!.key;
            return (
              <div key={t.id} className="flex items-start gap-1.5">
                <span className="mt-1"><MarkenSymbol art={art} color={colors ? markenFarbe(colors, art) : "currentColor"} /></span>
                <span className="min-w-0 flex-1 truncate">{t.kategorie} {t.name}</span>
                <span className="tnum shrink-0 text-ink2">{t.betrag != null ? eurSigned(t.betrag) : ""}</span>
              </div>
            );
          })}
          {tx.length > 6 && <div className="text-xs text-muted">+ {tx.length - 6} weitere</div>}
        </div>
      )}
    </div>
  );
}

function PerfChart({ data, colors }: { data: { d: string; rendite: number }[]; colors: Colors }) {
  const fmtTick = useMemo(() => tickFormat(data), [data]);
  const last = data.length ? data[data.length - 1].rendite : 0;
  return (
    <>
      <div className="text-sm text-ink2">Ende des Zeitraums: <Delta value={last} kind="pct" /></div>
      <div className="mt-3 h-[320px]">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fillPerf" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={colors.s1} stopOpacity={0.22} />
                <stop offset="100%" stopColor={colors.s1} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={colors.line} />
            <XAxis dataKey="d" tickFormatter={fmtTick} axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={28} />
            <YAxis tickFormatter={(v) => `${v} %`} axisLine={false} tickLine={false} width={52} />
            <ReferenceLine y={0} stroke={colors.axis} />
            <Tooltip cursor={{ stroke: colors.axis, strokeWidth: 1 }}
              content={<ChartTooltip fmt={(v) => pct(v)} labelFmt={datum} />} />
            <Area type="monotone" dataKey="rendite" name="Rendite" stroke={colors.s1} strokeWidth={2}
              fill="url(#fillPerf)" animationDuration={900} activeDot={{ r: 4, strokeWidth: 2, stroke: colors.surface }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

/** Aufteilung als Ring: Depotwert in der Mitte, Legende mit Wert und Anteil (Werte nie nur per Farbe). */
function Aufteilung({ data, depotwert, anzahl, colors }: {
  data: { typ: Typ; wert: number; anteil: number }[]; depotwert: number; anzahl: number; colors: Colors;
}) {
  const [aktiv, setAktiv] = useState<Typ | null>(null);
  if (!data.length) return <p className="text-sm text-muted">Keine offenen Positionen.</p>;
  const hervor = data.find((a) => a.typ === aktiv);
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row xl:flex-col">
      <div className="relative h-[180px] w-[180px] shrink-0">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="wert" nameKey="typ" innerRadius="68%" outerRadius="100%" paddingAngle={data.length > 1 ? 2 : 0}
              cornerRadius={4} stroke={colors.surface} strokeWidth={2} startAngle={90} endAngle={-270}
              animationDuration={900} onMouseEnter={(_, i) => setAktiv(data[i].typ)} onMouseLeave={() => setAktiv(null)}>
              {data.map((a) => (
                <Cell key={a.typ} fill={typFarbe(colors, a.typ)} opacity={aktiv && aktiv !== a.typ ? 0.35 : 1}
                  style={{ transition: "opacity .2s" }} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        {/* Mitte: Depotwert bzw. die Klasse unter dem Mauszeiger */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-[12px] text-ink2">{hervor ? hervor.typ : "Depot"}</span>
          <span className="tnum text-[15px] font-semibold">{eur(hervor ? hervor.wert : depotwert)}</span>
          <span className="text-[12px] text-muted">
            {hervor ? `${hervor.anteil.toFixed(1).replace(".", ",")} %` : `${anzahl} Positionen`}
          </span>
        </div>
      </div>
      <ul className="w-full space-y-2 text-sm">
        {data.map((a) => (
          <li key={a.typ} onMouseEnter={() => setAktiv(a.typ)} onMouseLeave={() => setAktiv(null)}
            className={cx("flex items-center justify-between gap-3 rounded-lg px-2 py-1 transition-colors",
              aktiv === a.typ && "bg-page")}>
            <span className="flex items-center gap-2 text-ink2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: typFarbe(colors, a.typ) }} />{a.typ}
            </span>
            <span className="text-right">
              <span className="tnum font-medium text-ink">{a.anteil.toFixed(1).replace(".", ",")} %</span>
              <span className="tnum block text-[12px] text-muted">{eur(a.wert)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LadeZustand() {
  return (
    <div className="grid gap-3 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <motion.div key={i} className="h-24 rounded-xl2 border border-line bg-surface"
          animate={{ opacity: [0.5, 1, 0.5] }} transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.1 }} />
      ))}
    </div>
  );
}
