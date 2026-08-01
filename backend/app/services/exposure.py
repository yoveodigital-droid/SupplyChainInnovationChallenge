"""Exposure service — turns port forecasts into what a shipment actually loses.

For a given plan (route + departure date + cargo) it walks the legs against the
forecast and returns:

* expected additional delay in days, with a p10–p90 range
* probability of a >3-day and a >7-day delay
* estimated demurrage in USD (delay beyond free days × port rate × TEU)
* spoilage probability for perishables (delay distribution vs remaining shelf life)

Modelling choices, stated plainly
---------------------------------
* Each port call contributes ``service_factor × max(0, forecast waiting −
  the port's normal waiting)``. The service factor encodes berth priority: a
  small feeder queues behind mainline vessels at a congested port, a truck
  barely queues at all.
* Each chokepoint transit contributes ``risk × delay-at-max-risk`` days.
* At transshipment points there is a connection risk: schedules carry about a
  day and a half of planned slack, and beyond that the later you arrive the
  more likely you miss the onward sailing and wait a full service interval.
* Headline risk is the probability of missing the *buyer's* deadline, not a
  fixed number of days. Three days late matters very differently on a 6-day
  Mombasa–Jeddah run and a 22-day Shanghai–Jeddah run, and a risk badge that
  ignores that just tells a forwarder their long routes are always red.
* Contributions are treated as independent and summed as normals. That
  understates tail correlation in a real network and is called out in the
  README as a known simplification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import RISK_AMBER, RISK_RED, SPOILAGE_AMBER, SPOILAGE_RED
from ..models import Chokepoint, Port
from .forecast import PortForecaster, _normal_cdf
from .graph import LegView

# Berth priority by calling service. A small feeder queues behind mainline
# vessels at a congested port; a truck barely queues at all.
# A road leg ends at the consignee's door, not in a berth queue, so it
# carries no port-congestion delay at its destination.
SERVICE_FACTOR = {"mainline": 0.85, "feeder": 1.35, "truck": 0.0}

# A hub running a declared priority-relay programme (a policy event in the
# feed) sells contracted berth windows at the receiving port and waives
# connection waiting. This is the mechanism that makes a transshipment reroute
# genuinely faster through a congested port, not just a longer way round.
PRIORITY_RELAY_FACTOR = 0.55
Z80 = 2.5631
Z10, Z90 = -1.2816, 1.2816

# Perishables rarely become a total loss; this is the assumed value destroyed
# when a consignment arrives past its shelf life.
SPOILAGE_LOSS_FRACTION = 0.62

# Planned slack built into a transshipment connection before a delay starts
# threatening the onward sailing.
CONNECTION_SLACK_DAYS = 1.5


@dataclass
class CallExposure:
    port_id: str
    port_name: str
    port_short_name: str
    day: date
    role: str  # load | transship | discharge
    service: str
    forecast_congestion: float
    forecast_waiting: float
    normal_waiting: float
    delay_days: float
    delay_sigma: float
    disruption_probability: float
    confidence: float
    risk_level: str


@dataclass
class LegExposure:
    leg_id: str
    origin_id: str
    dest_id: str
    mode: str
    service: str
    depart: date
    arrive: date
    transit_days: float
    chokepoints: list[str]
    chokepoint_risk: float
    chokepoint_delay_days: float
    connection_delay_days: float
    risk_level: str


@dataclass
class Exposure:
    etd: date
    scheduled_transit_days: float
    scheduled_arrival: date
    expected_delay_days: float
    delay_p10: float
    delay_p90: float
    delay_sigma: float
    expected_arrival: date
    prob_delay_over_3: float
    prob_delay_over_7: float
    prob_miss_deadline: float
    demurrage_usd: float
    demurrage_days: float
    spoilage_probability: float | None
    spoilage_band: str | None
    expected_spoilage_loss_usd: float
    risk_score: float
    risk_level: str
    confidence: float
    calls: list[CallExposure] = field(default_factory=list)
    legs: list[LegExposure] = field(default_factory=list)
    drivers: list[dict] = field(default_factory=list)


@dataclass
class Plan:
    """A shipment plan the exposure engine can price — real or hypothetical."""

    legs: list[LegView]
    etd: date
    teu: float
    perishable: bool = False
    shelf_life_days: int | None = None
    value_usd: float = 0.0
    # Latest arrival the buyer accepts. Drives the headline risk band.
    required_by: date | None = None


def _band(probability: float, amber: float, red: float) -> str:
    if probability >= red:
        return "red"
    if probability >= amber:
        return "amber"
    return "green"


def _expected_excess(mu: float, sigma: float, threshold: float) -> float:
    """E[max(0, X - threshold)] for X ~ Normal(mu, sigma)."""
    sigma = max(sigma, 1e-6)
    z = (threshold - mu) / sigma
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return max(0.0, sigma * pdf + (mu - threshold) * (1.0 - _normal_cdf(z)))


def _tail(mu: float, sigma: float, threshold: float) -> float:
    sigma = max(sigma, 1e-6)
    return round(min(max(1.0 - _normal_cdf((threshold - mu) / sigma), 0.0), 1.0), 4)


class ExposureEngine:
    """Bound to a forecaster (i.e. to one simulated 'today')."""

    def __init__(self, db: Session, forecaster: PortForecaster):
        self.db = db
        self.fc = forecaster
        self.ports = {p.id: p for p in db.execute(select(Port)).scalars()}
        self._chokepoints = {c.id: c for c in db.execute(select(Chokepoint)).scalars()}
        # Hubs currently running a declared priority-relay programme.
        self.priority_hubs = {
            ev.port_id
            for ev in forecaster.overlay.events
            if ev.type == "policy" and ev.severity >= 3 and ev.port_id
        }

    # ---------------------------------------------------------------- calls --
    def _call(
        self, port_id: str, day: date, role: str, service: str, priority_relay: bool = False
    ) -> CallExposure:
        port = self.ports[port_id]
        point = self.fc.point(port_id, day)
        factor = SERVICE_FACTOR.get(service, 1.0)
        if priority_relay:
            factor = min(factor, PRIORITY_RELAY_FACTOR)
        excess = max(0.0, point.waiting_days - port.base_waiting_days)
        delay = factor * excess
        spread = max(point.waiting_high - point.waiting_low, 0.15)
        sigma = factor * spread / Z80
        return CallExposure(
            port_id=port_id,
            port_name=port.name,
            port_short_name=port.short_name or port.name,
            day=day,
            role=role,
            service=service,
            forecast_congestion=point.congestion,
            forecast_waiting=round(point.waiting_days * factor, 2),
            normal_waiting=round(port.base_waiting_days * factor, 2),
            delay_days=round(delay, 2),
            delay_sigma=round(sigma, 3),
            disruption_probability=point.disruption_probability,
            confidence=point.confidence,
            risk_level=_band(point.disruption_probability, RISK_AMBER, RISK_RED),
        )

    # ------------------------------------------------------------ evaluation --
    def evaluate(self, plan: Plan) -> Exposure:
        legs = plan.legs
        if not legs:
            raise ValueError("a plan needs at least one leg")

        cursor = plan.etd
        mu_total = 0.0
        var_total = 0.0
        calls: list[CallExposure] = []
        leg_rows: list[LegExposure] = []
        confidences: list[float] = []
        drivers: list[dict] = []

        # Loading port.
        load_call = self._call(legs[0].origin_id, cursor, "load", legs[0].service)
        calls.append(load_call)
        mu_total += load_call.delay_days
        var_total += load_call.delay_sigma ** 2
        confidences.append(load_call.confidence)
        if load_call.delay_days >= 0.4:
            drivers.append({
                "kind": "port",
                "label": f"Congestion at {load_call.port_name} on loading",
                "days": round(load_call.delay_days, 2),
            })

        for i, leg in enumerate(legs):
            depart = cursor + timedelta(days=round(mu_total))
            arrive_scheduled = cursor + timedelta(days=math.ceil(leg.transit_days))

            # Chokepoint transit risk.
            cp_delay = 0.0
            cp_risk = 0.0
            for cp_id in leg.chokepoints:
                cp = self._chokepoints.get(cp_id)
                if cp is None:
                    continue
                risk = self.fc.overlay.chokepoint_risk(self.db, cp_id, depart)
                contribution = risk * cp.delay_days_at_max_risk
                cp_delay += contribution
                cp_risk = max(cp_risk, risk)
                if contribution >= 0.4:
                    drivers.append({
                        "kind": "chokepoint",
                        "label": f"{cp.name} transit risk",
                        "days": round(contribution, 2),
                    })
            mu_total += cp_delay
            var_total += (0.65 * cp_delay) ** 2

            # Connection risk at a transshipment point. A declared priority
            # relay at the hub waives it.
            conn_delay = 0.0
            priority_relay = leg.origin_id in self.priority_hubs and i > 0
            if i > 0 and not priority_relay:
                gap_days = 7.0 / max(leg.sailings_per_week, 0.5)
                p_miss = min(max((mu_total - CONNECTION_SLACK_DAYS) / 4.0, 0.0), 0.75)
                conn_delay = p_miss * gap_days
                mu_total += conn_delay
                var_total += p_miss * (1 - p_miss) * gap_days ** 2
                if conn_delay >= 0.4:
                    drivers.append({
                        "kind": "connection",
                        "label": f"Risk of missing the onward sailing at {self.ports[leg.origin_id].name}",
                        "days": round(conn_delay, 2),
                    })

            cursor = cursor + timedelta(days=math.ceil(leg.transit_days))

            role = "discharge" if i == len(legs) - 1 else "transship"
            call = self._call(leg.dest_id, cursor, role, leg.service, priority_relay=priority_relay)
            calls.append(call)
            mu_total += call.delay_days
            var_total += call.delay_sigma ** 2
            confidences.append(call.confidence)
            if call.delay_days >= 0.4:
                drivers.append({
                    "kind": "port",
                    "label": f"Congestion at {call.port_name} on arrival",
                    "days": round(call.delay_days, 2),
                })

            leg_rows.append(
                LegExposure(
                    leg_id=leg.id,
                    origin_id=leg.origin_id,
                    dest_id=leg.dest_id,
                    mode=leg.mode,
                    service=leg.service,
                    depart=depart,
                    arrive=arrive_scheduled,
                    transit_days=leg.transit_days,
                    chokepoints=list(leg.chokepoints),
                    chokepoint_risk=round(cp_risk, 3),
                    chokepoint_delay_days=round(cp_delay, 2),
                    connection_delay_days=round(conn_delay, 2),
                    risk_level=_band(
                        min(1.0, (cp_delay + conn_delay + call.delay_days) / 8.0),
                        RISK_AMBER,
                        RISK_RED,
                    ),
                )
            )

        # Carriers publish one end-to-end transit, not a sum of rounded legs.
        scheduled_transit = math.ceil(sum(leg.transit_days for leg in legs))
        scheduled_arrival = plan.etd + timedelta(days=scheduled_transit)
        sigma = math.sqrt(max(var_total, 0.04))

        p_over_3 = _tail(mu_total, sigma, 3.0)
        p_over_7 = _tail(mu_total, sigma, 7.0)

        dest_port = self.ports[legs[-1].dest_id]
        demurrage_days = _expected_excess(mu_total, sigma, float(dest_port.free_days))
        demurrage = demurrage_days * dest_port.demurrage_usd_per_teu_day * plan.teu

        spoilage_prob: float | None = None
        spoilage_band: str | None = None
        spoilage_loss = 0.0
        if plan.perishable and plan.shelf_life_days:
            slack = plan.shelf_life_days - scheduled_transit
            spoilage_prob = _tail(mu_total, sigma, float(slack))
            spoilage_band = _band(spoilage_prob, SPOILAGE_AMBER, SPOILAGE_RED)
            spoilage_loss = spoilage_prob * plan.value_usd * SPOILAGE_LOSS_FRACTION

        # Headline risk: the chance of actually missing the buyer's deadline,
        # or of the cargo spoiling — whichever is worse. Falls back to the
        # 3-day rule only when no deadline is known.
        if plan.required_by is not None:
            deadline_slack = (plan.required_by - scheduled_arrival).days
            schedule_risk = _tail(mu_total, sigma, float(deadline_slack))
        else:
            schedule_risk = p_over_3
        risk_score = max(schedule_risk, spoilage_prob or 0.0)
        risk_level = _band(risk_score, RISK_AMBER, RISK_RED)

        drivers.sort(key=lambda d: d["days"], reverse=True)

        return Exposure(
            etd=plan.etd,
            scheduled_transit_days=float(scheduled_transit),
            scheduled_arrival=scheduled_arrival,
            expected_delay_days=round(mu_total, 2),
            delay_p10=round(max(mu_total + Z10 * sigma, 0.0), 2),
            delay_p90=round(mu_total + Z90 * sigma, 2),
            delay_sigma=round(sigma, 3),
            expected_arrival=scheduled_arrival + timedelta(days=round(mu_total)),
            prob_delay_over_3=p_over_3,
            prob_delay_over_7=p_over_7,
            prob_miss_deadline=round(schedule_risk, 4),
            demurrage_usd=round(demurrage, 2),
            demurrage_days=round(demurrage_days, 2),
            spoilage_probability=spoilage_prob,
            spoilage_band=spoilage_band,
            expected_spoilage_loss_usd=round(spoilage_loss, 2),
            risk_score=round(risk_score, 4),
            risk_level=risk_level,
            confidence=round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
            calls=calls,
            legs=leg_rows,
            drivers=drivers[:5],
        )

    def delay_distribution(self, exposure: Exposure, bins: int = 13) -> list[dict]:
        """Discrete delay-day distribution for the dashboard chart."""
        mu, sigma = exposure.expected_delay_days, max(exposure.delay_sigma, 0.4)
        out = []
        for d in range(bins):
            lo, hi = d - 0.5, d + 0.5
            if d == 0:
                lo = -50.0
            p = _normal_cdf((hi - mu) / sigma) - _normal_cdf((lo - mu) / sigma)
            out.append({"days": d, "probability": round(max(p, 0.0), 4)})
        tail = 1.0 - sum(b["probability"] for b in out)
        if tail > 0.0005:
            out.append({"days": bins, "probability": round(tail, 4), "plus": True})
        return out
