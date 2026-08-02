import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Option, Persona, Shipment } from "../api/types";
import type { MapRoute } from "../components/CorridorMap";
import { DelayDistributionChart, SpoilageGauge } from "../components/charts";
import { MapPanel } from "../components/MapPanel";
import {
  Card,
  ConfidenceMeter,
  EmptyState,
  RiskBadge,
  Refreshing,
  RiskDot,
  Skeleton,
  Stat,
} from "../components/primitives";
import { RISK_COLOR, fmtDate, fmtDays, fmtPct, fmtTonnes, fmtUsd } from "../lib/format";
import { useAsync, useStore } from "../state/store";

/* -------------------------------------------------------------------------- */

function ShipmentRow({
  shipment,
  active,
  onSelect,
}: {
  shipment: Shipment;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-xl border px-3 py-2.5 text-left transition ${
        active
          ? "border-accent bg-accent-soft/60"
          : "border-transparent hover:border-line hover:bg-paper-sunken/60"
      }`}
    >
      <div className="flex items-center gap-2">
        <RiskDot level={shipment.risk_level} />
        <span className="truncate text-[13px] font-semibold">{shipment.reference}</span>
        <span className="ml-auto tnum text-[11px] font-semibold" style={{ color: RISK_COLOR[shipment.risk_level] }}>
          {fmtPct(shipment.risk_score)}
        </span>
      </div>
      <div className="mt-1 truncate text-[11.5px] text-ink-soft">{shipment.cargo}</div>
      <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-faint">
        <span className="truncate">
          {shipment.origin_id} → {shipment.dest_id}
        </span>
        <span aria-hidden>·</span>
        <span className="tnum">ETD {fmtDate(shipment.etd)}</span>
        {shipment.rerouted && (
          <span className="ml-auto rounded-full bg-accent-soft px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-accent-deep">
            rebooked
          </span>
        )}
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */

function OptionsTable({
  options,
  objective,
  onAccept,
  busy,
}: {
  options: Option[];
  objective: string;
  onAccept: (id: string) => void;
  busy: boolean;
}) {
  const columns: { key: keyof Option; head: string; render: (o: Option) => string; good: (o: Option) => boolean }[] = [
    {
      key: "delta_cost_usd",
      head: "Δ cost",
      render: (o) => fmtUsd(o.delta_cost_usd, { sign: true }),
      good: (o) => o.delta_cost_usd <= 0,
    },
    {
      key: "delta_transit_days",
      head: "Δ arrival",
      render: (o) => fmtDays(o.delta_transit_days, { sign: true }),
      good: (o) => o.delta_transit_days <= 0,
    },
    {
      key: "delta_risk_days",
      head: "Δ risk days",
      render: (o) => fmtDays(o.delta_risk_days, { sign: true }),
      good: (o) => o.delta_risk_days >= 0,
    },
    {
      key: "delta_co2_tonnes",
      head: "Δ CO₂",
      render: (o) => fmtTonnes(o.delta_co2_tonnes, { sign: true }),
      good: (o) => o.delta_co2_tonnes <= 0,
    },
  ];

  return (
    <div>
      <div className="-mx-4 overflow-x-auto px-4">
        <table className="w-full min-w-[820px] border-separate border-spacing-0 text-[12.5px]">
          <thead>
            <tr className="label">
              <th className="pb-2 pr-3 text-left font-semibold">Option</th>
              {columns.map((c) => (
                <th key={c.head} className="pb-2 px-2 text-right font-semibold">
                  {c.head}
                </th>
              ))}
              <th className="pb-2 px-2 text-right font-semibold">Landed cost</th>
              <th className="pb-2 pl-2 text-right font-semibold">Risk</th>
              <th className="pb-2 pl-2" />
            </tr>
          </thead>
          <tbody>
            {options.map((o) => (
              <tr
                key={o.id}
                className={o.recommended ? "bg-accent-soft/50" : undefined}
              >
                <td className="border-t border-line py-2.5 pr-3 align-top">
                  <div className="flex items-start gap-2">
                    <span
                      className={`tnum mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold ${
                        o.recommended ? "bg-accent text-white" : "bg-paper-sunken text-ink-soft"
                      }`}
                    >
                      {o.rank}
                    </span>
                    <div className="min-w-0">
                      <div className="font-semibold leading-snug">{o.label}</div>
                      <div className="mt-0.5 text-[11.5px] leading-snug text-ink-faint">
                        {o.route_port_names.join(" → ")} · ETD {fmtDate(o.etd)} ·{" "}
                        {o.scheduled_transit_days.toFixed(0)}d transit
                      </div>
                      {o.caveats.map((c) => (
                        <div key={c} className="mt-1 text-[11px] leading-snug text-risk-amber">
                          ⚠ {c}
                        </div>
                      ))}
                    </div>
                  </div>
                </td>
                {columns.map((c) => (
                  <td
                    key={c.head}
                    className="tnum whitespace-nowrap border-t border-line px-2 py-2.5 text-right align-top font-semibold"
                    style={{ color: c.good(o) ? RISK_COLOR.green : RISK_COLOR.red }}
                  >
                    {o.kind === "hold" ? <span className="text-ink-faint">—</span> : c.render(o)}
                  </td>
                ))}
                <td className="tnum whitespace-nowrap border-t border-line px-2 py-2.5 text-right align-top font-semibold">
                  {fmtUsd(o.costs.total_usd)}
                  {o.savings_usd > 0 && (
                    <div className="text-[11px] font-medium text-risk-green">
                      saves {fmtUsd(o.savings_usd)}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap border-t border-line pl-2 py-2.5 text-right align-top">
                  <RiskBadge level={o.risk_level} score={o.prob_miss_deadline} compact />
                </td>
                <td className="border-t border-line pl-2 py-2.5 text-right align-top">
                  {o.kind !== "hold" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onAccept(o.id)}
                      className={`btn px-2.5 py-1 text-[11.5px] ${o.recommended ? "btn-accent" : ""}`}
                    >
                      Apply
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 border-t border-line pt-3 text-[11.5px] leading-relaxed text-ink-faint">
        {objective}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function DashboardView({ persona }: { persona: Persona }) {
  const { world, version, refresh } = useStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const shipments = useAsync(() => api.shipments(persona.id), [persona.id, version]);
  const rows = shipments.data ?? [];
  const selected = rows.find((s) => s.id === selectedId) ?? rows[0];

  useEffect(() => {
    if (rows.length && !rows.some((s) => s.id === selectedId)) setSelectedId(rows[0].id);
  }, [rows, selectedId]);

  const exposure = useAsync(
    () => (selected ? api.exposure(selected.id) : Promise.resolve(null)),
    [selected?.id, version],
  );
  const recs = useAsync(
    () => (selected ? api.recommendations(selected.id) : Promise.resolve(null)),
    [selected?.id, version],
  );

  const routes = useMemo(() => {
    if (!selected || !world) return [];
    const legById = new Map(world.legs.map((l) => [l.id, l]));
    const current = selected.leg_ids.map((id) => legById.get(id)).filter(Boolean);
    if (!current.length) return [];
    const out: MapRoute[] = [
      {
        id: "current",
        ports: [current[0]!.origin_id, ...current.map((l) => l!.dest_id)],
        mode: current.map((l) => l!.mode),
        risk: selected.risk_level,
      },
    ];
    const top = recs.data?.options.find((o) => o.rank === 1);
    if (top && top.kind !== "hold") {
      out.push({
        id: "proposed",
        ports: top.route_ports,
        mode: top.leg_ids.map((id) => legById.get(id)?.mode ?? "sea"),
        risk: "green" as const,
        ghost: true,
      });
    }
    return out;
  }, [selected, world, recs.data]);

  const accept = async (optionId: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.accept(selected.id, optionId);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const counts = rows.reduce<Record<string, number>>((acc, s) => {
    acc[s.risk_level] = (acc[s.risk_level] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="grid gap-5 xl:grid-cols-[290px_minmax(0,1fr)]">
      {/* ------------------------------------------------------- list ---- */}
      <div className="space-y-3">
        <Card
          title={shipments.loading && !rows.length ? "Loading bookings…" : `${rows.length} live bookings`}
          subtitle={`${counts.red ?? 0} at risk · ${counts.amber ?? 0} to watch · ${counts.green ?? 0} on track`}
          bodyClassName="p-2 space-y-1"
        >
          {shipments.loading && !rows.length ? (
            <div className="space-y-2 p-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-14 w-full rounded-xl" />
              ))}
            </div>
          ) : (
            rows.map((s) => (
              <ShipmentRow
                key={s.id}
                shipment={s}
                active={s.id === selected?.id}
                onSelect={() => setSelectedId(s.id)}
              />
            ))
          )}
        </Card>
      </div>

      {/* --------------------------------------------------- detail ------ */}
      {!selected ? (
        shipments.loading ? (
          <div className="space-y-4">
            <Skeleton className="h-[360px] w-full rounded-2xl" />
            <Skeleton className="h-52 w-full rounded-2xl" />
          </div>
        ) : (
          <EmptyState>No bookings for this persona.</EmptyState>
        )
      ) : (
        <div className="space-y-4">
          <Card
            title={`${selected.reference} · ${selected.cargo}`}
            subtitle={`${selected.origin_name} → ${selected.dest_name} · ${selected.teu} TEU · ${fmtUsd(selected.value_usd)} · buyer ${selected.buyer}`}
            action={<RiskBadge level={selected.risk_level} score={selected.risk_score} />}
            bodyClassName="p-0"
          >
            <MapPanel
              ports={world?.ports ?? []}
              routes={routes}
              chokepoints={world?.chokepoints ?? []}
              height={280}
              className="rounded-none"
            />
            {exposure.data && (
              <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
                <Stat
                  label="Expected delay"
                  value={`${exposure.data.expected_delay_days.toFixed(1)} d`}
                  hint={`p10–p90 ${exposure.data.delay_p10.toFixed(1)}–${exposure.data.delay_p90.toFixed(1)} d`}
                  tone={selected.risk_level}
                />
                <Stat
                  label="Miss buyer deadline"
                  value={fmtPct(exposure.data.prob_miss_deadline)}
                  hint={`needs ${fmtDate(exposure.data.required_by)}`}
                />
                <Stat
                  label="Demurrage"
                  value={fmtUsd(exposure.data.demurrage_usd)}
                  hint={`${exposure.data.demurrage_days.toFixed(1)} chargeable days`}
                />
                <Stat
                  label="Arrives"
                  value={fmtDate(exposure.data.expected_arrival)}
                  hint={`scheduled ${fmtDate(exposure.data.scheduled_arrival)}`}
                />
              </div>
            )}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Delay distribution"
              subtitle="Probability the shipment arrives this many days late."
              action={
                exposure.data ? <ConfidenceMeter value={exposure.data.confidence} /> : undefined
              }
            >
              {exposure.data ? (
                <>
                  <DelayDistributionChart
                    bins={exposure.data.delay_distribution}
                    expected={exposure.data.expected_delay_days}
                  />
                  <div className="mt-2 flex gap-4 text-[11.5px] text-ink-faint">
                    <span>
                      &gt;3 days:{" "}
                      <strong className="tnum text-ink-soft">
                        {fmtPct(exposure.data.prob_delay_over_3)}
                      </strong>
                    </span>
                    <span>
                      &gt;7 days:{" "}
                      <strong className="tnum text-ink-soft">
                        {fmtPct(exposure.data.prob_delay_over_7)}
                      </strong>
                    </span>
                  </div>
                </>
              ) : (
                <Skeleton className="h-36 w-full" />
              )}
            </Card>

            <Card title="Where the days go" subtitle="Per-leg and per-call contributions.">
              {exposure.data ? (
                <div className="space-y-3">
                  {selected.perishable &&
                    exposure.data.spoilage_probability !== null &&
                    exposure.data.spoilage_band && (
                      <div className="rounded-xl bg-paper-sunken/70 p-3">
                        <SpoilageGauge
                          probability={exposure.data.spoilage_probability}
                          band={exposure.data.spoilage_band}
                          shelfLifeDays={selected.shelf_life_days ?? 0}
                          transitDays={exposure.data.scheduled_transit_days}
                        />
                      </div>
                    )}
                  <ul className="space-y-1.5">
                    {exposure.data.calls.map((call) => (
                      <li
                        key={`${call.port_id}-${call.day}`}
                        className="flex items-center gap-2.5 text-[12.5px]"
                      >
                        <RiskDot level={call.risk_level} />
                        <span className="w-[130px] shrink-0 truncate font-medium">
                          {call.port_short_name}
                        </span>
                        <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-ink-faint">
                          {call.role}
                        </span>
                        <span className="tnum ml-auto text-ink-soft">
                          wait {call.forecast_waiting.toFixed(1)}d
                        </span>
                        <span
                          className="tnum w-14 shrink-0 text-right font-semibold"
                          style={{ color: call.delay_days > 0.3 ? RISK_COLOR.red : "#8A8C99" }}
                        >
                          +{call.delay_days.toFixed(1)}d
                        </span>
                      </li>
                    ))}
                  </ul>
                  {exposure.data.legs.some((l) => l.chokepoint_delay_days > 0.05) && (
                    <ul className="hairline space-y-1.5 pt-3">
                      {exposure.data.legs
                        .filter((l) => l.chokepoint_delay_days > 0.05)
                        .map((leg) => (
                          <li key={leg.leg_id} className="flex items-center gap-2.5 text-[12.5px]">
                            <span className="text-ink-faint" aria-hidden>
                              ◆
                            </span>
                            <span className="truncate text-ink-soft">
                              {leg.chokepoints.join(", ").replace(/_/g, " ")} transit
                            </span>
                            <span className="tnum ml-auto text-[11px] text-ink-faint">
                              risk {fmtPct(leg.chokepoint_risk)}
                            </span>
                            <span className="tnum w-14 shrink-0 text-right font-semibold text-risk-red">
                              +{leg.chokepoint_delay_days.toFixed(1)}d
                            </span>
                          </li>
                        ))}
                    </ul>
                  )}
                </div>
              ) : (
                <Skeleton className="h-36 w-full" />
              )}
            </Card>
          </div>

          <Card
            title="Alternatives"
            subtitle="Ranked by expected total landed cost. Dominated options are removed."
          >
            {recs.data ? (
              <Refreshing active={recs.stale}>
              <OptionsTable
                options={recs.data.options}
                objective={recs.data.objective}
                onAccept={accept}
                busy={busy}
              />
              </Refreshing>
            ) : (
              <Skeleton className="h-40 w-full" />
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
