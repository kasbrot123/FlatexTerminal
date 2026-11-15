import { motion } from "framer-motion";
import { FileCheck2, Info } from "lucide-react";
import { useState } from "react";
import { api, Meta, PdfStatus } from "../api";
import { Colors, cx, datum, eur, eurSigned, useLoad } from "../lib";
import { Badge, Card, Delta, Hinweis, Kpi, Segmented } from "../ui";

export default function Steuern({ meta, colors }: { meta: Meta; colors: Colors }) {
  const { data, error } = useLoad(() => api.taxes(meta.bis_default), [meta.bis_default]);
  const [jahr, setJahr] = useState<number | null>(null);

  if (error) return <Card>Fehler: {error}</Card>;
  if (!data) return null;
  if (!data.jahre.length) return <Card>Noch keine steuerlich relevanten Vorgänge.</Card>;
  const j = data.jahre.find((x) => x.jahr === jahr) ?? data.jahre[data.jahre.length - 1];
  const diff = j.kest_bezahlt - j.kest_soll;
  const vk = data.verkaeufe.filter((v) => v.d.startsWith(String(j.jahr)));
  const er = data.ertraege.filter((e) => e.d.startsWith(String(j.jahr)));

  const posten = [
    { label: "Kursgewinne", wert: j.gewinne },
    { label: "Kursverluste", wert: j.verluste },
    { label: "Dividenden & Ausschüttungen (brutto)", wert: j.dividenden },
    { label: "Ausschüttungsgleiche Erträge", wert: j.age },
    { label: "Zinsen (25 %)", wert: j.zinsen },
  ].filter((p) => Math.abs(p.wert) > 0.005);
  const maxAbs = Math.max(...posten.map((p) => Math.abs(p.wert)), 1);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        {data.jahre.length > 1 && (
          <Segmented value={String(j.jahr)} onChange={(v) => setJahr(Number(v))}
            options={data.jahre.map((x) => ({ value: String(x.jahr), label: String(x.jahr) }))} />
        )}
        <Badge>{data.pdf_status.verkaeufe_mit_pdf + data.pdf_status.ertraege_mit_pdf > 0
          ? "Grundlage: Abrechnungs-PDFs + Kontoumsätze" : "Grundlage: Kontoumsätze (teils geschätzt)"}</Badge>
      </div>

      <PdfGrundlage s={data.pdf_status} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi big label={`Steuerpflichtig ${j.jahr}`} value={j.bemessung} format={(x) => eur(x)}
          hint="Gewinne + Dividenden + ausschüttungsgleiche Erträge − Verluste (Verlustausgleich im selben Jahr)" />
        <Kpi big label={`KESt rechnerisch (${new Intl.NumberFormat("de-AT", { maximumFractionDigits: 2 }).format(data.satz)} %)`} value={j.kest_soll}
          format={(x) => eur(x)} delay={0.05} />
        <Kpi big label="KESt abgezogen" value={j.kest_bezahlt} format={(x) => eur(x)} delay={0.1}
          sub={j.davon_geschaetzt > 0 ? <span className="text-ink2">davon {eur(j.davon_geschaetzt)} geschätzt</span> : undefined} />
        <Kpi big label={diff > 0 ? "Zu viel abgezogen" : "Noch offen"} value={Math.abs(diff)} format={(x) => eur(x)} delay={0.15}
          sub={<span className="text-ink2">{diff > 0
            ? "flatex gleicht Verluste meist automatisch aus"
            : "wird ggf. bei weiteren Vorgängen fällig"}</span>}
          hint="Differenz zwischen abgezogener und rechnerischer KESt – bei Schätzungen nur ein Richtwert" />
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Card className="lg:col-span-3" title={`Zusammensetzung ${j.jahr}`} delay={0.1}>
          <div className="space-y-3.5">
            {posten.map((p, i) => (
              <div key={p.label}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="text-ink2">{p.label}</span>
                  <span className="tnum font-medium">{eurSigned(p.wert)}</span>
                </div>
                <div className="relative mt-1.5 h-2 rounded-full bg-line/50">
                  <span className="absolute left-1/2 top-[-3px] h-[14px] w-px bg-axis" style={{ background: colors.axis }} />
                  <motion.div className="absolute top-0 h-2 rounded-full"
                    style={{ background: p.wert >= 0 ? colors.s1 : colors.bad, [p.wert >= 0 ? "left" : "right"]: "50%" }}
                    initial={{ width: 0 }} animate={{ width: `${(Math.abs(p.wert) / maxAbs) * 50}%` }}
                    transition={{ duration: 0.7, delay: i * 0.06 }} />
                </div>
              </div>
            ))}
            <div className="flex items-baseline justify-between border-t border-line pt-3 text-sm">
              <span className="font-medium">Bemessungsgrundlage</span>
              <span className="tnum font-semibold">{eur(j.bemessung)}</span>
            </div>
            {j.quellensteuer > 0 && (
              <div className="flex justify-between text-sm text-ink2"><span>Quellensteuer (laut PDF)</span>
                <span className="tnum">{eur(j.quellensteuer)}</span></div>
            )}
          </div>
          {j.hinweise.length > 0 && (
            <ul className="mt-4 space-y-1.5">
              {j.hinweise.map((h) => (
                <li key={h} className="flex gap-2 text-[13px] text-ink2"><Info size={14} className="mt-0.5 shrink-0 text-muted" />{h}</li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="lg:col-span-2" title="Offene Positionen" delay={0.15}>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[13px] text-ink2">Latente KESt bei Verkauf</div>
              <div className="tnum mt-0.5 text-xl font-semibold">{eur(data.kest_latent)}</div>
            </div>
            <div>
              <div className="text-[13px] text-ink2">Nicht realisierte Verluste</div>
              <div className="tnum mt-0.5 text-xl font-semibold">{eurSigned(data.verlust_offen)}</div>
            </div>
          </div>
          <div className="mt-4 max-h-[300px] space-y-2 overflow-y-auto pr-1">
            {data.offen.map((o) => (
              <div key={o.isin} className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate">{o.name}</span>
                <Delta value={o.gewinn} className="shrink-0" />
              </div>
            ))}
          </div>
          <Hinweis>Steuerliche Anschaffungskosten ohne Gebühren, inkl. ausschüttungsgleicher Erträge. Verluste lassen
            sich im selben Jahr mit Gewinnen verrechnen.</Hinweis>
        </Card>
      </div>

      <Card title={`Verkäufe ${j.jahr}`} delay={0.2}>
        {vk.length === 0 ? <p className="text-sm text-muted">Keine Verkäufe.</p> : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b border-line text-left text-[13px] text-ink2">
                <tr>
                  <th className="px-3 py-2.5 font-medium">Datum</th><th className="px-3 py-2.5 font-medium">Wertpapier</th>
                  <th className="px-3 py-2.5 text-right font-medium">Erlös</th>
                  <th className="px-3 py-2.5 text-right font-medium">Anschaffung</th>
                  <th className="px-3 py-2.5 text-right font-medium">Gewinn</th>
                  <th className="px-3 py-2.5 text-right font-medium">KESt</th>
                  <th className="px-3 py-2.5 font-medium">Quelle</th>
                </tr>
              </thead>
              <tbody>
                {vk.map((v, i) => (
                  <tr key={i} className="border-b border-line/70 last:border-0">
                    <td className="tnum px-3 py-2.5 text-ink2">{datum(v.d)}</td>
                    <td className="px-3 py-2.5">{v.name}</td>
                    <td className="tnum px-3 py-2.5 text-right">{eur(v.kurswert)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{eur(v.anschaffung)}</td>
                    <td className="px-3 py-2.5 text-right"><Delta value={v.gewinn} /></td>
                    <td className="tnum px-3 py-2.5 text-right">
                      {v.kest_bezahlt != null ? eur(v.kest_bezahlt) : v.kest_geschaetzt != null ? `≈ ${eur(v.kest_geschaetzt)}` : "–"}
                    </td>
                    <td className="px-3 py-2.5"><QuelleBadge q={v.quelle} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Erträge ${j.jahr}`} delay={0.25}>
        {er.length === 0 ? <p className="text-sm text-muted">Keine Erträge.</p> : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead className="border-b border-line text-left text-[13px] text-ink2">
                <tr>
                  <th className="px-3 py-2.5 font-medium">Datum</th><th className="px-3 py-2.5 font-medium">Art</th>
                  <th className="px-3 py-2.5 font-medium">Wertpapier</th>
                  <th className="px-3 py-2.5 text-right font-medium">Brutto</th>
                  <th className="px-3 py-2.5 text-right font-medium">Steuer</th>
                  <th className="px-3 py-2.5 text-right font-medium">Netto</th>
                  <th className="px-3 py-2.5 font-medium">Quelle</th>
                </tr>
              </thead>
              <tbody>
                {er.map((e, i) => (
                  <tr key={i} className="border-b border-line/70 last:border-0">
                    <td className="tnum px-3 py-2.5 text-ink2">{datum(e.d)}</td>
                    <td className="px-3 py-2.5">{e.art}</td>
                    <td className="px-3 py-2.5">{e.name ?? "–"}</td>
                    <td className="tnum px-3 py-2.5 text-right">{eur(e.brutto)}</td>
                    <td className="tnum px-3 py-2.5 text-right text-ink2">{eur(e.steuer)}</td>
                    <td className="tnum px-3 py-2.5 text-right">{e.art.startsWith("Ausschüttungsgleich") ? "–" : eur(e.netto)}</td>
                    <td className="px-3 py-2.5"><QuelleBadge q={e.quelle} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Hinweis>Ausschüttungsgleiche Erträge thesaurierender Fonds fließen nicht aufs Konto, werden aber besteuert –
          die KESt darauf bucht flatex direkt ab.</Hinweis>
      </Card>

      <p className={cx("text-[12px] leading-relaxed text-muted")}>
        Vereinfachte Berechnung nach österreichischem Recht (KESt 27,5 %, Zinsen 25 %, Verlustausgleich innerhalb des
        Kalenderjahres, Gebühren nicht absetzbar). Keine Steuerberatung – maßgeblich sind die Steuerdokumente von flatex.
      </p>
    </div>
  );
}

/** Zeigt, wie viele Steuerwerte exakt aus PDFs kommen und warum der Rest geschätzt ist. */
function PdfGrundlage({ s }: { s: PdfStatus }) {
  const alleExakt = s.verkaeufe === s.verkaeufe_mit_pdf && s.ertraege === s.ertraege_mit_pdf;
  if (s.dokumente === 0 && !s.verkaeufe) return null;
  return (
    <Card delay={0.05}>
      <div className="flex items-start gap-3 text-sm">
        <FileCheck2 size={20} className={cx("mt-0.5 shrink-0", alleExakt ? "text-good" : "text-muted")} />
        <div className="space-y-1.5">
          <div className="font-medium">
            {alleExakt ? "Alle Steuerwerte exakt aus Abrechnungen" : "Teilweise geschätzt"}
          </div>
          <div className="text-ink2">
            Verkäufe mit Abrechnung: <b className="tnum text-ink">{s.verkaeufe_mit_pdf} von {s.verkaeufe}</b> ·
            Dividenden/Ausschüttungen mit Abrechnung: <b className="tnum text-ink">{s.ertraege_mit_pdf} von {s.ertraege}</b>
          </div>
          <div className="text-ink2">
            {s.dokumente} PDFs im Postfach-Ordner, davon {s.gelesen} mit lesbaren Transaktionen
            {Object.keys(s.transaktionen).length > 0 && <> ({Object.entries(s.transaktionen).map(([t, n]) => `${n}× ${t}`).join(", ")})</>}.
          </div>
          {s.nicht_lesbar.length > 0 && (
            <details className="text-ink2">
              <summary className="cursor-pointer">Nicht auswertbare Dokumenttypen ({s.nicht_lesbar.reduce((a, x) => a + x.anzahl, 0)})</summary>
              <ul className="mt-1.5 list-disc pl-5">
                {s.nicht_lesbar.map((x) => <li key={x.name}>{x.anzahl}× {x.name}</li>)}
              </ul>
              <p className="mt-1.5 text-[12px] text-muted">Der PDF-Leser (flatex-pdf-cli) kennt diese Dokumentarten nicht –
                bei Kundeninformationen ist das egal, bei Abrechnungen bleibt der Wert geschätzt.</p>
            </details>
          )}
          {s.dokumente === 0 && <div className="text-muted">Keine PDFs geladen – Daten → „Postfach-PDFs“ für exakte Werte.</div>}
        </div>
      </div>
    </Card>
  );
}

function QuelleBadge({ q }: { q: string }) {
  const label = q === "PDF" ? "Abrechnung" : q === "Konto" ? "Konto" : "geschätzt";
  return <Badge>{label}</Badge>;
}
