import { motion } from "framer-motion";
import { CalendarClock, CheckCircle2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, KalenderEintrag, Meta } from "../api";
import { Colors, cx, datum, eur, eurAchse, monatKurz, pct, useLoad } from "../lib";

type Gruppe = "monat" | "quartal" | "jahr";

const monatsDiff = (a: string, b: string) =>
  (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + Number(b.slice(5, 7)) - Number(a.slice(5, 7)) + 1;

/** Summen je Monat/Quartal/Jahr über den ganzen Zeitraum (auch leere Perioden), optional aufaddiert. */
function perioden(liste: KalenderEintrag[], von: string, bis: string, gruppe: Gruppe, kumuliert: boolean) {
  const schluessel = (iso: string) => {
    const y = iso.slice(0, 4), m = Number(iso.slice(5, 7));
    return gruppe === "jahr" ? y : gruppe === "quartal" ? `${y}-Q${Math.ceil(m / 3)}` : iso.slice(0, 7);
  };
  const label = (k: string) => gruppe === "monat" ? monatKurz(`${k}-01`) : gruppe === "quartal" ? k.replace("-", " ") : k;
  const keys: string[] = [];
  let y = Number(von.slice(0, 4)), m = Number(von.slice(5, 7));
  const endY = Number(bis.slice(0, 4)), endM = Number(bis.slice(5, 7));
  while (y < endY || (y === endY && m <= endM)) {
    const k = schluessel(`${y}-${String(m).padStart(2, "0")}-01`);
    if (keys[keys.length - 1] !== k) keys.push(k);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  const summen = new Map<string, number>(keys.map((k) => [k, 0]));
  liste.forEach((e) => { const k = schluessel(e.d); if (summen.has(k)) summen.set(k, summen.get(k)! + e.netto); });
  let lauf = 0;
  return keys.map((k) => {
    lauf += summen.get(k)!;
    return { key: k, label: label(k), wert: Math.round((kumuliert ? lauf : summen.get(k)!) * 100) / 100 };
  });
}
import { Card, ChartTooltip, Hinweis, Kpi, Segmented } from "../ui";

const MONATE = ["Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
  "November", "Dezember"];

export default function Dividenden({ meta, colors }: { meta: Meta; colors: Colors }) {
  const { data, error } = useLoad(() => api.dividends(meta.bis_default), [meta.bis_default]);
  const jahre = useMemo(() => {
    const s = new Set<number>();
    data?.kalender.forEach((k) => s.add(Number(k.d.slice(0, 4))));
    return Array.from(s).sort();
  }, [data]);
  const [jahr, setJahr] = useState<number | null>(null);
  const aktivesJahr = jahr ?? jahre.find((j) => j === Number(meta.bis_default.slice(0, 4))) ?? jahre[jahre.length - 1];

  // Filter: Zeitraum + Gruppierung + Darstellung
  const [filter, setFilter] = useState<"alles" | "jahr" | "zeitraum">("alles");
  const [filterJahr, setFilterJahr] = useState<number | null>(null);
  const [von, setVon] = useState(meta.depot_start);
  const [bis, setBis] = useState(meta.bis_default);
  const [gruppe, setGruppe] = useState<Gruppe>("monat");
  const [kumuliert, setKumuliert] = useState(false);

  const erhalten = useMemo(() => (data?.kalender ?? []).filter((e) => e.status === "erhalten"), [data]);
  const fJahr = filterJahr ?? jahre[jahre.length - 1];
  const [fVon, fBis] = filter === "alles" ? [meta.depot_start, meta.bis_default]
    : filter === "jahr" ? [`${fJahr}-01-01`, `${fJahr}-12-31`] : [von, bis];
  const gefiltert = erhalten.filter((e) => e.d >= fVon && e.d <= fBis);
  const reihe = useMemo(() => perioden(gefiltert, fVon, fBis, gruppe, kumuliert),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [gefiltert.length, fVon, fBis, gruppe, kumuliert]);
  const proTitel = useMemo(() => {
    const m = new Map<string, { name: string; netto: number; anzahl: number }>();
    gefiltert.forEach((e) => {
      const x = m.get(e.isin) ?? { name: e.name ?? e.isin, netto: 0, anzahl: 0 };
      x.netto += e.netto; x.anzahl += 1;
      m.set(e.isin, x);
    });
    return Array.from(m.entries()).map(([isin, v]) => ({ isin, ...v })).sort((a, b) => b.netto - a.netto);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gefiltert.length, fVon, fBis]);

  if (error) return <Card>Fehler: {error}</Card>;
  if (!data) return null;
  const k = data.kpi;
  const maxTitel = Math.max(...proTitel.map((t) => t.netto), 1);
  const summe = gefiltert.reduce((s, e) => s + e.netto, 0);
  const monateImZeitraum = Math.max(1, monatsDiff(fVon, fBis > meta.bis_default ? meta.bis_default : fBis));
  const jahresOptionen = jahre.filter((j) => `${j}-01-01` <= meta.bis_default);

  return (
    <div className="space-y-5">
      {/* Filterzeile – gilt für Kennzahlen, Diagramm und „Nach Wertpapier“ */}
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={filter} onChange={setFilter} options={[
          { value: "alles", label: "Seit Eröffnung" }, { value: "jahr", label: "Jahr" }, { value: "zeitraum", label: "Von – Bis" }]} />
        {filter === "jahr" && jahresOptionen.length > 0 && (
          <Segmented size="sm" value={String(fJahr)} onChange={(v) => setFilterJahr(Number(v))}
            options={jahresOptionen.map((j) => ({ value: String(j), label: String(j) }))} />
        )}
        {filter === "zeitraum" && (
          <span className="flex items-center gap-2 text-sm">
            <input type="date" value={von} max={bis} onChange={(e) => e.target.value && setVon(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-ink outline-none focus:border-accent" />
            <span className="text-muted">bis</span>
            <input type="date" value={bis} min={von} onChange={(e) => e.target.value && setBis(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-ink outline-none focus:border-accent" />
          </span>
        )}
        <span className="text-sm text-muted">{datum(fVon)} – {datum(fBis)}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi big label="Erhalten im Zeitraum" value={summe} format={(x) => eur(x)}
          sub={<span className="text-ink2">{gefiltert.length} Zahlungen, netto · Ø {eur(summe / monateImZeitraum)}/Monat</span>} />
        <Kpi big label="Letzte 12 Monate" value={k.ttm} format={(x) => eur(x)} delay={0.05}
          sub={<span className="text-ink2">Rendite {pct(k.rendite_ttm).replace("+", "")} netto</span>}
          hint="Netto erhaltene Dividenden der letzten 12 Monate, bezogen auf den aktuellen Depotwert" />
        <Kpi big label="Erwartet (12 Monate)" value={k.erwartet_netto} format={(x) => eur(x)} delay={0.1}
          sub={<span className="text-ink2">brutto {eur(k.erwartet_brutto)} · {pct(k.rendite_erwartet).replace("+", "")}</span>}
          hint="Prognose: Ausschüttungen der letzten 12 Monate fortgeschrieben × aktuelle Stückzahl; netto mit 27,5 % KESt geschätzt" />
        <Kpi big label="Prognose-Genauigkeit" value={k.abgleich_abweichung} format={(x) => `± ${x.toFixed(1).replace(".", ",")} %`}
          delay={0.15} sub={<span className="text-ink2">Abgleich an {k.abgleich_anzahl} echten Zahlungen</span>}
          hint="Wie genau die Yahoo-Daten deine tatsächlich erhaltenen Dividenden nachrechnen (Median)" />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2" delay={0.1}
          title={`Dividenden ${kumuliert ? "kumuliert" : `pro ${{ monat: "Monat", quartal: "Quartal", jahr: "Jahr" }[gruppe]}`} (netto)`}
          right={
            <div className="flex flex-wrap gap-2">
              <Segmented size="sm" value={gruppe} onChange={setGruppe}
                options={[{ value: "monat", label: "Monat" }, { value: "quartal", label: "Quartal" }, { value: "jahr", label: "Jahr" }]} />
              <Segmented size="sm" value={kumuliert ? "kum" : "einzeln"} onChange={(v) => setKumuliert(v === "kum")}
                options={[{ value: "einzeln", label: "pro Zeitraum" }, { value: "kum", label: "kumuliert" }]} />
            </div>
          }>
          <div className="h-[280px]">
            <ResponsiveContainer>
              {kumuliert ? (
                <AreaChart data={reihe} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="fillDiv" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={colors.s1} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={colors.s1} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke={colors.line} />
                  <XAxis dataKey="label" axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={16} />
                  <YAxis tickFormatter={eurAchse} axisLine={false} tickLine={false} width={64} />
                  <Tooltip cursor={{ stroke: colors.axis }} content={<ChartTooltip fmt={(v) => eur(v)} />} />
                  <Area type="stepAfter" dataKey="wert" name="Kumuliert" stroke={colors.s1} strokeWidth={2} fill="url(#fillDiv)"
                    animationDuration={800} />
                </AreaChart>
              ) : (
                <BarChart data={reihe} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={colors.line} />
                  <XAxis dataKey="label" axisLine={{ stroke: colors.axis }} tickLine={false} minTickGap={12} />
                  <YAxis tickFormatter={eurAchse} axisLine={false} tickLine={false} width={64} />
                  <Tooltip cursor={{ fill: colors.line, opacity: 0.4 }} content={<ChartTooltip fmt={(v) => eur(v)} />} />
                  <Bar dataKey="wert" name="Netto" fill={colors.s1} radius={[4, 4, 0, 0]} maxBarSize={44} animationDuration={800} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Nach Wertpapier" delay={0.15}>
          {proTitel.length === 0 ? <p className="text-sm text-muted">Keine Dividenden im Zeitraum.</p> : (
            <div className="space-y-3">
              {proTitel.map((t, i) => (
                <div key={t.isin ?? i}>
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="truncate">{t.name ?? t.isin}</span>
                    <span className="tnum shrink-0 font-medium">{eur(t.netto)}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line/60">
                    <motion.div className="h-full rounded-full" style={{ background: colors.s1 }}
                      initial={{ width: 0 }} animate={{ width: `${(t.netto / maxTitel) * 100}%` }}
                      transition={{ duration: 0.7, delay: 0.1 + i * 0.05 }} />
                  </div>
                  <div className="mt-0.5 text-xs text-muted">{t.anzahl} Zahlung{t.anzahl === 1 ? "" : "en"}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Dividendenkalender" delay={0.2}
        right={jahre.length > 1 && (
          <Segmented size="sm" value={String(aktivesJahr)} onChange={(v) => setJahr(Number(v))}
            options={jahre.map((j) => ({ value: String(j), label: String(j) }))} />
        )}>
        <Kalender eintraege={data.kalender.filter((e) => Number(e.d.slice(0, 4)) === aktivesJahr)} jahr={aktivesJahr}
          colors={colors} />
        <div className="mt-4 flex flex-wrap gap-4 text-[13px] text-ink2">
          <span className="inline-flex items-center gap-1.5"><CheckCircle2 size={14} style={{ color: colors.s1 }} /> erhalten (netto laut Konto)</span>
          <span className="inline-flex items-center gap-1.5"><CalendarClock size={14} className="text-muted" /> erwartet (Prognose, netto geschätzt)</span>
        </div>
        <Hinweis>Erwartete Zahlungen: Ausschüttungen der letzten 12 Monate je Stück (Yahoo Finance) um ein Jahr
          fortgeschrieben, mal Stückzahl am {datum(data.bis)}; Zahltag aus deinem bisherigen Abstand zwischen Ex-Tag
          und Gutschrift. Fremdwährungen zum letzten Wechselkurs.</Hinweis>
      </Card>
    </div>
  );
}

function Kalender({ eintraege, jahr, colors }: { eintraege: KalenderEintrag[]; jahr: number; colors: Colors }) {
  const proMonat = MONATE.map((_, i) => eintraege.filter((e) => Number(e.d.slice(5, 7)) === i + 1));
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {proMonat.map((liste, i) => {
        const summe = liste.reduce((s, e) => s + e.netto, 0);
        const nurPrognose = liste.length > 0 && liste.every((e) => e.status === "erwartet");
        return (
          <motion.div key={`${jahr}-${i}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03 }}
            className={cx("min-h-[112px] rounded-xl border p-3",
              liste.length ? "border-line bg-page" : "border-dashed border-line/70")}>
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] font-medium text-ink2">{MONATE[i]}</span>
              {liste.length > 0 && (
                <span className={cx("tnum text-sm font-semibold", nurPrognose ? "text-ink2" : "text-ink")}>
                  {nurPrognose && "≈ "}{eur(summe)}
                </span>
              )}
            </div>
            <ul className="mt-2 space-y-1.5">
              {liste.map((e, j) => (
                <li key={j} className="flex items-start justify-between gap-2 text-[13px]"
                  title={e.status === "erwartet"
                    ? `Prognose · Ex-Tag ${datum(e.ex)} · ${e.stueck} Stk. × ${eur(e.je_stueck)} brutto${e.quelle ? ` · ${e.quelle}` : ""}`
                    : `Gutschrift ${datum(e.d)} · brutto ≈ ${eur(e.brutto)}`}>
                  <span className="flex min-w-0 items-center gap-1.5">
                    {e.status === "erhalten"
                      ? <CheckCircle2 size={13} className="shrink-0" style={{ color: colors.s1 }} />
                      : <CalendarClock size={13} className="shrink-0 text-muted" />}
                    <span className={cx("truncate", e.status === "erwartet" && "text-ink2")}>{e.name ?? e.isin}</span>
                  </span>
                  <span className={cx("tnum shrink-0", e.status === "erwartet" ? "text-muted" : "text-ink")}>{eur(e.netto)}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        );
      })}
    </div>
  );
}
