import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Alert, ChatMessage, Chip, Option, Persona, Shipment } from "../api/types";
import { Card, ConfidenceMeter, Refreshing, RiskBadge, Skeleton } from "../components/primitives";
import { MapPanel } from "../components/MapPanel";
import type { MapRoute } from "../components/CorridorMap";
import { RISK_COLOR, fmtDate, fmtPct, fmtUsd } from "../lib/format";
import { useAsync, useStore } from "../state/store";

const CHIP_ICON: Record<Chip["key"], string> = {
  cost: "$",
  time: "⏱",
  risk: "▲",
  co2: "☁",
};

/* -------------------------------------------------------------------------- */

function Bubble({
  message,
  index,
  onChoose,
  chosen,
  busy,
}: {
  message: ChatMessage;
  index: number;
  onChoose?: (optionId: string) => void;
  chosen?: string | null;
  busy?: boolean;
}) {
  const mine = message.sender === "user";
  const isOption = message.kind === "option";
  const [head, ...rest] = message.text.split("\n");
  const picked = chosen === message.option_id;

  return (
    <div
      className={`flex animate-bubble-in ${mine ? "justify-end" : "justify-start"}`}
      style={{ animationDelay: `${Math.min(index, 8) * 55}ms` }}
    >
      <div
        className={[
          "relative max-w-[86%] rounded-2xl px-3 py-2 text-[13px] leading-[1.45] shadow-sm",
          mine
            ? "rounded-br-sm bg-[#DCF8C6] text-ink"
            : "rounded-bl-sm bg-white text-ink",
          isOption && message.recommended ? "ring-2 ring-accent/70" : "",
          picked ? "ring-2 ring-risk-green" : "",
        ].join(" ")}
      >
        {isOption && message.recommended && (
          <span className="absolute -top-2 left-3 rounded-full bg-accent px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
            Best option
          </span>
        )}
        <p className={isOption ? "font-semibold" : "whitespace-pre-line"}>{head}</p>
        {rest.length > 0 && (
          <p className="mt-1 text-[12px] leading-snug text-ink-soft">{rest.join("\n")}</p>
        )}

        {message.chips.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.chips.map((chip) => (
              <span
                key={chip.key}
                className="chip border"
                style={{
                  background: chip.tone === "good" ? "#DCF3E7" : "#FBE3E1",
                  color: chip.tone === "good" ? RISK_COLOR.green : RISK_COLOR.red,
                  borderColor: "transparent",
                }}
              >
                <span aria-hidden className="opacity-60">
                  {CHIP_ICON[chip.key]}
                </span>
                {chip.label}
              </span>
            ))}
          </div>
        )}

        {isOption && onChoose && message.option_id && (
          <button
            type="button"
            disabled={busy || !!chosen}
            onClick={() => onChoose(message.option_id!)}
            className="mt-2.5 w-full rounded-lg bg-accent px-3 py-1.5 text-[12px] font-semibold text-white
                       transition hover:bg-accent-deep disabled:opacity-40"
          >
            {picked ? "Selected ✓" : "Choose this"}
          </button>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function PhoneFrame({
  persona,
  children,
  footer,
}: {
  persona: Persona;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[380px]">
      <div className="rounded-phone border-[10px] border-[#22242C] bg-[#22242C] shadow-phone">
        <div className="overflow-hidden rounded-[2rem] bg-[#ECE5DD]">
          {/* status bar */}
          <div className="flex items-center justify-between bg-[#075E54] px-4 pb-1 pt-2 text-[10px] font-medium text-white/80">
            <span className="tnum">09:41</span>
            <span className="h-4 w-20 rounded-full bg-[#22242C]" aria-hidden />
            <span className="tnum">◍ ▮▮▮</span>
          </div>
          {/* conversation header */}
          <div className="flex items-center gap-2.5 bg-[#075E54] px-3 pb-2.5 text-white">
            <div className="grid h-9 w-9 place-items-center rounded-full bg-white/15 text-lg">🛰</div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold">PortPulse Alerts</div>
              <div className="truncate text-[10.5px] text-white/70">
                to {persona.name.split(" ")[0]} · {persona.location}
              </div>
            </div>
            <span className="rounded-full bg-white/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide">
              {persona.language === "sw" ? "SW" : "EN"}
            </span>
          </div>

          <div
            className="max-h-[520px] min-h-[420px] space-y-2 overflow-y-auto px-3 py-3"
            style={{
              backgroundImage:
                "radial-gradient(circle at 20% 10%, rgba(255,255,255,0.5) 0 1px, transparent 1px), radial-gradient(circle at 70% 60%, rgba(255,255,255,0.4) 0 1px, transparent 1px)",
              backgroundSize: "28px 28px, 34px 34px",
            }}
          >
            {children}
          </div>

          {footer}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function PhoneView({ persona }: { persona: Persona }) {
  const { world, version, refresh } = useStore();
  // Opens in English for the room; one tap shows the same alert in the
  // trader's own language, which is the point being demonstrated.
  const [lang, setLang] = useState("en");
  const [revealed, setRevealed] = useState(1);
  const [chosen, setChosen] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ChatMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<boolean | null>(null);

  const shipments = useAsync(() => api.shipments(persona.id), [persona.id, version]);
  const shipment: Shipment | undefined = shipments.data?.[0];

  const alert = useAsync(
    () => (shipment ? api.alert(shipment.id, lang) : Promise.resolve(null)),
    [shipment?.id, lang, version],
  );
  const recs = useAsync(
    () => (shipment ? api.recommendations(shipment.id) : Promise.resolve(null)),
    [shipment?.id, version],
  );
  const exposure = useAsync(
    () => (shipment ? api.exposure(shipment.id) : Promise.resolve(null)),
    [shipment?.id, version],
  );

  // A new world state restarts the conversation from the alert.
  useEffect(() => {
    setRevealed(1);
    setChosen(null);
    setConfirmation(null);
    setFeedback(null);
  }, [version, lang]);

  const bundle: Alert | null = alert.data;
  const messages = bundle?.messages ?? [];
  const visible = messages.slice(0, revealed);
  const options: Option[] = recs.data?.options ?? [];
  const top = options.find((o) => o.rank === 1);

  const chooseOption = async (optionId: string) => {
    if (!shipment) return;
    setBusy(true);
    try {
      const result = await api.accept(shipment.id, optionId, lang);
      setChosen(optionId);
      setConfirmation(result.message);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const sendFeedback = async (helpful: boolean) => {
    if (!shipment) return;
    setFeedback(helpful);
    await api.feedback(shipment.id, helpful);
  };

  const routes = useMemo(() => {
    if (!shipment || !world) return [];
    const legById = new Map(world.legs.map((l) => [l.id, l]));
    const current = shipment.leg_ids.map((id) => legById.get(id)).filter(Boolean);
    if (current.length === 0) return [];
    const out: MapRoute[] = [
      {
        id: "current",
        ports: [current[0]!.origin_id, ...current.map((l) => l!.dest_id)],
        mode: current.map((l) => l!.mode),
        risk: shipment.risk_level,
        label: "Booked route",
      },
    ];
    if (top && top.kind !== "hold" && !chosen) {
      out.push({
        id: "proposed",
        ports: top.route_ports,
        mode: top.leg_ids.map((id) => legById.get(id)?.mode ?? "sea"),
        risk: "green" as const,
        label: "Recommended",
      });
    }
    return out;
  }, [shipment, world, top, chosen]);

  if (!shipment) {
    return (
      <div className="grid gap-4 lg:grid-cols-[minmax(0,380px)_1fr]">
        <Skeleton className="h-[600px] rounded-phone" />
        <Skeleton className="h-[600px] rounded-2xl" />
      </div>
    );
  }

  const moreToReveal = revealed < messages.length;
  const nextIsPrompt = messages[revealed]?.sender === "user";

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,392px)_minmax(0,1fr)]">
      {/* ---------------------------------------------------------------- */}
      <div>
        <PhoneFrame
          persona={persona}
          footer={
            <div className="border-t border-black/5 bg-[#F0F0F0] px-3 py-2.5">
              {confirmation ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-ink-faint">Was this alert useful?</span>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => void sendFeedback(true)}
                      className={`rounded-full border px-2.5 py-1 text-[12px] transition ${
                        feedback === true
                          ? "border-risk-green bg-risk-greenSoft text-risk-green"
                          : "border-line bg-white text-ink-soft hover:border-line-strong"
                      }`}
                      aria-label="This alert was useful"
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      onClick={() => void sendFeedback(false)}
                      className={`rounded-full border px-2.5 py-1 text-[12px] transition ${
                        feedback === false
                          ? "border-risk-red bg-risk-redSoft text-risk-red"
                          : "border-line bg-white text-ink-soft hover:border-line-strong"
                      }`}
                      aria-label="This alert was not useful"
                    >
                      👎
                    </button>
                  </div>
                </div>
              ) : moreToReveal ? (
                <button
                  type="button"
                  onClick={() => setRevealed((r) => r + 1)}
                  className="w-full rounded-full bg-[#075E54] px-3 py-2 text-[12.5px] font-semibold text-white
                             transition hover:bg-[#064c44]"
                >
                  {nextIsPrompt ? "Reply “1” — see all options" : "Continue"}
                </button>
              ) : (
                <p className="text-center text-[11px] text-ink-faint">
                  Tap an option above to confirm the change.
                </p>
              )}
            </div>
          }
        >
          <Refreshing active={alert.stale}>
          {visible.map((message, i) => (
            <Bubble
              key={message.id}
              message={message}
              index={i}
              chosen={chosen}
              busy={busy}
              onChoose={message.kind === "option" ? chooseOption : undefined}
            />
          ))}
          {confirmation && <Bubble message={confirmation} index={visible.length} />}
          </Refreshing>
        </PhoneFrame>

        <div className="mt-3 flex items-center justify-center gap-2">
          {(["en", "sw"] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLang(code)}
              className={`btn px-3 py-1 text-[12px] ${lang === code ? "btn-accent" : ""}`}
            >
              {code === "en" ? "English" : "Kiswahili"}
            </button>
          ))}
        </div>
        {bundle && (
          <p className="mt-2 text-center text-[11px] text-ink-faint">
            Alert is <span className="tnum font-semibold text-ink-soft">{bundle.alert_chars}</span>{" "}
            characters — fits one SMS-length message on a 2G connection.
          </p>
        )}
      </div>

      {/* ---------------------------------------------------------------- */}
      <div className="space-y-4">
        <Card
          title={`${shipment.cargo} · ${shipment.reference}`}
          subtitle={`${shipment.origin_name} → ${shipment.dest_name} · ${shipment.teu} TEU · buyer ${shipment.buyer}`}
          action={<RiskBadge level={shipment.risk_level} score={shipment.risk_score} />}
          bodyClassName="p-0"
        >
          <MapPanel
            ports={world?.ports ?? []}
            routes={routes}
            chokepoints={world?.chokepoints ?? []}
            height={300}
            className="rounded-none"
          />
          <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
            <Field label="ETD" value={fmtDate(shipment.etd)} />
            <Field
              label="Expected arrival"
              value={exposure.data ? fmtDate(exposure.data.expected_arrival) : "—"}
              hint={exposure.data ? `buyer needs ${fmtDate(shipment.required_by)}` : undefined}
            />
            <Field
              label="Expected delay"
              value={exposure.data ? `${exposure.data.expected_delay_days.toFixed(1)} d` : "—"}
              tone={shipment.risk_level}
            />
            <Field
              label="Spoilage risk"
              value={
                shipment.spoilage_probability !== null
                  ? fmtPct(shipment.spoilage_probability)
                  : "n/a"
              }
              tone={exposure.data?.spoilage_band ?? undefined}
              hint={shipment.shelf_life_days ? `${shipment.shelf_life_days}-day shelf life` : undefined}
            />
          </div>
        </Card>

        {shipment.rerouted && (
          <div className="rounded-xl border border-risk-green/30 bg-risk-greenSoft px-4 py-3 text-[13px] text-risk-green">
            <strong className="font-semibold">Rebooked.</strong> {shipment.applied_option}
          </div>
        )}

        <Card
          title="Why this alert fired"
          subtitle="Every number below is produced by the model, not written into the demo."
        >
          {exposure.data ? (
            <div className="space-y-3">
              {exposure.data.drivers.length === 0 && (
                <p className="rounded-lg bg-risk-greenSoft px-3 py-2 text-[12.5px] leading-snug text-risk-green">
                  Nothing is pushing this shipment off schedule right now — every port on the route
                  is forecast to run at its normal level.
                </p>
              )}
              <ul className="space-y-2">
                {exposure.data.drivers.map((driver) => (
                  <li key={driver.label} className="flex items-center gap-3 text-[13px]">
                    <span className="tnum w-14 shrink-0 rounded bg-paper-sunken px-1.5 py-0.5 text-center text-[11.5px] font-bold text-ink-soft">
                      +{driver.days.toFixed(1)}d
                    </span>
                    <span className="text-ink-soft">{driver.label}</span>
                  </li>
                ))}
              </ul>
              <div className="hairline flex items-center justify-between pt-3 text-[12px] text-ink-faint">
                <span>Forecast confidence across the route</span>
                <ConfidenceMeter value={exposure.data.confidence} />
              </div>
              {top && top.kind !== "hold" && (
                <p className="rounded-lg bg-accent-soft px-3 py-2 text-[12.5px] leading-snug text-accent-deep">
                  Best alternative saves{" "}
                  <strong className="tnum">{fmtUsd(Math.max(top.savings_usd, 0))}</strong> in expected
                  landed cost and <strong className="tnum">{top.delta_risk_days.toFixed(1)} days</strong> of
                  delay risk.
                </p>
              )}
            </div>
          ) : (
            <Skeleton className="h-24 w-full" />
          )}
        </Card>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "green" | "amber" | "red";
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div
        className="tnum mt-1 text-[15px] font-semibold"
        style={tone ? { color: RISK_COLOR[tone] } : undefined}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-ink-faint">{hint}</div>}
    </div>
  );
}
