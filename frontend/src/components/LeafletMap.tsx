import "leaflet/dist/leaflet.css";

import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";

import type { Chokepoint, PortStatus } from "../api/types";
import { ACCENT, RISK_COLOR } from "../lib/format";
import type { MapRoute } from "./CorridorMap";

export const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

interface Props {
  ports: PortStatus[];
  routes: MapRoute[];
  chokepoints: Chokepoint[];
  focusPorts: string[];
  height: number;
}

/**
 * Real basemap, loaded only when `useTilesReachable` has confirmed a tile
 * server actually answers. Everything here is lazy-imported so an offline
 * laptop never pays for Leaflet at all.
 */
export default function LeafletMap({ ports, routes, chokepoints, focusPorts, height }: Props) {
  const byId = new Map(ports.map((p) => [p.id, p]));
  const anchors = (focusPorts.length ? focusPorts : ports.map((p) => p.id))
    .map((id) => byId.get(id))
    .filter(Boolean) as PortStatus[];
  const bounds: [number, number][] = anchors.map((p) => [p.lat, p.lon]);

  return (
    <div className="overflow-hidden rounded-xl" style={{ height }}>
      <MapContainer
        bounds={bounds.length > 1 ? bounds : undefined}
        center={bounds.length === 1 ? bounds[0] : [12, 62]}
        zoom={bounds.length === 1 ? 5 : 3}
        boundsOptions={{ padding: [40, 40] }}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer url={TILE_URL} attribution="&copy; OpenStreetMap contributors" />

        {routes.map((route) => {
          const line = route.ports
            .map((id) => byId.get(id))
            .filter(Boolean)
            .map((p) => [p!.lat, p!.lon] as [number, number]);
          return (
            <Polyline
              key={route.id}
              positions={line}
              pathOptions={{
                color: route.ghost ? "#8A8C99" : route.risk ? RISK_COLOR[route.risk] : ACCENT,
                weight: route.ghost ? 2 : 4,
                opacity: route.ghost ? 0.6 : 0.95,
                dashArray: route.ghost ? "6 6" : undefined,
              }}
            />
          );
        })}

        {chokepoints
          .filter((cp) => cp.current_risk >= 0.3)
          .map((cp) => (
            <CircleMarker
              key={cp.id}
              center={[cp.lat, cp.lon]}
              radius={9}
              pathOptions={{
                color: RISK_COLOR[cp.risk_level],
                fillColor: RISK_COLOR[cp.risk_level],
                fillOpacity: 0.35,
              }}
            >
              <Tooltip>
                {cp.name} — {Math.round(cp.current_risk * 100)}% transit risk
              </Tooltip>
            </CircleMarker>
          ))}

        {ports.map((port) => {
          const onRoute = focusPorts.includes(port.id);
          return (
            <CircleMarker
              key={port.id}
              center={[port.lat, port.lon]}
              radius={onRoute ? 7 : 3.5}
              pathOptions={{
                color: "#FFFDF8",
                weight: onRoute ? 2 : 1,
                fillColor: onRoute ? RISK_COLOR[port.risk_level] : "#9AA6AE",
                fillOpacity: 1,
              }}
            >
              <Tooltip>
                {port.name} — congestion {port.congestion_now.toFixed(0)}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
