import { api } from "../api/client";
import type { Persona } from "../api/types";
import { ArrivalsChart, CongestionChart } from "../components/charts";
import { MapPanel } from "../components/MapPanel";
import type { MapRoute } from "../components/CorridorMap";
import { Card, ConfidenceMeter, Explainer, RiskBadge, Skeleton, Stat } from "../components/primitives";
import { EVENT_ICON, RISK_COLOR, fmtDate, fmtPct } from "../lib/format";
import { useAsync, useStore } from "../state/store";

const SEVERITY_TONE = ["#8A8C99", "#8A8C99", "#B87400", "#B87400", "#C42A2A", "#C42A2A"];

export function PortView({ persona }: { persona: Persona }) {
  const { world, version } = useStore();
  const portId = persona.home_port_id ?? "SAJED";

  const pressure = useAsync(() => api.pressure(portId, 14, 60), [portId, version]);
  const data = pressure.data;

  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-72 w-full rounded-2xl" />
      </div>
    );
  }

  const { port, forecast } = data;
  const overThreshold = forecast.filter((f) => f.congestion >= port.congestion_threshold);
  const peak = forecast.reduce((a, b) => (b.congestion > a.congestion ? b : a), forecast[0]);
  const worstWait = Math.max(...forecast.map((f) => f.waiting_days));
  // Colour an inbound service by the live risk of the worst chokepoint it
  // transits, so the map answers "what is dangerous today", not "what is a
  // chokepoint in general".
  const riskByChokepoint = new Map((world?.chokepoints ?? []).map((c) => [c.id, c]));
  const inboundRoutes: MapRoute[] = (world?.legs ?? [])
    .filter((l) => l.dest_id === portId && l.mode === "sea")
    .slice(0, 10)
    .map((l) => {
      const worst = l.chokepoints
        .map((id) => riskByChokepoint.get(id))
        .filter(Boolean)
        .sort((a, b) => b!.current_risk - a!.current_risk)[0];
      const hot = (worst?.current_risk ?? 0) >= 0.3;
      return {
        id: l.id,
        ports: [l.origin_id, l.dest_id],
        mode: [l.mode],
        risk: hot ? (worst!.risk_level as "amber" | "red") : undefined,
        ghost: !hot,
      };
    });

  return (
    <div className="space-y-4">
      {/* --------------------------------------------------- headline ---- */}
      <Card bodyClassName="p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-semibold tracking-tight">{port.name}</h2>
              <RiskBadge level={port.risk_level} score={port.disruption_probability_7d} />
            </div>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-soft">{data.summary}</p>
          </div>
          <Explainer
            contributions={data.explanation}
            confidence={port.confidence_7d}
            note="Declared disruptions are added on top of the statistical baseline and listed first."
          />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-5">
          <Stat
            label="Congestion now"
            value={port.congestion_now.toFixed(0)}
            hint={`normal ${port.base_congestion.toFixed(0)}`}
          />
          <Stat
            label="Peak in 14 days"
            value={peak.congestion.toFixed(0)}
            hint={data.peak_day ? fmtDate(data.peak_day) : undefined}
            tone={peak.congestion >= port.congestion_threshold ? "red" : "green"}
          />
          <Stat
            label="Days over threshold"
            value={`${overThreshold.length} / ${forecast.length}`}
            hint={`threshold ${port.congestion_threshold.toFixed(0)}`}
            tone={overThreshold.length > 3 ? "red" : overThreshold.length ? "amber" : "green"}
          />
          <Stat
            label="Worst berth wait"
            value={`${worstWait.toFixed(1)} d`}
            hint={`normal ${port.base_waiting_days.toFixed(1)} d`}
          />
          <Stat
            label="Tracked inbound"
            value={String(data.inbound_shipments)}
            hint="shipments on PortPulse"
          />
        </div>
      </Card>

      {/* --------------------------------------------------- forecast ---- */}
      <Card
        title="Inbound pressure — 60 days observed, 14 days forecast"
        subtitle="Shaded band is the 80% prediction interval from the quantile models."
        action={<ConfidenceMeter value={port.confidence_7d} />}
      >
        <CongestionChart
          history={data.history}
          forecast={forecast}
          threshold={port.congestion_threshold}
          height={260}
        />
        {forecast[0]?.event_uplift > 0 && (
          <div className="mt-3 rounded-lg border border-risk-red/25 bg-risk-redSoft/60 px-3 py-2.5">
            <div className="label mb-1.5 text-risk-red">Declared disruptions in this forecast</div>
            <ul className="space-y-1">
              {peak.event_drivers.map((d) => (
                <li key={d.headline} className="flex items-start gap-2 text-[12px] text-ink-soft">
                  <span
                    className="tnum shrink-0 font-bold"
                    style={{ color: d.points >= 0 ? RISK_COLOR.red : RISK_COLOR.green }}
                  >
                    {d.points >= 0 ? "+" : "−"}
                    {Math.abs(d.points).toFixed(1)}
                  </span>
                  <span>{d.headline}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-ink-faint">
              Statistical baseline at the peak is {peak.congestion_baseline.toFixed(0)}; declared
              events add {peak.event_uplift.toFixed(0)} points on top.
            </p>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Expected vessel arrivals"
          subtitle="Next 14 days. Red bars are days the berth queue is forecast to exceed the threshold."
        >
          <ArrivalsChart forecast={forecast} threshold={port.congestion_threshold} />
        </Card>

        <Card
          title="Upstream disruption feed"
          subtitle="Events at this port, on its chokepoints, or at the ports that feed it."
          bodyClassName="p-0"
        >
          <ul className="max-h-[300px] divide-y divide-line overflow-y-auto">
            {data.upstream_events.length === 0 && (
              <li className="px-4 py-6 text-center text-[13px] text-ink-faint">
                Nothing unusual reported upstream.
              </li>
            )}
            {data.upstream_events.map((event) => (
              <li key={event.id} className="flex gap-3 px-4 py-3">
                <span
                  className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px]"
                  style={{
                    background: `${SEVERITY_TONE[event.severity]}1A`,
                    color: SEVERITY_TONE[event.severity],
                  }}
                  aria-hidden
                >
                  {EVENT_ICON[event.type] ?? "•"}
                </span>
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[12.5px] font-semibold leading-snug">{event.headline}</span>
                    {event.scenario && (
                      <span className="shrink-0 rounded-full bg-risk-redSoft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-risk-red">
                        live
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11.5px] leading-snug text-ink-soft">{event.detail}</p>
                  <div className="mt-1 flex items-center gap-2 text-[10.5px] text-ink-faint">
                    <span className="tnum">{fmtDate(event.day)}</span>
                    <span aria-hidden>·</span>
                    <span className="capitalize">{event.type}</span>
                    <span aria-hidden>·</span>
                    <span>severity {event.severity}/5</span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card
        title="Where the pressure comes from"
        subtitle="Inbound services. Solid coloured lines transit a chokepoint that is elevated today."
        bodyClassName="p-0"
      >
        <MapPanel
          ports={world?.ports ?? []}
          routes={inboundRoutes}
          chokepoints={world?.chokepoints ?? []}
          focusPorts={[portId, ...inboundRoutes.map((r) => r.ports[0])]}
          height={320}
          className="rounded-none rounded-b-2xl"
        />
      </Card>

      <Card title="Chokepoint status" bodyClassName="p-4">
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(world?.chokepoints ?? []).map((cp) => (
            <li key={cp.id} className="rounded-xl border border-line px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[12.5px] font-semibold">{cp.name}</span>
                <span
                  className="tnum text-[12px] font-bold"
                  style={{ color: RISK_COLOR[cp.risk_level] }}
                >
                  {fmtPct(cp.current_risk)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper-sunken">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(cp.current_risk * 100, 2)}%`,
                    background: RISK_COLOR[cp.risk_level],
                  }}
                />
              </div>
              <p className="mt-1.5 text-[11px] leading-snug text-ink-faint">{cp.note}</p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
