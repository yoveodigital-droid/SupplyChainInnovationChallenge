import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ForecastPoint, Observation, RiskLevel } from "../api/types";
import { ACCENT, RISK_COLOR, fmtDate } from "../lib/format";

const AXIS = { stroke: "#8A8C99", fontSize: 11 } as const;
const GRID = "#E2DCD1";

const tooltipStyle = {
  contentStyle: {
    borderRadius: 10,
    border: "1px solid #E2DCD1",
    background: "#FFFDF8",
    fontSize: 12,
    boxShadow: "0 8px 24px -12px rgba(23,24,29,0.3)",
  },
  labelStyle: { fontWeight: 600, color: "#17181D", marginBottom: 2 },
} as const;

/* -------------------------------------------------------------------------- */

export function DelayDistributionChart({
  bins,
  expected,
  height = 150,
}: {
  bins: { days: number; probability: number; plus?: boolean }[];
  expected: number;
  height?: number;
}) {
  const data = bins.map((b) => ({
    ...b,
    pct: b.probability * 100,
    label: b.plus ? `${b.days}+` : `${b.days}`,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 14, right: 6, bottom: 0, left: -6 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tickLine={false} axisLine={false} {...AXIS} />
        <YAxis tickLine={false} axisLine={false} unit="%" {...AXIS} width={38} />
        <Tooltip
          {...tooltipStyle}
          formatter={(v: number) => [`${v.toFixed(1)}%`, "Chance"]}
          labelFormatter={(l: string) => `${l} day${l === "1" ? "" : "s"} late`}
        />
        <ReferenceLine
          x={String(Math.round(expected))}
          stroke={ACCENT}
          strokeDasharray="3 3"
          label={{ value: "expected", fill: ACCENT, fontSize: 10, position: "top" }}
        />
        <Bar dataKey="pct" fill={ACCENT} radius={[3, 3, 0, 0]} maxBarSize={26} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------------- */

interface CongestionSeriesPoint {
  day: string;
  observed?: number;
  forecast?: number;
  band?: [number, number];
  confidence?: number;
}

export function CongestionChart({
  history,
  forecast,
  threshold,
  height = 240,
}: {
  history: Observation[];
  forecast: ForecastPoint[];
  threshold: number;
  height?: number;
}) {
  const data: CongestionSeriesPoint[] = [
    ...history.map((h) => ({ day: h.day, observed: h.congestion_index })),
    ...forecast.map((f) => ({
      day: f.day,
      forecast: f.congestion,
      band: [f.congestion_low, f.congestion_high] as [number, number],
      confidence: f.confidence,
    })),
  ];
  // Join the two series so the line does not break at "today".
  const lastObserved = history.at(-1);
  if (lastObserved) {
    const idx = data.findIndex((d) => d.day === lastObserved.day);
    if (idx >= 0) {
      data[idx] = {
        ...data[idx],
        forecast: lastObserved.congestion_index,
        band: [lastObserved.congestion_index, lastObserved.congestion_index],
      };
    }
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -4 }}>
        <defs>
          <linearGradient id="pp-band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.22} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0.06} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="day"
          tickFormatter={fmtDate}
          tickLine={false}
          axisLine={false}
          minTickGap={28}
          {...AXIS}
        />
        <YAxis
          domain={[0, 100]}
          ticks={[0, 25, 50, 75, 100]}
          tickLine={false}
          axisLine={false}
          width={34}
          {...AXIS}
        />
        <Tooltip
          {...tooltipStyle}
          labelFormatter={(l: string) => fmtDate(l)}
          formatter={(value: number | number[], name: string) => {
            if (name === "band" && Array.isArray(value)) {
              return [`${value[0].toFixed(0)} – ${value[1].toFixed(0)}`, "80% range"];
            }
            return [
              typeof value === "number" ? value.toFixed(1) : String(value),
              name === "observed" ? "Observed" : "Forecast",
            ];
          }}
        />
        <ReferenceLine
          y={threshold}
          stroke={RISK_COLOR.red}
          strokeDasharray="4 4"
          label={{
            value: `disruption threshold ${threshold.toFixed(0)}`,
            fill: RISK_COLOR.red,
            fontSize: 10,
            position: "insideTopRight",
          }}
        />
        {lastObserved && (
          <ReferenceLine
            x={lastObserved.day}
            stroke="#8A8C99"
            label={{ value: "today", fill: "#8A8C99", fontSize: 10, position: "insideTopLeft" }}
          />
        )}
        <Area
          type="monotone"
          dataKey="band"
          stroke="none"
          fill="url(#pp-band)"
          isAnimationActive={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="observed"
          stroke="#4A4C57"
          strokeWidth={1.8}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="forecast"
          stroke={ACCENT}
          strokeWidth={2.4}
          strokeDasharray="5 4"
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------------- */

export function ArrivalsChart({
  forecast,
  threshold,
  height = 160,
}: {
  forecast: ForecastPoint[];
  threshold: number;
  height?: number;
}) {
  const data = forecast.map((f) => ({
    day: f.day,
    arrivals: f.expected_arrivals,
    over: f.congestion >= threshold,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -14 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="day"
          tickFormatter={fmtDate}
          tickLine={false}
          axisLine={false}
          minTickGap={18}
          {...AXIS}
        />
        <YAxis tickLine={false} axisLine={false} width={34} allowDecimals={false} {...AXIS} />
        <Tooltip
          {...tooltipStyle}
          labelFormatter={(l: string) => fmtDate(l)}
          formatter={(v: number) => [v.toFixed(1), "Expected arrivals"]}
        />
        <Bar dataKey="arrivals" radius={[3, 3, 0, 0]} maxBarSize={22}>
          {data.map((d) => (
            <Cell key={d.day} fill={d.over ? RISK_COLOR.red : ACCENT} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* -------------------------------------------------------------------------- */

export function SpoilageGauge({
  probability,
  band,
  shelfLifeDays,
  transitDays,
}: {
  probability: number;
  band: RiskLevel;
  shelfLifeDays: number;
  transitDays: number;
}) {
  const pct = Math.round(probability * 100);
  const radius = 52;
  const circumference = Math.PI * radius;
  const filled = circumference * Math.min(probability, 1);
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 130 74" className="h-[74px] w-[130px] shrink-0" role="img"
           aria-label={`Spoilage risk ${pct} percent`}>
        <path
          d="M 13 66 A 52 52 0 0 1 117 66"
          fill="none"
          stroke="#EFEAE1"
          strokeWidth="12"
          strokeLinecap="round"
        />
        <path
          d="M 13 66 A 52 52 0 0 1 117 66"
          fill="none"
          stroke={RISK_COLOR[band]}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
        />
        <text
          x="65"
          y="60"
          textAnchor="middle"
          fontSize="24"
          fontWeight="700"
          fill={RISK_COLOR[band]}
          className="tnum"
        >
          {pct}%
        </text>
      </svg>
      <div className="min-w-0 text-[12px] leading-snug text-ink-soft">
        <div className="label mb-1">Spoilage risk</div>
        <p>
          {shelfLifeDays}-day shelf life against a {transitDays}-day scheduled transit leaves{" "}
          <strong className="tnum text-ink">{shelfLifeDays - transitDays} days</strong> of slack.
        </p>
      </div>
    </div>
  );
}
