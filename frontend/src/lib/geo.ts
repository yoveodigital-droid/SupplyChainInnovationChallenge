/**
 * Coarse coastlines for the offline corridor map.
 *
 * These are deliberately low-fidelity silhouettes — enough for a viewer to
 * orient themselves between Southeast Asia, the Indian Ocean, the Gulf and East
 * Africa without shipping a basemap. When network tiles happen to be reachable
 * the app upgrades to a real Leaflet map instead; this is the guaranteed path.
 */

export type Ring = [number, number][]; // [lon, lat]

export const LANDMASSES: { id: string; ring: Ring }[] = [
  {
    id: "africa",
    ring: [
      [32.6, 31.3], [34.8, 28.6], [37.0, 24.0], [38.6, 18.0], [39.6, 15.2],
      [43.3, 12.6], [45.6, 10.6], [51.3, 11.9], [51.0, 9.0], [47.0, 4.0],
      [41.8, -1.9], [40.6, -10.0], [40.2, -16.5], [35.5, -24.0], [32.0, -28.8],
      [27.0, -33.6], [18.4, -34.3], [14.5, -22.5], [11.8, -15.0], [8.9, -1.0],
      [9.4, 4.2], [3.0, 6.4], [-2.0, 5.0], [-7.7, 4.4], [-14.0, 11.0],
      [-17.0, 15.0], [-16.0, 21.5], [-11.0, 27.0], [-6.0, 32.0], [2.0, 35.5],
      [11.0, 37.0], [20.0, 32.6], [25.0, 31.5],
    ],
  },
  {
    id: "madagascar",
    ring: [[44.0, -16.0], [48.5, -13.2], [50.5, -15.5], [50.2, -25.2], [45.2, -25.5], [43.3, -21.5]],
  },
  {
    id: "arabia",
    ring: [
      [43.3, 12.6], [45.6, 13.0], [48.5, 14.0], [52.5, 16.8], [56.4, 17.9],
      [59.8, 22.5], [57.0, 25.0], [55.0, 25.5], [51.5, 25.0], [50.0, 27.0],
      [48.0, 29.5], [43.5, 30.0], [39.0, 27.5], [35.0, 28.2], [34.5, 29.6],
      [37.2, 24.0], [39.0, 18.5], [41.0, 15.0],
    ],
  },
  {
    id: "asia-minor",
    ring: [[26.0, 36.0], [36.0, 36.5], [43.5, 37.5], [48.0, 30.0], [43.5, 30.0], [34.5, 31.5], [28.0, 40.5]],
  },
  {
    id: "india",
    ring: [
      [61.5, 25.2], [66.0, 25.5], [68.5, 23.5], [70.5, 20.8], [73.0, 16.0],
      [76.0, 9.0], [77.6, 8.1], [80.2, 13.0], [80.5, 16.5], [84.5, 19.0],
      [87.5, 21.5], [89.5, 22.0], [92.5, 21.5], [92.0, 25.5], [88.0, 27.0],
      [80.0, 28.8], [74.0, 32.5], [69.0, 27.5], [64.0, 29.5], [61.0, 29.0],
    ],
  },
  {
    id: "sri-lanka",
    ring: [[79.7, 8.0], [80.2, 9.8], [81.9, 7.5], [81.2, 6.0], [80.0, 5.9]],
  },
  {
    id: "indochina",
    ring: [
      [92.5, 21.5], [95.0, 17.0], [98.0, 13.0], [100.0, 13.5], [100.6, 8.0],
      [103.5, 1.4], [104.5, 1.6], [105.0, 8.7], [107.5, 10.4], [109.3, 13.0],
      [109.5, 18.0], [107.0, 21.0], [104.0, 22.5], [98.5, 24.0], [95.0, 26.5],
    ],
  },
  {
    id: "china",
    ring: [
      [104.0, 22.5], [108.5, 21.5], [113.5, 22.2], [118.0, 24.5], [121.5, 29.0],
      [122.2, 31.5], [120.5, 34.5], [122.0, 39.5], [117.5, 39.0], [110.0, 38.0],
      [104.0, 34.0], [100.0, 28.0], [101.5, 24.0],
    ],
  },
  {
    id: "sumatra",
    ring: [[95.3, 5.6], [98.6, 3.8], [103.0, -0.8], [105.9, -5.9], [104.5, -5.9], [100.3, -2.4], [95.3, 2.0]],
  },
  {
    id: "borneo-java",
    ring: [
      [105.5, -6.0], [110.0, -6.9], [114.6, -8.5], [110.0, -8.2], [106.0, -6.5],
      [109.0, -3.0], [117.5, -3.9], [119.0, 0.5], [117.0, 4.3], [110.0, 2.0],
      [108.9, -1.5],
    ],
  },
];

