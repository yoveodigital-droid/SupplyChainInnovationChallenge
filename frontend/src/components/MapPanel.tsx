import { Suspense, lazy, useEffect, useState } from "react";

import type { Chokepoint, PortStatus } from "../api/types";
import { CorridorMap, type MapRoute } from "./CorridorMap";

const LeafletMap = lazy(() => import("./LeafletMap"));

/**
 * Probe a single tile before deciding to use Leaflet.
 *
 * The demo has to survive a conference wifi that resolves DNS but serves
 * nothing, so this waits a short, fixed time and then gives up for good. On
 * failure the stylised SVG map stays — which is the intended look anyway.
 */
function useTilesReachable(timeoutMs = 1800): boolean {
  const [reachable, setReachable] = useState(false);

  useEffect(() => {
    if (import.meta.env.VITE_FORCE_SVG_MAP === "1") return;
    let settled = false;
    const image = new Image();
    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        image.src = "";
      }
    }, timeoutMs);

    image.onload = () => {
      if (!settled) {
        settled = true;
        window.clearTimeout(timer);
        setReachable(true);
      }
    };
    image.onerror = () => {
      settled = true;
      window.clearTimeout(timer);
    };
    image.src = "https://a.tile.openstreetmap.org/2/2/1.png";

    return () => {
      settled = true;
      window.clearTimeout(timer);
    };
  }, [timeoutMs]);

  return reachable;
}

interface Props {
  ports: PortStatus[];
  routes?: MapRoute[];
  chokepoints?: Chokepoint[];
  focusPorts?: string[];
  height?: number;
  showAllPorts?: boolean;
  className?: string;
}

export function MapPanel({
  ports,
  routes = [],
  chokepoints = [],
  focusPorts,
  height = 380,
  showAllPorts = true,
  className = "",
}: Props) {
  const tiles = useTilesReachable();
  const focus = focusPorts ?? [...new Set(routes.flatMap((r) => r.ports))];

  const fallback = (
    <CorridorMap
      ports={ports}
      routes={routes}
      chokepoints={chokepoints}
      focusPorts={focusPorts}
      height={height}
      showAllPorts={showAllPorts}
      className={className}
    />
  );

  if (!tiles) return fallback;

  return (
    <Suspense fallback={fallback}>
      <LeafletMap
        ports={ports}
        routes={routes}
        chokepoints={chokepoints}
        focusPorts={focus}
        height={height}
      />
    </Suspense>
  );
}
