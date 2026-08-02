import type { RiskLevel } from "../api/types";

export const RISK_COLOR: Record<RiskLevel, string> = {
  green: "#0F8A54",
  amber: "#B87400",
  red: "#C42A2A",
};

export const RISK_SOFT: Record<RiskLevel, string> = {
  green: "#DCF3E7",
  amber: "#FCEFD5",
  red: "#FBE3E1",
};

export const RISK_WORD: Record<RiskLevel, string> = {
  green: "On track",
  amber: "Watch",
  red: "At risk",
};

export const ACCENT = "#5B2BD9";

export function fmtDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fmtLongDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function fmtUsd(value: number, opts: { sign?: boolean } = {}): string {
  const rounded = Math.round(value);
  const body = `$${Math.abs(rounded).toLocaleString("en-US")}`;
  if (!opts.sign) return rounded < 0 ? `−${body}` : body;
  if (rounded === 0) return `$0`;
  return `${rounded > 0 ? "+" : "−"}${body}`;
}

export function fmtPct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function fmtDays(value: number, opts: { sign?: boolean } = {}): string {
  const body = `${Math.abs(value).toFixed(1)}d`;
  if (!opts.sign) return body;
  if (Math.abs(value) < 0.05) return "0d";
  return `${value > 0 ? "+" : "−"}${body}`;
}

export function fmtTonnes(value: number, opts: { sign?: boolean } = {}): string {
  const body = `${Math.abs(value).toFixed(2)} t`;
  if (!opts.sign) return body;
  if (Math.abs(value) < 0.005) return "0 t";
  return `${value > 0 ? "+" : "−"}${body}`;
}

/** Days between two ISO dates. */
export function daysBetween(a: string, b: string): number {
  const ms = new Date(`${b}T00:00:00`).getTime() - new Date(`${a}T00:00:00`).getTime();
  return Math.round(ms / 86_400_000);
}

export const EVENT_ICON: Record<string, string> = {
  security: "⚠",
  weather: "🌊",
  labor: "⚒",
  congestion: "⛴",
  policy: "◈",
};
