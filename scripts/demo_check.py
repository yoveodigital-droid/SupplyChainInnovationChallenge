#!/usr/bin/env python3
"""Replay the scripted demo (§7) against a running API and print every beat.

Run it before walking on stage:

    make demo-check          # or: python scripts/demo_check.py

It asserts the same things the pytest suite does, but against the live server
the presenter is about to use, and it leaves the world in its seed state.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections import Counter

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
AMINA = "SHP-AMN-001"

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
failures: list[str] = []


def call(path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = f"{GREEN}✓{OFF}" if ok else f"{RED}✗{OFF}"
    print(f"  {mark} {label}" + (f"  {DIM}{detail}{OFF}" if detail else ""))
    if not ok:
        failures.append(label)


def step(n: int, title: str) -> None:
    print(f"\n{BOLD}{n}. {title}{OFF}")


def main() -> int:
    try:
        call("/health")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"{RED}Cannot reach {BASE} — start the backend with `make dev`.{OFF}\n  {exc}")
        return 2

    print(f"{BOLD}PortPulse scripted demo check{OFF}  {DIM}{BASE}{OFF}")

    step(0, "Reset to seed state")
    state = call("/demo/reset", "POST")
    check("clock back at the seed date", state["days_advanced"] == 0, state["sim_date"])
    check("scenario inactive", state["scenario_active"] is False)

    step(1, "Seed state is calm")
    ships = call("/shipments")
    check("every shipment green", all(s["risk_level"] == "green" for s in ships), f"{len(ships)} shipments")
    amina = call(f"/shipments/{AMINA}")
    check("Amina's mangoes on track", amina["risk_level"] == "green")
    calm = call(f"/shipments/{AMINA}/alert")
    check("phone shows an all-clear", calm["risk_level"] == "green", f"{calm['alert_chars']} chars")

    step(2, "Presenter triggers the scenario, then advances one day")
    call("/demo/trigger", "POST")
    state = call("/demo/advance", "POST")
    check("scenario running", state["scenario_active"] and state["scenario_day"] == 1, state["sim_date"])

    step(3, "Amina flips red")
    amina = call(f"/shipments/{AMINA}")
    check("risk is red", amina["risk_level"] == "red", f"score {amina['risk_score']:.0%}")
    check(
        "spoilage risk HIGH",
        (amina["spoilage_probability"] or 0) > 0.5,
        f"{amina['spoilage_probability']:.0%}",
    )

    step(4, "The alert reaches her phone")
    alert = call(f"/shipments/{AMINA}/alert")
    check("fits one message", alert["within_limit"], f"{alert['alert_chars']} chars")
    check("mentions Salalah", "Salalah" in alert["alert_text"])
    swahili = call(f"/shipments/{AMINA}/alert?lang=sw")
    check("Swahili version available", swahili["within_limit"] and swahili["language"] == "sw",
          f"{swahili['alert_chars']} chars")
    print(f"    {DIM}{alert['alert_text']}{OFF}")

    step(5, "Recommendations")
    options = call(f"/shipments/{AMINA}/recommendations")["options"]
    top = next(o for o in options if o["rank"] == 1)
    check("top option reroutes via Salalah", "Salalah" in top["label"] and top["kind"] != "hold")
    check("hold is present and quantified", any(o["kind"] == "hold" for o in options))
    check("top option cuts risk days", top["delta_risk_days"] > 1, f"{top['delta_risk_days']:.1f} d")
    for o in options:
        print(f"    {DIM}#{o['rank']} {o['label'][:74]}{OFF}")

    step(6, "Rafael's portfolio")
    rafael = call("/shipments?persona=rafael")
    counts = Counter(s["risk_level"] for s in rafael)
    flagged = counts["amber"] + counts["red"]
    check("3 of 8 bookings flagged", len(rafael) == 8 and flagged == 3, dict(counts))

    step(7, "Jeddah sees the inbound wave")
    pressure = call("/ports/SAJED/pressure")
    check(
        "forecast crosses the disruption threshold",
        pressure["peak_congestion"] > pressure["port"]["congestion_threshold"],
        f"peak {pressure['peak_congestion']:.0f} vs {pressure['port']['congestion_threshold']:.0f}",
    )
    check("live events in the upstream feed", any(e["scenario"] for e in pressure["upstream_events"]))

    step(8, "Amina accepts the recommendation")
    accepted = call(f"/shipments/{AMINA}/accept", "POST", {"option_id": top["id"]})
    check("route changed", accepted["shipment"]["leg_ids"] == top["leg_ids"],
          " → ".join(accepted["shipment"]["leg_ids"]))
    check("risk improved", accepted["shipment"]["risk_score"] < amina["risk_score"],
          f"{amina['risk_score']:.0%} → {accepted['shipment']['risk_score']:.0%}")
    print(f"    {DIM}{accepted['message']['text']}{OFF}")

    step(9, "Reset for the next run")
    call("/demo/reset", "POST")
    check("Amina green again", call(f"/shipments/{AMINA}")["risk_level"] == "green")

    print()
    if failures:
        print(f"{RED}{len(failures)} check(s) failed:{OFF} " + "; ".join(failures))
        return 1
    print(f"{GREEN}All checks passed — the scripted demo is ready.{OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
