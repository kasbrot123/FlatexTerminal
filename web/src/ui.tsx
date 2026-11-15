import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { ReactNode, useEffect, useId } from "react";
import { cx, eur, pct } from "./lib";

// --- Karte -------------------------------------------------------------------------------------
export function Card({ title, right, children, className, delay = 0 }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; delay?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      className={cx("theme-fade rounded-xl2 border border-line bg-surface p-5 shadow-card", className)}
    >
      {(title || right) && (
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
          {right}
        </header>
      )}
      {children}
    </motion.section>
  );
}

// --- Zahl, die sanft auf den neuen Wert läuft ----------------------------------------------------
export function AnimatedNumber({ value, format }: { value: number; format: (x: number) => string }) {
  const mv = useMotionValue(value);
  const text = useTransform(mv, (x) => format(x));
  useEffect(() => {
    const c = animate(mv, value, { duration: 0.9, ease: [0.22, 1, 0.36, 1] });
    return c.stop;
  }, [value, mv]);
  return <motion.span>{text}</motion.span>;
}

// --- Veränderung mit Pfeil (nie Farbe allein) ---------------------------------------------------
export function Delta({ value, kind = "eur", className }: { value: number | null; kind?: "eur" | "pct"; className?: string }) {
  if (value == null) return <span className="text-muted">–</span>;
  const up = value > 0.00001, down = value < -0.00001;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const txt = kind === "eur" ? `${up ? "+" : down ? "−" : ""}${eur(Math.abs(value))}` : pct(value);
  return (
    <span className={cx("inline-flex items-center gap-0.5 tnum font-medium", up ? "text-good" : down ? "text-bad" : "text-muted", className)}>
      <Icon size={15} strokeWidth={2.4} aria-hidden />
      {txt}
    </span>
  );
}

// --- Kennzahl -----------------------------------------------------------------------------------
export function Kpi({ label, value, format = (x) => eur(x), sub, hint, big, delay = 0 }: {
  label: string; value: number | null; format?: (x: number) => string; sub?: ReactNode; hint?: string;
  big?: boolean; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay }}
      className="theme-fade rounded-xl2 border border-line bg-surface px-4 py-3.5 shadow-card"
      title={hint}
    >
      <div className="text-[13px] text-ink2">{label}</div>
      <div className={cx("mt-1 font-semibold tracking-tight text-ink", big ? "text-3xl" : "text-xl")}>
        {value == null ? "–" : <AnimatedNumber value={value} format={format} />}
      </div>
      {sub && <div className="mt-1 text-[13px]">{sub}</div>}
    </motion.div>
  );
}

// --- Umschalter (Segmente) mit gleitendem Hintergrund -------------------------------------------
export function Segmented<T extends string>({ options, value, onChange, size = "md" }: {
  options: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  const id = useId();
  return (
    <div role="tablist" className="inline-flex rounded-full border border-line bg-page p-0.5">
      {options.map((o) => (
        <button
          key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={cx("relative rounded-full font-medium transition-colors",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
            value === o.value ? "text-ink" : "text-ink2 hover:text-ink")}
        >
          {value === o.value && (
            <motion.span layoutId={`seg-${id}`} className="absolute inset-0 rounded-full bg-raised shadow-card"
              transition={{ type: "spring", stiffness: 500, damping: 38 }} />
          )}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

// --- Mini-Verlauf ----------------------------------------------------------------------------
export function Sparkline({ values, color, width = 96, height = 28 }: {
  values: number[]; color: string; width?: number; height?: number;
}) {
  if (values.length < 2) return <span className="text-muted">–</span>;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * width, height - 2 - ((v - min) / span) * (height - 4)]);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} aria-hidden>
      <motion.path d={d} fill="none" stroke={color} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: "easeOut" }} />
    </svg>
  );
}

// --- Tooltip für Recharts --------------------------------------------------------------------
export function ChartTooltip({ active, payload, label, fmt, labelFmt }: {
  active?: boolean; payload?: { name: string; value: number; color: string; dataKey: string }[];
  label?: string; fmt: (v: number, key: string) => string; labelFmt?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-raised/95 px-3 py-2 text-sm shadow-card backdrop-blur">
      {label && <div className="mb-1 text-xs text-ink2">{labelFmt ? labelFmt(label) : label}</div>}
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink2">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />{p.name}
          </span>
          <span className="tnum font-medium text-ink">{fmt(p.value, p.dataKey)}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-[13px] text-ink2">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: i.color }} />{i.label}
        </span>
      ))}
    </div>
  );
}

export function Hinweis({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-[13px] leading-relaxed text-muted">{children}</p>;
}

export function Badge({ children, color }: { children: ReactNode; color?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] font-medium text-ink2">
      {color && <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />}
      {children}
    </span>
  );
}
