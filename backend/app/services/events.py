"""Event-propagation model.

The gradient-boosted forecaster in ``forecast.py`` learns the *endogenous*
behaviour of a port: level, seasonality, weekly rhythm, weather response and
how shocks decay once they are visible in the data. It cannot, and should not,
predict a security incident that has not happened yet.

Declared events are therefore *exogenous* inputs, propagated through the port
graph by this module and added on top of the statistical baseline:

    forecast = ML baseline  +  Σ (impact of each active event)

Both terms are reported separately in the API so nothing is hidden behind a
single number.

Propagation rules
-----------------
* A **port-targeted** event (congestion, weather, labour, policy) hits that
  port directly, and spills over at 25% to ports one leg downstream.
* A **chokepoint-targeted** event hits every port in proportion to how much of
  its sea service transits that chokepoint, weighting arrivals fully and
  departures at 40% — a port congests because ships pile up waiting to berth,
  not because its outbound strings are long. This is what makes Salalah the
  corridor's shock absorber: nothing *arrives* there via Bab el-Mandeb, so a Red
  Sea security event leaves its yard alone even though it relays cargo onward
  through the strait.
* Impact follows a ramp / plateau / decay profile in days since declaration.

Swap seam
---------
Replace ``load_active_events`` with a real news/AIS event feed. The propagation
maths and everything downstream stay as they are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chokepoint, Event, Leg

# Congestion-index uplift at severity 5 with full exposure.
PORT_EVENT_UPLIFT: dict[str, float] = {
    "congestion": 26.0,
    "weather": 20.0,
    "labor": 24.0,
    "security": 6.0,
    "policy": -9.0,  # relief measures pull congestion down
}
CHOKEPOINT_CONGESTION_UPLIFT = 20.0
CHOKEPOINT_RISK_AT_SEV5 = 0.92
SPILLOVER_FRACTION = 0.25

# A security episode of this kind does not blow over in a week: the plateau is
# deliberately longer than the longest departure-delay option, so "just wait a
# few days" cannot silently become the answer to everything.
RAMP_DAYS = 3.0
PLATEAU_DAYS = 16.0
DECAY_DAYS = 14.0
# A security incident overnight makes tomorrow's transit risky immediately; the
# ramp is about congestion building, not about the risk appearing from nothing.
RAMP_FLOOR = 0.4

# How far ahead the stored "current" chokepoint risk looks: the risk that
# matters is the one facing a vessel entering the strait this week.
RISK_LOOKAHEAD_DAYS = 3

# Relation between congestion index and vessel waiting days. Mirrors the data
# generator so the overlay stays consistent with the observed history.
WAITING_PIVOT = 54.0
WAITING_SCALE = 22.0


def severity_scale(severity: int) -> float:
    return float(min(max(severity, 0), 5) / 5.0) ** 1.15


def impact_profile(days_since: float) -> float:
    """Ramp in, hold, then decay. Zero before the event is declared."""
    if days_since < 0:
        return 0.0
    if days_since < RAMP_DAYS:
        return RAMP_FLOOR + (1.0 - RAMP_FLOOR) * days_since / RAMP_DAYS
    if days_since <= RAMP_DAYS + PLATEAU_DAYS:
        return 1.0
    over = days_since - RAMP_DAYS - PLATEAU_DAYS
    return max(0.0, 1.0 - over / DECAY_DAYS)


def congestion_to_waiting(congestion: float) -> float:
    """Structural waiting-days curve used to translate a congestion overlay."""
    return 0.28 + math.exp((congestion - WAITING_PIVOT) / WAITING_SCALE)


@dataclass(frozen=True)
class ActiveEvent:
    id: str
    day: date
    type: str
    severity: int
    headline: str
    port_id: str | None
    chokepoint_id: str | None


@dataclass
class PortImpact:
    congestion: float
    drivers: list[tuple[str, float]]  # (event headline, congestion points)


def load_active_events(db: Session, as_of: date, lookback_days: int = 40) -> list[ActiveEvent]:
    """Events declared on or before ``as_of`` that can still be biting."""
    rows = db.execute(
        select(Event).where(
            Event.day <= as_of,
            Event.day >= as_of - timedelta(days=lookback_days),
            Event.severity >= 3,
        )
    ).scalars()
    return [
        ActiveEvent(
            id=e.id, day=e.day, type=e.type, severity=e.severity,
            headline=e.headline, port_id=e.port_id, chokepoint_id=e.chokepoint_id,
        )
        for e in rows
    ]


@lru_cache(maxsize=8)
def _exposure_cache_key(_version: int) -> None:  # pragma: no cover - cache token
    return None


OUTBOUND_WEIGHT = 0.4


def chokepoint_exposure(db: Session) -> dict[str, dict[str, float]]:
    """``{chokepoint_id: {port_id: weighted share of its services transiting it}}``.

    Arrivals count fully, departures at ``OUTBOUND_WEIGHT``.
    """
    legs = db.execute(select(Leg).where(Leg.mode == "sea")).scalars().all()
    touching: dict[str, list[tuple[Leg, float]]] = {}
    for leg in legs:
        touching.setdefault(leg.dest_id, []).append((leg, 1.0))
        touching.setdefault(leg.origin_id, []).append((leg, OUTBOUND_WEIGHT))

    exposure: dict[str, dict[str, float]] = {}
    for port_id, weighted in touching.items():
        total = sum(w for _, w in weighted)
        if total <= 0:
            continue
        sums: dict[str, float] = {}
        for leg, w in weighted:
            for cp in leg.chokepoints or []:
                sums[cp] = sums.get(cp, 0.0) + w
        for cp, hit in sums.items():
            exposure.setdefault(cp, {})[port_id] = round(hit / total, 4)
    return exposure


def downstream_neighbours(db: Session) -> dict[str, list[str]]:
    legs = db.execute(select(Leg)).scalars().all()
    out: dict[str, list[str]] = {}
    for leg in legs:
        out.setdefault(leg.origin_id, []).append(leg.dest_id)
        out.setdefault(leg.dest_id, []).append(leg.origin_id)
    return {k: sorted(set(v)) for k, v in out.items()}


class EventOverlay:
    """Computes exogenous congestion uplift per (port, day) from active events."""

    def __init__(self, db: Session, as_of: date):
        self.as_of = as_of
        self.events = load_active_events(db, as_of)
        self.exposure = chokepoint_exposure(db)
        self.neighbours = downstream_neighbours(db)
        self._cache: dict[tuple[str, date], PortImpact] = {}

    def congestion_uplift(self, port_id: str, day: date) -> PortImpact:
        key = (port_id, day)
        if key in self._cache:
            return self._cache[key]

        total = 0.0
        drivers: list[tuple[str, float]] = []
        for ev in self.events:
            profile = impact_profile((day - ev.day).days)
            if profile <= 0:
                continue
            scale = severity_scale(ev.severity) * profile
            contribution = 0.0

            if ev.chokepoint_id:
                share = self.exposure.get(ev.chokepoint_id, {}).get(port_id, 0.0)
                contribution += CHOKEPOINT_CONGESTION_UPLIFT * scale * share

            if ev.port_id:
                base = PORT_EVENT_UPLIFT.get(ev.type, 0.0)
                if ev.port_id == port_id:
                    contribution += base * scale
                elif port_id in self.neighbours.get(ev.port_id, []):
                    contribution += base * scale * SPILLOVER_FRACTION

            if abs(contribution) >= 0.05:
                total += contribution
                drivers.append((ev.headline, round(contribution, 2)))

        drivers.sort(key=lambda d: abs(d[1]), reverse=True)
        impact = PortImpact(congestion=round(total, 2), drivers=drivers)
        self._cache[key] = impact
        return impact

    def waiting_uplift(self, baseline_congestion: float, port_id: str, day: date) -> float:
        """Translate the congestion overlay into extra waiting days."""
        uplift = self.congestion_uplift(port_id, day).congestion
        if abs(uplift) < 0.05:
            return 0.0
        before = congestion_to_waiting(baseline_congestion)
        after = congestion_to_waiting(baseline_congestion + uplift)
        return round(after - before, 3)

    def chokepoint_risk(self, db: Session, chokepoint_id: str, day: date) -> float:
        """Current transit risk 0–1 for a chokepoint on a given day."""
        cp = db.get(Chokepoint, chokepoint_id)
        base = cp.base_risk if cp else 0.05
        risk = base
        for ev in self.events:
            if ev.chokepoint_id != chokepoint_id:
                continue
            profile = impact_profile((day - ev.day).days)
            peak = CHOKEPOINT_RISK_AT_SEV5 * severity_scale(ev.severity)
            risk = max(risk, base + (1.0 - base) * peak * profile)
        return round(min(risk, 0.98), 4)
