import { describe, expect, it } from "vitest";

import { fmtDays, fmtPct, fmtTonnes, fmtUsd } from "../lib/format";
import { arcPath, boundsOf, fitAspect, makeProjection } from "../lib/geo";

describe("formatting", () => {
  it("signs money the way a trader reads it", () => {
    expect(fmtUsd(1234)).toBe("$1,234");
    expect(fmtUsd(1234, { sign: true })).toBe("+$1,234");
    expect(fmtUsd(-561, { sign: true })).toBe("−$561");
    expect(fmtUsd(0, { sign: true })).toBe("$0");
  });

  it("formats days, percentages and tonnes", () => {
    expect(fmtDays(4.25)).toBe("4.3d");
    expect(fmtDays(-2, { sign: true })).toBe("−2.0d");
    expect(fmtDays(0.01, { sign: true })).toBe("0d");
    expect(fmtPct(0.784)).toBe("78%");
    expect(fmtTonnes(0.14, { sign: true })).toBe("+0.14 t");
  });
});

describe("map projection", () => {
  const bounds = boundsOf(
    [
      { lat: -4.05, lon: 39.66 },
      { lat: 21.48, lon: 39.16 },
    ],
    5,
  );

  it("keeps both endpoints inside the viewport", () => {
    const fitted = fitAspect(bounds, 900, 380);
    const project = makeProjection(fitted, 900, 380);
    for (const [lon, lat] of [
      [39.66, -4.05],
      [39.16, 21.48],
    ] as const) {
      const [x, y] = project(lon, lat);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(900);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(380);
    }
  });

  it("puts north above south", () => {
    const project = makeProjection(fitAspect(bounds, 900, 380), 900, 380);
    expect(project(39.16, 21.48)[1]).toBeLessThan(project(39.66, -4.05)[1]);
  });

  it("emits a quadratic arc between two points", () => {
    expect(arcPath([0, 0], [100, 0])).toMatch(/^M 0\.0 0\.0 Q .* 100\.0 0\.0$/);
  });
});
