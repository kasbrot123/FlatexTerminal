import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowUp, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import { AktivePosition, api, Meta, Transaktion, Typ } from "../api";
import { Colors, cx, datum, eur, eurAchse, eurSigned, monatKurz, num, pct, typFarbe, useLoad } from "../lib";
import { Badge, Card, ChartTooltip, Delta, Hinweis, Kpi, Legend, Segmented, Sparkline } from "../ui";

type SortKey = "name" | "wert" | "gewinn" | "gewinn_pct" | "anteil" | "transaktionen";

/** Anzahl Transaktionen mit Aufschlüsselung als Tooltip. */
function AnzahlZelle({ p }: { p: { kaeufe: number; verkaeufe: number; ertraege: number; transaktionen: number } }) {
  const teile = [`${p.kaeufe} Kauf${p.kaeufe === 1 ? "" : "e"}`, `${p.verkaeufe} Verkauf${p.verkaeufe === 1 ? "" : "e"}`]
    .concat(p.ertraege ? [`${p.ertraege} Dividende${p.ertraege === 1 ? "" : "n"}`] : []);
  return (
    <span className="tnum" title={teile.join(" · ")}>
      {p.transaktionen}
      <span className="ml-1 text-xs text-muted">({p.kaeufe}K/{p.verkaeufe}V{p.ertraege ? `/${p.ertraege}D` : ""})</span>
    </span>
  );
}

