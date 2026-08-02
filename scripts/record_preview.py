#!/usr/bin/env python3
"""Record the live API into a fixture bundle for the hosted preview.

The published preview runs with no network access, so it replays real responses
instead of calling the backend. This script drives a running API through the
scripted demo and captures every read the UI performs at each step.

    make preview        # records, builds and inlines everything
    python scripts/record_preview.py [api-base] [output.json]

Output is a single JSON file consumed by `frontend/src/api/fixtures.ts`.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "frontend/src/preview-fixtures.json")

# Recorded worlds, in the order the presenter reaches them. Each is described by
# the demo actions needed to get there from a fresh reset.
STATES: dict[str, list[str]] = {
    "seed": [],
    "triggered": ["trigger"],
    "day1": ["trigger", "advance"],
    "day2": ["trigger", "advance", "advance"],
}

TRANSITIONS: dict[str, dict[str, str]] = {
    "seed": {"trigger": "triggered", "advance": "seed_day1", "reset": "seed"},
    "triggered": {"advance": "day1", "reset": "seed"},
    "day1": {"advance": "day2", "reset": "seed"},
    "day2": {"reset": "seed"},
}

# Advancing before triggering is a plausible click; record that branch too.
STATES["seed_day1"] = ["advance"]
TRANSITIONS["seed_day1"] = {"trigger": "day1", "reset": "seed"}

AMINA = "SHP-AMN-001"
LANGS = ("en", "sw")
FLOAT_DP = 4


def call(path: str, method: str = "GET", body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def shrink(value: Any) -> Any:
    """Round floats. Over a megabyte of recorded JSON, the tail digits are pure
    weight — nothing in the UI shows more than two decimal places."""
    if isinstance(value, float):
        rounded = round(value, FLOAT_DP)
        return int(rounded) if rounded == int(rounded) else rounded
    if isinstance(value, dict):
        return {k: shrink(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shrink(v) for v in value]
    return value


def goto(actions: list[str]) -> None:
    call("/demo/reset", "POST")
    for action in actions:
        call(f"/demo/{action}", "POST")


def shipment_reads(shipment_id: str, full_langs: bool) -> dict[str, Any]:
    reads = {
        f"/shipments/{shipment_id}": call(f"/shipments/{shipment_id}"),
        f"/shipments/{shipment_id}/exposure": call(f"/shipments/{shipment_id}/exposure"),
        f"/shipments/{shipment_id}/recommendations": call(
            f"/shipments/{shipment_id}/recommendations"
        ),
    }
    for lang in LANGS if full_langs else ("en",):
        reads[f"/shipments/{shipment_id}/alert?lang={lang}"] = call(
            f"/shipments/{shipment_id}/alert?lang={lang}"
        )
    return reads


def capture_state() -> dict[str, Any]:
    """Every read the three views perform for the current world."""
    reads: dict[str, Any] = {
        "/demo/state": call("/demo/state"),
        "/meta": call("/meta"),
        "/ports": call("/ports"),
        "/chokepoints": call("/chokepoints"),
        "/events?limit=25": call("/events?limit=25"),
        "/shipments": call("/shipments"),
        "/ports/SAJED/pressure?horizon=14&history_days=60": call(
            "/ports/SAJED/pressure?horizon=14&history_days=60"
        ),
    }
    for persona in ("amina", "rafael", "jeddah_pa"):
        reads[f"/shipments?persona={persona}"] = call(f"/shipments?persona={persona}")

    for shipment in reads["/shipments"]:
        reads.update(shipment_reads(shipment["id"], full_langs=shipment["id"] == AMINA))
    return reads


def capture_accepts(state_key: str, actions: list[str]) -> dict[str, Any]:
    """For each shipment, what accepting its top recommendation returns, plus the
    reads that become stale as a result."""
    out: dict[str, Any] = {}
    goto(actions)
    shipments = call("/shipments")

    for shipment in shipments:
        shipment_id = shipment["id"]
        options = call(f"/shipments/{shipment_id}/recommendations")["options"]
        top = next((o for o in options if o["rank"] == 1 and o["kind"] != "hold"), None)
        if top is None:
            continue  # nothing to apply: holding is already the best plan

        goto(actions)
        response = call(
            f"/shipments/{shipment_id}/accept", "POST", {"option_id": top["id"]}
        )
        patch: dict[str, Any] = {
            "/shipments": call("/shipments"),
            f"/shipments?persona={shipment['persona_id']}": call(
                f"/shipments?persona={shipment['persona_id']}"
            ),
        }
        patch.update(shipment_reads(shipment_id, full_langs=shipment_id == AMINA))
        out[f"{state_key}|{shipment_id}"] = {
            "response": response,
            "patch": patch,
            "option_id": top["id"],
        }

    goto(actions)
    return out


def main() -> int:
    try:
        call("/health")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Cannot reach {BASE} — start the backend first (`make api`).\n  {exc}")
        return 2

    states: dict[str, Any] = {}
    accepts: dict[str, Any] = {}

    for key, actions in STATES.items():
        print(f"  recording {key} …", flush=True)
        goto(actions)
        states[key] = capture_state()
        accepts.update(capture_accepts(key, actions))

    # Hoist anything identical across every state into a shared block.
    shared: dict[str, Any] = {}
    first = next(iter(states.values()))
    for path in list(first):
        values = [json.dumps(state[path], sort_keys=True) for state in states.values()]
        if len(set(values)) == 1:
            shared[path] = first[path]
            for state in states.values():
                del state[path]
    shared["/legs"] = call("/legs")
    shared["/personas"] = call("/personas")

    bundle = shrink(
        {
            "version": 1,
            "generated_at": call("/demo/state")["seed_date"],
            "initial": "seed",
            "shared": shared,
            "states": states,
            "transitions": TRANSITIONS,
            "accepts": accepts,
        }
    )

    call("/demo/reset", "POST")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, separators=(",", ":")))
    size_kb = OUT.stat().st_size / 1024
    print(
        f"\nWrote {OUT} — {size_kb:,.0f} KB, {len(states)} states, "
        f"{len(accepts)} recorded decisions, {len(shared)} shared reads."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
