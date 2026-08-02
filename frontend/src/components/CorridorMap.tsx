import { useMemo } from "react";

import type { Chokepoint, PortStatus, RiskLevel } from "../api/types";
import { ACCENT, RISK_COLOR } from "../lib/format";
import { LANDMASSES, arcPath, frameAround, makeProjection } from "../lib/geo";

export interface MapRoute {
  id: string;
  ports: string[];
  mode?: ("sea" | "land")[];
  risk?: RiskLevel;
  /** Dashed, de-emphasised: the plan being replaced. */
  ghost?: boolean;
  label?: string;
}

interface Props {
  ports: PortStatus[];
  routes?: MapRoute[];
  chokepoints?: Chokepoint[];
  /** Ports to label and enlarge; defaults to every port on a route. */
  focusPorts?: string[];
  height?: number;
  showAllPorts?: boolean;
  className?: string;
}

const WIDTH = 900;

/**
 * Stylised corridor map, rendered as inline SVG.
 *
 * This is the default renderer precisely because it cannot fail offline: no
 * tiles, no network, no blank grey square in front of a jury. `LeafletMap`
 * takes over only when a tile server turns out to be reachable.
 */
export function CorridorMap({
  ports,
  routes = [],
  chokepoints = [],
  focusPorts,
  height = 380,
  showAllPorts = true,
  className = "",
}: Props) {
  const byId = useMemo(() => new Map(ports.map((p) => [p.id, p])), [ports]);

  const routePortIds = useMemo(
    () => new Set(routes.flatMap((r) => r.ports)),
    [routes],
  );
  const highlighted = useMemo(
    () => new Set(focusPorts ?? [...routePortIds]),
    [focusPorts, routePortIds],
  );

  const project = useMemo(() => {
    const anchors = highlighted.size ? ports.filter((p) => highlighted.has(p.id)) : ports;
    return makeProjection(frameAround(anchors, WIDTH, height), WIDTH, height);
  }, [ports, highlighted, height]);

  // Jeddah and King Abdullah Port are 80 nm apart; without this their labels
  // sit on top of each other.
  const labelOffsets = useMemo(() => {
    const placed: { x: number; y: number; dy: number }[] = [];
    const offsets = new Map<string, number>();
    for (const port of ports) {
      if (!highlighted.has(port.id)) continue;
      const [x, y] = project(port.lon, port.lat);
      let dy = 18;
      while (placed.some((q) => Math.abs(q.x - x) < 74 && Math.abs(q.y + q.dy - (y + dy)) < 13)) {
        dy = dy > 0 ? -13 : -dy + 15;
        if (Math.abs(dy) > 70) break;
      }
      placed.push({ x, y, dy });
      offsets.set(port.id, dy);
    }
    return offsets;
  }, [ports, highlighted, project]);

  const land = useMemo(
    () =>
      LANDMASSES.map(({ id, ring }) => ({
        id,
        d:
          ring
            .map(([lon, lat], i) => {
              const [x, y] = project(lon, lat);
              return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
            })
            .join(" ") + " Z",
      })),
    [project],
  );

  return (
    <div className={`relative overflow-hidden rounded-xl bg-sea ${className}`}>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        className="block h-auto w-full"
        role="img"
        aria-label="Corridor map from Southeast Asia to the Gulf"
      >
        <defs>
          <pattern id="pp-grid" width="45" height="45" patternUnits="userSpaceOnUse">
            <path d="M45 0 L0 0 0 45" fill="none" stroke="rgba(23,24,29,0.045)" strokeWidth="1" />
          </pattern>
          <filter id="pp-soft" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        <rect width={WIDTH} height={height} fill="#DCE6EC" />
        <rect width={WIDTH} height={height} fill="url(#pp-grid)" />

        {land.map(({ id, d }) => (
          <path key={id} d={d} fill="#EAE4D8" stroke="#D8CFBE" strokeWidth="1.1" />
        ))}

        {/* Chokepoints sit under the routes so the lines stay readable. */}
        {chokepoints.map((cp) => {
          const [x, y] = project(cp.lon, cp.lat);
          const hot = cp.current_risk >= 0.3;
          return (
            <g key={cp.id}>
              {hot && (
                <circle
                  cx={x}
                  cy={y}
                  r={13}
                  fill={RISK_COLOR[cp.risk_level]}
                  opacity={0.25}
                  filter="url(#pp-soft)"
                />
              )}
              <rect
                x={x - 5}
                y={y - 5}
                width={10}
                height={10}
                transform={`rotate(45 ${x} ${y})`}
                fill={hot ? RISK_COLOR[cp.risk_level] : "#FFFDF8"}
                stroke={hot ? RISK_COLOR[cp.risk_level] : "#8A8C99"}
                strokeWidth="1.5"
              />
              {hot && (
                <text
                  x={x}
                  y={y - 12}
                  textAnchor="middle"
                  className="tnum"
                  fontSize="10.5"
                  fontWeight="700"
                  fill={RISK_COLOR[cp.risk_level]}
                >
                  {Math.round(cp.current_risk * 100)}%
                </text>
              )}
            </g>
          );
        })}

        {routes.map((route) =>
          route.ports.slice(0, -1).map((from, i) => {
            const to = route.ports[i + 1];
            const a = byId.get(from);
            const b = byId.get(to);
            if (!a || !b) return null;
            const p1 = project(a.lon, a.lat);
            const p2 = project(b.lon, b.lat);
            const isLand = route.mode?.[i] === "land";
            const stroke = route.ghost ? "#8A8C99" : (route.risk ? RISK_COLOR[route.risk] : ACCENT);
            return (
              <g key={`${route.id}-${from}-${to}`}>
                {!route.ghost && (
                  <path
                    d={arcPath(p1, p2, isLand ? 0.02 : 0.13)}
                    fill="none"
                    stroke={stroke}
                    strokeWidth="7"
                    strokeLinecap="round"
                    opacity={0.16}
                  />
                )}
                <path
                  d={arcPath(p1, p2, isLand ? 0.02 : 0.13)}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={route.ghost ? 1.6 : 2.6}
                  strokeLinecap="round"
                  strokeDasharray={route.ghost ? "5 5" : isLand ? "1 6" : undefined}
                  opacity={route.ghost ? 0.65 : 1}
                />
              </g>
            );
          }),
        )}

        {ports.map((port) => {
          const onRoute = highlighted.has(port.id);
          if (!onRoute && !showAllPorts) return null;
          const [x, y] = project(port.lon, port.lat);
          if (x < -20 || x > WIDTH + 20 || y < -20 || y > height + 20) return null;
          const color = RISK_COLOR[port.risk_level];
          return (
            <g key={port.id}>
              {onRoute && port.risk_level === "red" && (
                <circle cx={x} cy={y} r={7} fill={color} opacity={0.3}>
                  <animate
                    attributeName="r"
                    values="7;16;7"
                    dur="2.4s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values="0.32;0;0.32"
                    dur="2.4s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
              <circle
                cx={x}
                cy={y}
                r={onRoute ? 5.5 : 3}
                fill={onRoute ? color : "#FFFDF8"}
                stroke={onRoute ? "#FFFDF8" : "#9AA6AE"}
                strokeWidth={onRoute ? 2 : 1.2}
              />
              {onRoute && (
                <text
                  x={x}
                  y={y + (labelOffsets.get(port.id) ?? 18)}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight="600"
                  fill="#17181D"
                  stroke="#DCE6EC"
                  strokeWidth="3"
                  paintOrder="stroke"
                >
                  {port.short_name}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] font-medium uppercase tracking-wider text-ink-faint/80">
        Stylised corridor view · offline
      </div>
    </div>
  );
}
