import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3, Coins, FolderOpen, LayoutDashboard, ListOrdered, Moon, Receipt, Settings2, Sun, Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { EinstellungenPanel } from "./EinstellungenPanel";
import { cx, datum, setFarbWahl, useColors, useLoad, useTheme } from "./lib";
import { SyncButton, SyncPanel, useSyncStatus } from "./SyncPanel";
import Dividenden from "./pages/Dividenden";
import Dokumente from "./pages/Dokumente";
import Positionen from "./pages/Positionen";
import Steuern from "./pages/Steuern";
import Transaktionen from "./pages/Transaktionen";
import Uebersicht from "./pages/Uebersicht";

const TABS = [
  { id: "uebersicht", label: "Übersicht", icon: LayoutDashboard },
  { id: "positionen", label: "Positionen", icon: Wallet },
  { id: "transaktionen", label: "Transaktionen", icon: ListOrdered },
  { id: "dividenden", label: "Dividenden", icon: Coins },
  { id: "steuern", label: "Steuern", icon: Receipt },
  { id: "dokumente", label: "Dokumente", icon: FolderOpen },
] as const;
type TabId = (typeof TABS)[number]["id"];

function useHashTab(): [TabId, (t: TabId) => void] {
  const read = () => (TABS.find((t) => `#/${t.id}` === window.location.hash)?.id ?? "uebersicht") as TabId;
  const [tab, setTab] = useState<TabId>(read);
  useEffect(() => {
    const on = () => setTab(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [tab, (t) => { window.location.hash = `/${t}`; setTab(t); }];
}

export default function App() {
  const [theme, setTheme] = useTheme();
  const colors = useColors(theme);
  const [tab, setTab] = useHashTab();
  const [version, setVersion] = useState(0);            // steigt nach jedem Abruf -> alle Daten neu laden
  const [panel, setPanel] = useState(false);
  const fertig = useCallback(() => setVersion((v) => v + 1), []);
  const { status: syncStatus, neuLaden } = useSyncStatus(fertig);
  const [einstellungen, setEinstellungen] = useState(false);
  // Farbwahl muss stehen, bevor die Seiten zeichnen
  const { data: farbEinst } = useLoad(api.einstellungen, [version]);
  if (farbEinst) setFarbWahl(farbEinst.farben);
  const { data: meta, error } = useLoad(api.meta, [version]);

  return (
    <div className="glow min-h-screen">
      <header className="theme-fade sticky top-0 z-30 border-b border-line bg-page/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <motion.div initial={{ rotate: -20, scale: 0.6, opacity: 0 }} animate={{ rotate: 0, scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-white shadow-card">
              <BarChart3 size={19} strokeWidth={2.4} />
            </motion.div>
            <div className="leading-tight">
              <div className="text-[15px] font-semibold">Flatex Terminal</div>
              <div className="text-xs text-muted">
                {meta ? `Depot seit ${datum(meta.depot_start)} · Stand ${datum(meta.bis_default)}` : " "}
              </div>
            </div>
          </div>
          <nav className="ml-auto hidden items-center gap-1 lg:flex">
            {TABS.map((t) => (
              <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)} icon={<t.icon size={16} />}>
                {t.label}
              </TabButton>
            ))}
          </nav>
          <div className="ml-auto lg:ml-2">
            <SyncButton status={syncStatus} onClick={() => setPanel(true)} />
          </div>
          <button onClick={() => setEinstellungen(true)} aria-label="Einstellungen"
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 transition hover:text-ink">
            <Settings2 size={17} />
          </button>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface text-ink2 transition hover:text-ink"
            aria-label={theme === "dark" ? "Hellen Modus aktivieren" : "Dunklen Modus aktivieren"}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={theme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }}>
                {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
              </motion.span>
            </AnimatePresence>
          </button>
        </div>
        {/* Reiter auf schmalen Bildschirmen */}
        <nav className="flex gap-1 overflow-x-auto px-3 pb-2 lg:hidden">
          {TABS.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)} icon={<t.icon size={15} />}>
              {t.label}
            </TabButton>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {error && (
          <div className="rounded-xl2 border border-line bg-surface p-5 text-sm">
            Das Backend ist nicht erreichbar ({error}). Bitte mit <code>python -m flatex web</code> starten.
          </div>
        )}
        {meta && !meta.hat_daten && <Willkommen onStart={() => setPanel(true)} />}
        {meta?.hat_daten && (
          <AnimatePresence mode="wait">
            <motion.div key={`${tab}-${version}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25, ease: "easeOut" }}>
              {tab === "uebersicht" && <Uebersicht meta={meta} colors={colors} onOpenPositions={() => setTab("positionen")} />}
              {tab === "positionen" && <Positionen meta={meta} colors={colors} />}
              {tab === "transaktionen" && <Transaktionen meta={meta} colors={colors} />}
              {tab === "dividenden" && <Dividenden meta={meta} colors={colors} />}
              {tab === "steuern" && <Steuern meta={meta} colors={colors} />}
              {tab === "dokumente" && <Dokumente />}
            </motion.div>
          </AnimatePresence>
        )}
      </main>

      <AnimatePresence>
        {panel && <SyncPanel status={syncStatus} onClose={() => setPanel(false)} neuLaden={neuLaden} />}
      </AnimatePresence>
      <AnimatePresence>
        {einstellungen && <EinstellungenPanel colors={colors} onClose={() => setEinstellungen(false)} onGespeichert={fertig} />}
      </AnimatePresence>
    </div>
  );
}

function Willkommen({ onStart }: { onStart: () => void }) {
  const schritte = [
    ["Zugang hinterlegen", "Kundennummer und Passwort – bleiben lokal auf diesem Rechner."],
    ["Daten abrufen", "Konto- und Depotumsätze seit Depotstart, dazu Kurse und Dividenden."],
    ["Auswerten", "Vermögen, Performance, Positionen, Dividenden und Steuern."],
  ];
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="mx-auto mt-10 max-w-2xl rounded-xl2 border border-line bg-surface p-8 text-center shadow-card">
      <motion.div initial={{ scale: 0.6, rotate: -15 }} animate={{ scale: 1, rotate: 0 }}
        transition={{ type: "spring", stiffness: 240, damping: 16 }}
        className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-accent text-white shadow-card">
        <BarChart3 size={28} />
      </motion.div>
      <h1 className="mt-5 text-2xl font-semibold">Willkommen im Flatex Terminal</h1>
      <p className="mt-2 text-ink2">Noch keine Daten vorhanden. In drei Schritten zur Auswertung deines Depots:</p>
      <ol className="mt-6 space-y-3 text-left">
        {schritte.map(([t, d], i) => (
          <motion.li key={t} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.08 }}
            className="flex gap-3 rounded-xl border border-line bg-page p-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent/10 text-sm font-semibold text-accent">{i + 1}</span>
            <span><span className="font-medium">{t}</span><span className="block text-sm text-ink2">{d}</span></span>
          </motion.li>
        ))}
      </ol>
      <motion.button whileTap={{ scale: 0.97 }} onClick={onStart}
        className="mt-6 inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-semibold text-white shadow-card hover:brightness-110">
        Los geht's
      </motion.button>
      <p className="mt-4 text-[13px] text-muted">Tipp: Den Depotstart in der config.toml (oder FLATEX_DEPOT_START) setzen – das spart Anfragen.</p>
    </motion.div>
  );
}

function TabButton({ active, onClick, icon, children }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <button onClick={onClick} aria-current={active ? "page" : undefined}
      className={cx("relative flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-medium transition-colors",
        active ? "text-ink" : "text-ink2 hover:text-ink")}>
      {active && (
        <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-full border border-line bg-surface shadow-card"
          transition={{ type: "spring", stiffness: 420, damping: 34 }} />
      )}
      <span className="relative flex items-center gap-1.5">{icon}{children}</span>
    </button>
  );
}