export default function Positionen({ meta, colors }: { meta: Meta; colors: Colors }) {
  const { data, error } = useLoad(() => api.positions(meta.bis_default), [meta.bis_default]);
  const [typ, setTyp] = useState<"Alle" | Typ>("Alle");
  const [suche, setSuche] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "wert", desc: true });
  const [offen, setOffen] = useState<string | null>(null);

  const liste = useMemo(() => {
    if (!data) return [];
    const s = suche.trim().toLowerCase();
    return data.aktiv
      .filter((p) => typ === "Alle" || p.typ === typ)
      .filter((p) => !s || p.name.toLowerCase().includes(s) || p.isin.toLowerCase().includes(s))
      .sort((a, b) => {
        const va = a[sort.key], vb = b[sort.key];
        const c = typeof va === "string" ? (va as string).localeCompare(vb as string) : (va as number) - (vb as number);
        return sort.desc ? -c : c;
      });
  }, [data, typ, suche, sort]);

  if (error) return <Card>Fehler: {error}</Card>;
  if (!data) return null;
  const summe = liste.reduce((s, p) => ({ wert: s.wert + p.wert, gewinn: s.gewinn + p.gewinn, einstand: s.einstand + p.einstand }),
    { wert: 0, gewinn: 0, einstand: 0 });
  const typen = Array.from(new Set(data.aktiv.map((p) => p.typ)));
  const th = (key: SortKey, label: string, right = true) => (
    <th className={cx("px-3 py-2.5 font-medium", right && "text-right")}>
      <button onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : true })}
        className={cx("inline-flex items-center gap-1 hover:text-ink", sort.key === key && "text-ink")}>
        {label}{sort.key === key && (sort.desc ? <ArrowDown size={13} /> : <ArrowUp size={13} />)}
      </button>
    </th>
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Positionen" value={liste.length} format={(x) => String(Math.round(x))} />
        <Kpi label="Marktwert" value={summe.wert} format={(x) => eur(x)} delay={0.05} />
        <Kpi label="Einstand (bezahlt)" value={summe.einstand} format={(x) => eur(x)} delay={0.1} />
        <Kpi label="Nicht realisiert" value={summe.gewinn} format={(x) => eurSigned(x)} delay={0.15}
          sub={<Delta value={summe.einstand ? (summe.gewinn / summe.einstand) * 100 : null} kind="pct" />} />
      </div>

      <Card title={`Aktive Positionen am ${datum(data.bis)}`} delay={0.1}
        right={
          <div className="flex flex-wrap items-center gap-2">
            {typen.length > 1 && (
              <Segmented size="sm" value={typ} onChange={setTyp}
                options={[{ value: "Alle", label: "Alle" }, ...typen.map((t) => ({ value: t, label: t }))]} />
            )}
            <SuchFeld value={suche} onChange={setSuche} />
          </div>
        }>
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[920px] text-sm">
            <thead className="border-b border-line text-left text-[13px] text-ink2">
              <tr>
                {th("name", "Wertpapier", false)}
                <th className="px-3 py-2.5 font-medium">90 Tage</th>
                <th className="px-3 py-2.5 text-right font-medium">Stück</th>
                <th className="px-3 py-2.5 text-right font-medium">Ø Einstand</th>
                <th className="px-3 py-2.5 text-right font-medium">Kurs</th>
                {th("wert", "Wert")}
                {th("gewinn", "Gewinn")}
                {th("gewinn_pct", "%")}
                {th("transaktionen", "Transaktionen")}
                {th("anteil", "Anteil")}
              </tr>
            </thead>
            <tbody>
              {liste.map((p, i) => (
                <motion.tr key={p.isin} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.025, 0.3) }}
                  onClick={() => setOffen(p.isin)}
                  className="cursor-pointer border-b border-line/70 transition-colors last:border-0 hover:bg-page">
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2.5">
                      <span className="h-8 w-1 rounded-full" style={{ background: typFarbe(colors, p.typ) }} />
                      <div className="min-w-0">
                        <div className="truncate font-medium text-ink">{p.name}</div>
                        <div className="flex items-center gap-2 text-xs text-muted">{p.isin}
                          {p.ersatzkurs && <Badge>Ersatzkurs</Badge>}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3"><Sparkline values={p.spark} color={p.gewinn >= 0 ? colors.good : colors.bad} /></td>
                  <td className="tnum px-3 py-3 text-right">{num(p.stueck)}</td>
                  <td className="tnum px-3 py-3 text-right text-ink2">{eur(p.durchschnitt)}</td>
                  <td className="tnum px-3 py-3 text-right text-ink2">{eur(p.kurs)}</td>
                  <td className="tnum px-3 py-3 text-right font-medium">{eur(p.wert)}</td>
                  <td className="px-3 py-3 text-right"><Delta value={p.gewinn} /></td>
                  <td className="px-3 py-3 text-right"><Delta value={p.gewinn_pct} kind="pct" /></td>
                  <td className="px-3 py-3 text-right"><AnzahlZelle p={p} /></td>
                  <td className="px-3 py-3">
                    <div className="ml-auto flex w-24 items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line/60">
                        <motion.div className="h-full rounded-full" style={{ background: typFarbe(colors, p.typ) }}
                          initial={{ width: 0 }} animate={{ width: `${p.anteil}%` }} transition={{ duration: 0.7 }} />
                      </div>
                      <span className="tnum w-10 text-right text-xs text-ink2">{p.anteil.toFixed(1).replace(".", ",")}</span>
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
        <Hinweis>Einstand = tatsächlich bezahlt inkl. Kaufgebühren. Zeile anklicken für Details.</Hinweis>
      </Card>

      {data.geschlossen.length > 0 && (
        <Card title="Geschlossene Positionen" delay={0.15}>
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-line text-left text-[13px] text-ink2">
                <tr>
                  <th className="px-3 py-2.5 font-medium">Wertpapier</th>
                  <th className="px-3 py-2.5 font-medium">Zuletzt</th>
                  <th className="px-3 py-2.5 text-right font-medium">Gekauft</th>
                  <th className="px-3 py-2.5 text-right font-medium">Verkauft</th>
                  <th className="px-3 py-2.5 text-right font-medium">Ergebnis</th>
                  <th className="px-3 py-2.5 text-right font-medium">%</th>
                  <th className="px-3 py-2.5 text-right font-medium">Transaktionen</th>
                </tr>
              </thead>
              <tbody>
                {[...data.geschlossen].sort((a, b) => b.ergebnis - a.ergebnis).map((p) => (
                  <tr key={p.isin} onClick={() => setOffen(p.isin)}
                    className="cursor-pointer border-b border-line/70 last:border-0 hover:bg-page">
                    <td className="px-3 py-2.5"><div className="font-medium">{p.name}</div><div className="text-xs text-muted">{p.isin}</div></td>
                    <td className="px-3 py-2.5 text-ink2">{datum(p.letzte)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{eur(p.gekauft)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{eur(p.verkauft)}</td>
                    <td className="px-3 py-2.5 text-right"><Delta value={p.ergebnis} /></td>
                    <td className="px-3 py-2.5 text-right"><Delta value={p.ergebnis_pct} kind="pct" /></td>
                    <td className="px-3 py-2.5 text-right"><AnzahlZelle p={p} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Hinweis>Ergebnis = Verkaufserlöse + Dividenden − bezahlte Käufe − Steuern.</Hinweis>
        </Card>
      )}

      <AnimatePresence>
        {offen && <Detail isin={offen} bis={data.bis} colors={colors} onClose={() => setOffen(null)} />}
      </AnimatePresence>
    </div>
  );
}

export function SuchFeld({ value, onChange, placeholder = "Suchen …" }: {
  value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <label className="flex items-center gap-2 rounded-full border border-line bg-page px-3 py-1.5 text-sm focus-within:border-accent">
      <Search size={15} className="text-muted" />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-36 bg-transparent text-ink outline-none placeholder:text-muted" />
    </label>
  );
}

// --- Detailansicht als Seitenpanel (auch aus dem Reiter Transaktionen) ---------------------
export const Detail = PositionDetail;

export function PositionDetail({ isin, bis, colors, onClose, transaktion }: {
  isin: string; bis: string; colors: Colors; onClose: () => void; transaktion?: Transaktion;
}) {
  const { data } = useLoad(() => api.position(isin, bis), [isin, bis]);
  const geschlossen = !!data && Math.abs(data.summe.stueck) < 1e-9;
  const [ansicht, setAnsicht] = useState<"kurs" | "wert">("kurs");
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const kaeufe = data?.buchungen.filter((b) => b.art === "Kauf").map((b) => ({ d: b.d, kauf: b.kurs, b })) ?? [];
  const verkaeufe = data?.buchungen.filter((b) => b.art === "Verkauf").map((b) => ({ d: b.d, verkauf: b.kurs, b })) ?? [];
  const chartData = useMemo(() => {
    if (!data) return [];
    const m = new Map(data.verlauf.map((v) => [v.d, { ...v } as Record<string, unknown>]));
    for (const k of kaeufe) m.set(k.d, { ...(m.get(k.d) ?? { d: k.d }), kauf: k.kauf });
    for (const v of verkaeufe) m.set(v.d, { ...(m.get(v.d) ?? { d: v.d }), verkauf: v.verkauf });
    return Array.from(m.values()).sort((a, b) => String(a.d).localeCompare(String(b.d)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.aside role="dialog" aria-modal="true" aria-label="Positionsdetails"
        className="fixed inset-y-0 right-0 z-50 w-full max-w-3xl overflow-y-auto border-l border-line bg-page p-5 shadow-2xl sm:p-7"
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 36 }}>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              {data && <Badge color={typFarbe(colors, data.typ)}>{data.typ}</Badge>}
              {data && <Badge>{geschlossen ? "geschlossen" : "aktiv"}</Badge>}
              {data?.ticker && (
                <span className="text-xs text-muted">
                  Kursquelle {data.ticker}{data.waehrung && data.waehrung !== "EUR" ? ` (${data.waehrung}, umgerechnet in €)` : ""}
                </span>
              )}
            </div>
            <h2 className="mt-1.5 text-xl font-semibold">{data?.name ?? isin}</h2>
            <div className="text-sm text-muted">{isin}</div>
          </div>
          <button onClick={onClose} aria-label="Schließen"
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 hover:text-ink">
            <X size={18} />
          </button>
        </div>

        {!data ? <div className="h-40 animate-pulse rounded-xl2 bg-surface" /> : (
          <div className="space-y-5">
            {transaktion && <TransaktionKarte t={transaktion} verlauf={data.verlauf} aktuell={data.summe.kurs} />}
            {geschlossen ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Kpi label="Gekauft für" value={data.summe.gekauft_eur} format={(x) => eur(x)}
                  sub={<span className="text-ink2">{data.summe.kaeufe} Käufe</span>} />
                <Kpi label="Verkauft für" value={data.summe.verkauft_eur} format={(x) => eur(x)} delay={0.04}
                  sub={<span className="text-ink2">{data.summe.verkaeufe} Verkäufe</span>} />
                <Kpi label="Dividenden" value={data.summe.ertraege} format={(x) => eur(x)} delay={0.08} />
                <Kpi label="Ergebnis gesamt" value={data.summe.ergebnis} format={(x) => eurSigned(x)} delay={0.12}
                  sub={<Delta value={data.summe.ergebnis_pct} kind="pct" />}
                  hint="Verkaufserlöse + Dividenden − bezahlte Käufe − Steuern" />
              </div>
            ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Kpi label="Wert" value={data.summe.marktwert} format={(x) => eur(x)}
                sub={<span className="text-ink2">{num(data.summe.stueck)} Stk. × {eur(data.summe.kurs)}</span>} />
              <Kpi label="Einstand" value={data.summe.einstand} format={(x) => eur(x)} delay={0.04} />
              <Kpi label="Nicht realisiert" value={data.summe.unrealisiert} format={(x) => eurSigned(x)} delay={0.08} />
              <Kpi label="Ergebnis gesamt" value={data.summe.ergebnis} format={(x) => eurSigned(x)} delay={0.12}
                sub={<Delta value={data.summe.ergebnis_pct} kind="pct" />}
                hint="Wert + Verkaufserlöse + Dividenden − bezahlte Käufe − Steuern" />
            </div>
            )}
            <p className="text-sm text-ink2">
              {data.summe.kaeufe} Käufe für {eur(data.summe.gekauft_eur)} · {data.summe.verkaeufe} Verkäufe für{" "}
              {eur(data.summe.verkauft_eur)} · Gebühren {eur(data.summe.gebuehren)} · Erträge {eur(data.summe.ertraege)}
              {data.summe.steuer_thesaurierung > 0 && <> · KESt Thesaurierung {eur(data.summe.steuer_thesaurierung)}</>}
            </p>

            <Card title={ansicht === "kurs" ? "Kurs mit deinen Käufen und Verkäufen" : "Wert und investiertes Geld"}
              right={<Segmented size="sm" value={ansicht} onChange={setAnsicht}
                options={[{ value: "kurs", label: "Kurs" }, { value: "wert", label: "Wert" }]} />}>
              <Legend items={ansicht === "kurs"
                ? [{ label: "Kurs", color: colors.s1 }, { label: "Kauf", color: colors.s2 }, { label: "Verkauf", color: colors.s3 }]
                : [{ label: "Wert", color: colors.s1 }, { label: "Investiert (netto)", color: colors.s2 }]} />
              <div className="mt-3 h-[280px]">
                <ResponsiveContainer>
                  <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={colors.line} />
                    <XAxis dataKey="d" tickFormatter={monatKurz} axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={30} />
                    <YAxis tickFormatter={eurAchse} axisLine={false} tickLine={false} width={70} domain={["auto", "auto"]} />
                    <Tooltip cursor={{ stroke: colors.axis }} content={<ChartTooltip fmt={(v) => eur(v)} labelFmt={datum} />} />
                    {ansicht === "kurs" ? (
                      <>
                        <Line dataKey="kurs" name="Kurs" stroke={colors.s1} strokeWidth={2} dot={false} connectNulls animationDuration={800} />
                        <Scatter dataKey="kauf" name="Kauf" fill={colors.s2} shape="triangle" stroke={colors.surface} strokeWidth={2} />
                        <Scatter dataKey="verkauf" name="Verkauf" fill={colors.s3} shape="diamond" stroke={colors.surface} strokeWidth={2} />
                      </>
                    ) : (
                      <>
                        <Line dataKey="wert" name="Wert" stroke={colors.s1} strokeWidth={2} dot={false} connectNulls animationDuration={800} />
                        <Line dataKey="investiert" name="Investiert" type="stepAfter" stroke={colors.s2} strokeWidth={2} dot={false} connectNulls animationDuration={800} />
                      </>
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              {data.ersatzkurs && <Hinweis>Kein Börsenkurs verfügbar – bewertet mit dem letzten flatex-Handelskurs.</Hinweis>}
            </Card>

            <Card title="Buchungen">
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="border-b border-line text-left text-[13px] text-ink2">
                    <tr>
                      <th className="px-3 py-2 font-medium">Datum</th><th className="px-3 py-2 font-medium">Art</th>
                      <th className="px-3 py-2 text-right font-medium">Stück</th><th className="px-3 py-2 text-right font-medium">Kurs</th>
                      <th className="px-3 py-2 text-right font-medium">Konto</th><th className="px-3 py-2 text-right font-medium">Gebühr</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.buchungen.map((b, i) => (
                      <tr key={i} className="border-b border-line/70 last:border-0">
                        <td className="px-3 py-2 text-ink2">{datum(b.d)}</td>
                        <td className="px-3 py-2">{b.art}</td>
                        <td className="tnum px-3 py-2 text-right">{num(b.stueck)}</td>
                        <td className="tnum px-3 py-2 text-right text-ink2">{eur(b.kurs)}</td>
                        <td className="tnum px-3 py-2 text-right">{b.konto == null ? "–" : eurSigned(b.konto)}</td>
                        <td className="tnum px-3 py-2 text-right text-ink2">{eur(b.gebuehr ?? b.abzuege_verkauf)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {data.ertraege.length > 0 && (
                <div className="mt-4 space-y-1.5 text-sm">
                  {data.ertraege.map((e, i) => (
                    <div key={i} className="flex justify-between gap-3">
                      <span className="text-ink2">{datum(e.d)} · {e.kategorie}</span>
                      <span className="tnum">{eurSigned(e.betrag)}</span>
                    </div>
                  ))}
                </div>
              )}
              <Hinweis>Bei Verkäufen enthält die Gebühr auch die einbehaltene KESt (Trennung folgt mit den PDFs).
                {data.kurs_abweichung != null && <> Kursquelle weicht im Schnitt {pct(data.kurs_abweichung * 100, 1).replace("+", "")} von den flatex-Ausführungskursen ab.</>}
              </Hinweis>
            </Card>
          </div>
        )}
      </motion.aside>
    </>
  );
}

/** Hervorgehobene Einzeltransaktion: Ausführungskurs vs. Börsenkurs am Tag und heute. */
function TransaktionKarte({ t, verlauf, aktuell }: {
  t: Transaktion; verlauf: { d: string; kurs: number | null }[]; aktuell: number | null;
}) {
  // Börsenkurs am Tag (bzw. letzter davor) und letzter verfügbarer Kurs
  const amTag = [...verlauf].reverse().find((v) => v.d <= t.d && v.kurs != null)?.kurs ?? null;
  const letzter = aktuell ?? [...verlauf].reverse().find((v) => v.kurs != null)?.kurs ?? null;
  const basis = t.kurs ?? amTag;
  const seitdem = basis && letzter ? (letzter / basis - 1) * 100 : null;
  const istVerkauf = t.kategorie === "Verkauf";
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-xl2 border border-accent/50 bg-accent/5 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-semibold">Diese Transaktion: {t.kategorie} am {datum(t.d)}</span>
        {t.valuta && <span className="text-xs text-muted">Valuta {datum(t.valuta)}</span>}
      </div>
      <dl className="grid grid-cols-2 gap-x-5 gap-y-2.5 text-sm sm:grid-cols-4">
        {t.stueck != null && <Feld label="Stück" wert={num(t.stueck)} />}
        {t.kurs != null && <Feld label="Ausführungskurs" wert={eur(t.kurs)} />}
        <Feld label="Börsenkurs am Tag" wert={eur(amTag)} />
        <Feld label={letzter === aktuell && aktuell != null ? "Kurs heute" : "letzter Kurs"} wert={eur(letzter)} />
        {t.betrag != null && <Feld label="Kontobetrag" wert={eurSigned(t.betrag)} />}
        {t.gebuehr != null && <Feld label={istVerkauf ? "Gebühren + KESt" : "Gebühr"} wert={eur(t.gebuehr)} />}
        {seitdem != null && (
          <div>
            <dt className="text-ink2">{istVerkauf ? "Kurs seit Verkauf" : "Kurs seitdem"}</dt>
            <dd className="mt-0.5"><Delta value={seitdem} kind="pct" /></dd>
          </div>
        )}
      </dl>
      <p className="mt-3 break-words text-[12px] text-muted">{t.text}</p>
    </motion.div>
  );
}

function Feld({ label, wert }: { label: string; wert: string }) {
  return <div><dt className="text-ink2">{label}</dt><dd className="tnum mt-0.5 font-medium">{wert}</dd></div>;
}

export type { AktivePosition };
