import { useEffect, useState } from "react";
import type { Typ } from "./api";

// --- Formatierung (de-AT) ----------------------------------------------------------------------
const nf = (min: number, max: number) =>
  new Intl.NumberFormat("de-AT", { minimumFractionDigits: min, maximumFractionDigits: max });
const n0 = nf(0, 0), n2 = nf(2, 2);

// Beträge immer mit Euro und Cent
export const eur = (x: number | null | undefined) => (x == null ? "–" : `${n2.format(x)} €`);
export const eurSigned = (x: number | null | undefined) =>
  x == null ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${n2.format(Math.abs(x))} €`;
export const pct = (x: number | null | undefined, digits = 2) =>
  x == null ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${nf(digits, digits).format(Math.abs(x))} %`;
export const num = (x: number | null | undefined, max = 4) => (x == null ? "–" : nf(0, max).format(x));

/** Achsenbeschriftung für Geldbeträge – immer mit €, große Werte als „19 Tsd. €". */
export const eurAchse = (v: number) => {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${nf(0, 1).format(v / 1_000_000)} Mio. €`;
  if (a >= 10_000) return `${n0.format(v / 1000)} Tsd. €`;
  if (a >= 1000) return `${nf(0, 1).format(v / 1000)} Tsd. €`;
  return `${nf(0, a < 10 ? 2 : 0).format(v)} €`;
};
export const datum = (iso: string | null | undefined) => {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
};
export const monatKurz = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("de-AT", { month: "short", year: "2-digit" });

// --- Datumsrechnung ----------------------------------------------------------------------------
export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const addDays = (s: string, n: number) => {
  const d = new Date(s + "T00:00:00");
  d.setDate(d.getDate() + n);
  return iso(d);
};
export const addMonths = (s: string, n: number) => {
  const d = new Date(s + "T00:00:00");
  d.setMonth(d.getMonth() + n);
  return iso(d);
};

// --- Theme ------------------------------------------------------------------------------------
export type Theme = "light" | "dark";

function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const a = document.documentElement.getAttribute("data-theme");
    return a === "dark" || a === "light" ? a : systemTheme();
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* privates Fenster */ }
  }, [theme]);
  return [theme, setTheme];
}

/** Aktuelle Farbwerte (Hex) aus den CSS-Variablen – für SVG-Diagramme. */
export function useColors(theme: Theme) {
  const read = () => {
    const cs = getComputedStyle(document.documentElement);
    const c = (n: string) => `rgb(${cs.getPropertyValue(`--${n}`).trim().split(/\s+/).join(",")})`;
    return {
      s1: c("s1"), s2: c("s2"), s3: c("s3"), s4: c("s4"), s5: c("s5"), s6: c("s6"), s7: c("s7"), s8: c("s8"),
      ink: c("ink"), ink2: c("ink2"), muted: c("muted"),
      line: c("line"), axis: c("axis"), surface: c("surface"), good: c("good"), bad: c("bad"),
    };
  };
  const [colors, setColors] = useState(read);
  useEffect(() => { setColors(read()); }, [theme]);
  return colors;
}
export type Colors = ReturnType<typeof useColors>;

// --- Farbe je Wertpapierklasse (in den Einstellungen wählbar) ------------------------------------
export type Slot = "s1" | "s2" | "s3" | "s4" | "s5" | "s6" | "s7" | "s8";
export const SLOTS: { slot: Slot; name: string }[] = [
  { slot: "s1", name: "Blau" }, { slot: "s2", name: "Orange" }, { slot: "s3", name: "Aqua" },
  { slot: "s4", name: "Gelb" }, { slot: "s5", name: "Magenta" }, { slot: "s6", name: "Grün" },
  { slot: "s7", name: "Violett" }, { slot: "s8", name: "Rot" },
];
export const STANDARD_FARBEN: Record<Typ, Slot> = { Aktie: "s8", ETF: "s1", Derivat: "s3", Sonstige: "s4" };
let farbWahl: Partial<Record<Typ, Slot>> = {};
/** Wird von der App gesetzt, sobald die Einstellungen geladen sind. */
export const setFarbWahl = (f: Partial<Record<string, string>>) => { farbWahl = f as Partial<Record<Typ, Slot>>; };
export const typSlot = (t: Typ): Slot => farbWahl[t] ?? STANDARD_FARBEN[t];

/** Farbe je Wertpapierklasse – folgt der Klasse, nie dem Rang. */
export const typFarbe = (c: Colors, t: Typ) => c[typSlot(t)];

// --- Daten laden -------------------------------------------------------------------------------
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn().then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading };
}

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
