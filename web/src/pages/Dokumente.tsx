import { AnimatePresence, motion } from "framer-motion";
import { Download, Eye, FileSpreadsheet, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, rohUrl } from "../api";
import { cx, datum, useLoad } from "../lib";
import { Card, Hinweis, Segmented } from "../ui";
import { SuchFeld } from "./Positionen";

const groesse = (b: number) => (b < 1024 ? `${b} B` : b < 1024 * 1024 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`)
  .replace(".", ",");

export default function Dokumente() {
  const { data, error } = useLoad(api.rohdaten, []);
  const [art, setArt] = useState<"csv" | "pdf">("csv");
  const [suche, setSuche] = useState("");
  const [vorschau, setVorschau] = useState<string | null>(null);

  if (error) return <Card>Fehler: {error}</Card>;
  if (!data) return null;
  const s = suche.toLowerCase();
  const csv = data.csv.filter((f) => !s || f.name.toLowerCase().includes(s) || f.quelle.includes(s));
  const pdf = data.pdf.filter((f) => !s || f.name.toLowerCase().includes(s) || f.datum.includes(s));

  return (
    <div className="space-y-5">
      <Card title="Rohdaten" right={
        <div className="flex flex-wrap items-center gap-2">
          <Segmented size="sm" value={art} onChange={setArt}
            options={[{ value: "csv", label: `Umsatz-Exporte (${data.csv.length})` }, { value: "pdf", label: `PDFs (${data.pdf.length})` }]} />
          <SuchFeld value={suche} onChange={setSuche} />
        </div>
      }>
        {art === "csv" ? (
          csv.length === 0 ? <p className="text-sm text-muted">Noch keine Exporte geladen.</p> : (
            <ul className="divide-y divide-line/70">
              {csv.map((f, i) => (
                <motion.li key={f.pfad} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}
                  className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex min-w-0 items-center gap-3">
                    <FileSpreadsheet size={18} className="shrink-0 text-muted" />
                    <span className="min-w-0">
                      <span className="font-medium">{f.quelle === "konto" ? "Kontoumsätze" : "Depotumsätze"}</span>
                      <span className="ml-2 text-ink2">{f.von ? `${datum(f.von)} – ${datum(f.bis)}` : f.name}</span>
                      <span className="block text-xs text-muted">{f.name} · {groesse(f.groesse)}</span>
                    </span>
                  </span>
                  <span className="flex gap-2">
                    <Knopf onClick={() => setVorschau(f.pfad)} icon={<Eye size={15} />}>Ansehen</Knopf>
                    <Knopf href={rohUrl(f.pfad, true)} icon={<Download size={15} />}>Download</Knopf>
                  </span>
                </motion.li>
              ))}
            </ul>
          )
        ) : (
          pdf.length === 0 ? (
            <p className="text-sm text-muted">Keine PDFs vorhanden. Postfach-PDFs werden nur auf Wunsch geladen (Daten → „Postfach-PDFs“).</p>
          ) : (
            <ul className="divide-y divide-line/70">
              {pdf.map((f, i) => (
                <motion.li key={f.pfad} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}
                  className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="flex min-w-0 items-center gap-3">
                    <FileText size={18} className="shrink-0 text-muted" />
                    <span className="min-w-0">
                      <span className="font-medium">{f.name}</span>
                      <span className="block text-xs text-muted">{datum(f.datum)} · {groesse(f.groesse)}</span>
                    </span>
                  </span>
                  <span className="flex gap-2">
                    <Knopf href={rohUrl(f.pfad)} neuesFenster icon={<Eye size={15} />}>Öffnen</Knopf>
                    <Knopf href={rohUrl(f.pfad, true)} icon={<Download size={15} />}>Download</Knopf>
                  </span>
                </motion.li>
              ))}
            </ul>
          )
        )}
        <Hinweis>Originaldateien so, wie sie von flatex geladen wurden – unverändert und nur lokal gespeichert.</Hinweis>
      </Card>

      <AnimatePresence>{vorschau && <Vorschau pfad={vorschau} onClose={() => setVorschau(null)} />}</AnimatePresence>
    </div>
  );
}

function Knopf({ children, icon, onClick, href, neuesFenster }: {
  children: React.ReactNode; icon: React.ReactNode; onClick?: () => void; href?: string; neuesFenster?: boolean;
}) {
  const cls = "inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] text-ink2 hover:text-ink";
  return href
    ? <a href={href} className={cls} target={neuesFenster ? "_blank" : undefined} rel="noreferrer">{icon}{children}</a>
    : <button onClick={onClick} className={cls}>{icon}{children}</button>;
}

function Vorschau({ pfad, onClose }: { pfad: string; onClose: () => void }) {
  const { data, error } = useLoad(() => api.rohVorschau(pfad), [pfad]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" onClick={onClose}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.div role="dialog" aria-modal="true" aria-label="Vorschau"
        className="fixed inset-4 z-50 flex flex-col overflow-hidden rounded-xl2 border border-line bg-page shadow-2xl sm:inset-10"
        initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }}>
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <div className="min-w-0 truncate font-medium">{pfad.split("/").pop()}
            {data?.gesamt != null && <span className="ml-2 text-sm text-muted">{data.gesamt} Zeilen</span>}</div>
          <div className="flex gap-2">
            <Knopf href={rohUrl(pfad, true)} icon={<Download size={15} />}>Download</Knopf>
            <button onClick={onClose} aria-label="Schließen"
              className="grid h-8 w-8 place-items-center rounded-full border border-line bg-surface text-ink2 hover:text-ink"><X size={16} /></button>
          </div>
        </header>
        <div className="flex-1 overflow-auto">
          {error && <p className="p-5 text-bad">{error}</p>}
          {data?.hinweis && <p className="p-5 text-muted">{data.hinweis}</p>}
          {data && !data.hinweis && (
            <table className="min-w-full text-[13px]">
              <thead className="sticky top-0 bg-surface text-left text-ink2">
                <tr>{data.kopf.map((k, i) => <th key={i} className="whitespace-nowrap border-b border-line px-3 py-2 font-medium">{k || "—"}</th>)}</tr>
              </thead>
              <tbody>
                {data.zeilen.map((z, i) => (
                  <tr key={i} className={cx("border-b border-line/60", i % 2 === 1 && "bg-surface/50")}>
                    {z.map((c, j) => <td key={j} className="tnum whitespace-nowrap px-3 py-1.5">{c}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </motion.div>
    </>
  );
}