export interface Bounds {
  minLon: number;
  maxLon: number;
  minLat: number;
  maxLat: number;
}

export const CORRIDOR_BOUNDS: Bounds = {
  minLon: 14,
  maxLon: 126,
  minLat: -37,
  maxLat: 42,
};

export function boundsOf(points: { lat: number; lon: number }[], padding = 6): Bounds {
  if (points.length === 0) return CORRIDOR_BOUNDS;
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  return {
    minLon: Math.min(...lons) - padding,
    maxLon: Math.max(...lons) + padding,
    minLat: Math.min(...lats) - padding,
    maxLat: Math.max(...lats) + padding,
  };
}

/**
 * Frame the viewport around a set of points at a single, undistorted scale.
 *
 * Padding the bounding box and then forcing the viewport aspect ratio zooms a
 * tall, narrow route (Mombasa–Jeddah is 25° of latitude and half a degree of
 * longitude) all the way out to a hemisphere. Instead: pick one degrees-per-
 * pixel scale that leaves the points occupying `fill` of each axis, then centre
 * the viewport on them. Extra ocean appears on the wide axis, which is fine;
 * the route stays legible, which is the point.
 */
export function frameAround(
  points: { lat: number; lon: number }[],
  width: number,
  height: number,
  fillX = 0.62,
  fillY = 0.66,
): Bounds {
  if (points.length === 0) return CORRIDOR_BOUNDS;
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  const spanLon = Math.max(Math.max(...lons) - Math.min(...lons), 1.5);
  const spanLat = Math.max(Math.max(...lats) - Math.min(...lats), 1.5);
  const centreLon = (Math.max(...lons) + Math.min(...lons)) / 2;
  const centreLat = (Math.max(...lats) + Math.min(...lats)) / 2;

  // Pixels per degree, limited by whichever axis is tighter.
  const scale = Math.min((width * fillX) / spanLon, (height * fillY) / spanLat);
  const halfLon = width / scale / 2;
  const halfLat = height / scale / 2;
  return {
    minLon: centreLon - halfLon,
    maxLon: centreLon + halfLon,
    minLat: centreLat - halfLat,
    maxLat: centreLat + halfLat,
  };
}

/** Grow bounds so the drawn area matches the viewport aspect ratio. */
export function fitAspect(bounds: Bounds, width: number, height: number): Bounds {
  const target = width / height;
  let { minLon, maxLon, minLat, maxLat } = bounds;
  const spanLon = maxLon - minLon;
  const spanLat = maxLat - minLat;
  const current = spanLon / spanLat;
  if (current < target) {
    const needed = spanLat * target;
    const pad = (needed - spanLon) / 2;
    minLon -= pad;
    maxLon += pad;
  } else {
    const needed = spanLon / target;
    const pad = (needed - spanLat) / 2;
    minLat -= pad;
    maxLat += pad;
  }
  return { minLon, maxLon, minLat, maxLat };
}

export function makeProjection(bounds: Bounds, width: number, height: number) {
  const spanLon = bounds.maxLon - bounds.minLon;
  const spanLat = bounds.maxLat - bounds.minLat;
  return (lon: number, lat: number): [number, number] => [
    ((lon - bounds.minLon) / spanLon) * width,
    height - ((lat - bounds.minLat) / spanLat) * height,
  ];
}

/** A gently bowed path between two points — reads as a sailing route. */
export function arcPath(
  [x1, y1]: [number, number],
  [x2, y2]: [number, number],
  bow = 0.14,
): string {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const cx = mx - dy * bow;
  const cy = my + dx * bow;
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}
