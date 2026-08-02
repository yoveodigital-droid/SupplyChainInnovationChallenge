import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import type { Contribution, RiskLevel } from "../api/types";
import { RISK_COLOR, RISK_SOFT, RISK_WORD, fmtPct } from "../lib/format";

/* --------------------------------------------------------------------------
 * Risk
 * ----------------------------------------------------------------------- */

export function RiskDot({ level, size = 8 }: { level: RiskLevel; size?: number }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: RISK_COLOR[level] }}
      aria-hidden
    />
  );
}

export function RiskBadge({
  level,
  score,
  label,
  compact = false,
}: {
  level: RiskLevel;
  /** 0–1. Always shown: a colour alone is not a number. */
  score?: number;
  label?: string;
  compact?: boolean;
}) {
  return (
    <span
      className={`chip ${compact ? "" : "px-2.5 py-1"}`}
      style={{ background: RISK_SOFT[level], color: RISK_COLOR[level] }}
    >
      <RiskDot level={level} size={6} />
      {label ?? RISK_WORD[level]}
      {score !== undefined && <span className="opacity-70">· {fmtPct(score)}</span>}
    </span>
  );
}

/* --------------------------------------------------------------------------
 * Confidence + "How was this predicted?"
 * ----------------------------------------------------------------------- */

export function ConfidenceMeter({ value, className = "" }: { value: number; className?: string }) {
  const pct = Math.round(value * 100);
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-paper-sunken">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-accent"
          style={{ width: `${Math.max(pct, 3)}%` }}
        />
      </span>
      <span className="tnum text-[11px] font-semibold text-ink-soft">{pct}%</span>
    </span>
  );
}

export function Explainer({
  contributions,
  confidence,
  note,
}: {
  contributions: Contribution[];
  confidence?: number;
  note?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px]
                   font-medium text-ink-soft transition hover:border-accent hover:text-accent"
      >
        <span
          className="grid h-3.5 w-3.5 place-items-center rounded-full border border-current text-[9px] font-bold"
          aria-hidden
        >
          ?
        </span>
        How was this predicted?
      </button>
      {open && (
        <div
          id={id}
          role="dialog"
          className="absolute right-0 z-40 mt-2 w-80 rounded-xl border border-line bg-paper-raised p-3.5 text-left shadow-lift"
        >
          <div className="label mb-2">What moved this forecast</div>
          <ul className="space-y-2">
            {contributions.map((c, i) => (
              <li key={`${c.feature}-${i}`} className="flex items-start gap-2.5 text-[12.5px] leading-snug">
                <span
                  className="mt-0.5 tnum shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold"
                  style={{
                    background: c.effect > 0 ? RISK_SOFT.red : RISK_SOFT.green,
                    color: c.effect > 0 ? RISK_COLOR.red : RISK_COLOR.green,
                  }}
                >
                  {c.effect > 0 ? "+" : "−"}
                  {Math.abs(c.effect).toFixed(1)}
                </span>
                <span className="text-ink-soft">{c.label}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 border-t border-line pt-2.5 text-[11px] leading-relaxed text-ink-faint">
            Figures are congestion-index points added or removed versus a typical day at this port.
            {confidence !== undefined && (
              <>
                {" "}
                Model confidence <strong className="text-ink-soft">{Math.round(confidence * 100)}%</strong>.
              </>
            )}
            {note ? ` ${note}` : ""}
          </p>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Layout helpers
 * ----------------------------------------------------------------------- */

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
  bodyClassName = "p-4",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h3 className="text-[13px] font-semibold tracking-tight text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-[11.5px] leading-snug text-ink-faint">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: RiskLevel;
}) {
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div
        className="tnum mt-1 text-[19px] font-semibold leading-none tracking-tight"
        style={tone ? { color: RISK_COLOR[tone] } : undefined}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-[11.5px] leading-snug text-ink-faint">{hint}</div>}
    </div>
  );
}

export function Skeleton({ className = "h-4 w-24" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-paper-sunken ${className}`} />;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-line px-6 py-10 text-center text-sm text-ink-faint">
      {children}
    </div>
  );
}

export function ActivityBar({ active }: { active: boolean }) {
  return (
    <div
      className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden"
      aria-hidden={!active}
    >
      <div
        className={`h-full w-1/3 bg-accent transition-opacity duration-150 ${
          active ? "opacity-100" : "opacity-0"
        }`}
        style={active ? { animation: "pp-sweep 1.1s ease-in-out infinite" } : undefined}
      />
    </div>
  );
}

/** Dim and mark a region whose contents are being replaced. */
export function Refreshing({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  return (
    <div
      aria-busy={active}
      className={active ? "opacity-45 transition-opacity duration-200" : "transition-opacity duration-200"}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-[15px] font-semibold tracking-tight">{children}</h2>
      {right}
    </div>
  );
}
