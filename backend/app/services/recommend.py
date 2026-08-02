"""Recommendation engine — the prescribe half of predict / personalise / prescribe.

Given a shipment, it enumerates real alternatives, prices each one end to end,
and ranks them.

Candidate generation
--------------------
1. K fastest routes through the port graph (alternative transshipment hubs,
   alternative discharge ports with a land leg, the Cape swing where one
   exists), plus the shipment's current route.
2. Departure options: as booked, or +3 / +5 / +7 days.
3. "Hold current plan" is always present as an explicit, quantified option.

Scoring
-------
Every candidate is priced as **expected total landed cost**:

    freight + demurrage + expected spoilage loss
           + late-delivery penalty + inventory holding + carbon

Money is the only unit in which a mango exporter's spoilage risk and a
forwarder's demurrage bill can be compared, and it is what makes the engine
cargo-aware without hand-tuned persona weights: for perishables the spoilage
term dominates by itself.

The four headline trade-off criteria (Δcost, Δtransit, Δrisk-days, ΔCO2) are
reported separately, and any alternative that is dominated on all four by
another shown option is pruned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Port, Shipment
from .exposure import Exposure, ExposureEngine, Plan
from .graph import LegView, candidate_routes, load_legs, route_nodes, route_totals

# --- economic assumptions, all in one place so a reviewer can argue with them ---
CARBON_PRICE_USD_PER_TONNE = 95.0
HOLDING_COST_RATE_PER_DAY = 0.00045  # ~16%/yr working-capital cost of cargo value
# Contractual penalty per day past ``required_by``, as a share of cargo value.
# Fresh-produce contracts are written against a market week, so lateness costs
# an exporter far more than it costs a machinery importer.
LATE_PENALTY_RATE_PER_DAY = {"perishable": 0.020, "dry": 0.008}
LATE_PENALTY_CAP = 0.25  # never more than 25% of cargo value

DEPARTURE_OPTIONS = (0, 3, 5, 7)
# A harvest-linked perishable booking cannot slip a week: the fruit is already
# picked and the packhouse slot is fixed. Three days is the realistic ceiling.
PERISHABLE_DEPARTURE_OPTIONS = (0, 3)
MAX_ALTERNATIVES = 3
DOMINANCE_EPSILON = {"cost": 25.0, "transit": 0.4, "risk": 0.25, "co2": 0.02}


@dataclass
class CostBreakdown:
    freight_usd: float
    demurrage_usd: float
    spoilage_loss_usd: float
    late_penalty_usd: float
    holding_usd: float
    carbon_usd: float
    total_usd: float


@dataclass
class Option:
    id: str
    kind: str  # hold | reroute | delay | reroute_delay
    label: str
    summary: str
    rationale: str
    leg_ids: list[str]
    route_ports: list[str]
    route_port_names: list[str]
    via: list[str]
    etd: date
    departure_delay_days: int
    scheduled_transit_days: float
    scheduled_arrival: date
    expected_arrival: date
    required_by: date
    days_late: float
    # Four headline trade-off criteria, all relative to "hold current plan".
    delta_cost_usd: float
    delta_transit_days: float
    delta_risk_days: float
    delta_co2_tonnes: float
    # Absolutes
    freight_usd: float
    co2_tonnes: float
    expected_delay_days: float
    prob_delay_over_3: float
    prob_delay_over_7: float
    prob_miss_deadline: float
    demurrage_usd: float
    spoilage_probability: float | None
    spoilage_band: str | None
    risk_level: str
    confidence: float
    costs: CostBreakdown
    savings_usd: float
    score: float
    rank: int = 0
    recommended: bool = False
    dominated_by: str | None = None
    caveats: list[str] = field(default_factory=list)
    exposure: Exposure | None = None


def _fmt_date(d: date) -> str:
    return d.strftime("%-d %b") if hasattr(d, "strftime") else str(d)


def _price(
    plan: Plan,
    exposure: Exposure,
    route: list[LegView],
    required_by: date,
    reference_day: date,
) -> tuple[CostBreakdown, float]:
    totals = route_totals(route)
    freight = totals["cost_per_teu"] * plan.teu
    co2 = totals["co2_tonnes_per_teu"] * plan.teu

    days_late = max(0.0, (exposure.expected_arrival - required_by).days)
    penalty_rate = LATE_PENALTY_RATE_PER_DAY["perishable" if plan.perishable else "dry"]
    late_penalty = min(
        days_late * penalty_rate * plan.value_usd,
        LATE_PENALTY_CAP * plan.value_usd,
    )
    holding_days = max(0.0, (exposure.expected_arrival - reference_day).days)
    holding = holding_days * HOLDING_COST_RATE_PER_DAY * plan.value_usd
    carbon = co2 * CARBON_PRICE_USD_PER_TONNE

    total = (
        freight
        + exposure.demurrage_usd
        + exposure.expected_spoilage_loss_usd
        + late_penalty
        + holding
        + carbon
    )
    return (
        CostBreakdown(
            freight_usd=round(freight, 2),
            demurrage_usd=round(exposure.demurrage_usd, 2),
            spoilage_loss_usd=round(exposure.expected_spoilage_loss_usd, 2),
            late_penalty_usd=round(late_penalty, 2),
            holding_usd=round(holding, 2),
            carbon_usd=round(carbon, 2),
            total_usd=round(total, 2),
        ),
        days_late,
    )


def _label(
    route: list[LegView],
    current_ids: list[str],
    delay: int,
    etd: date,
    names: dict[str, str],
) -> tuple[str, list[str]]:
    nodes = route_nodes(route)
    via = nodes[1:-1]
    same_route = [leg.id for leg in route] == current_ids
    if same_route and delay == 0:
        return "Hold current plan", via
    if same_route:
        return f"Depart {_fmt_date(etd)} (+{delay} days), same routing", via
    if route[-1].mode == "land":
        hubs = [names[n] for n in nodes[1:-2]]
        prefix = ("via " + " + ".join(hubs) + ", ") if hubs else ""
        via_text = f"{prefix}discharge at {names[nodes[-2]]}, road to {names[nodes[-1]]}"
    elif via:
        via_text = "via " + " + ".join(names[n] for n in via)
    else:
        via_text = "direct sailing"
    if delay == 0:
        return f"Reroute {via_text}", via
    return f"Depart {_fmt_date(etd)} (+{delay} days) {via_text}", via


def _dominates(a: Option, b: Option) -> bool:
    """True when ``a`` is at least as good as ``b`` on all four criteria and
    strictly better (beyond a tolerance) on at least one."""
    eps = DOMINANCE_EPSILON
    not_worse = (
        a.delta_cost_usd <= b.delta_cost_usd + eps["cost"]
        and a.delta_transit_days <= b.delta_transit_days + eps["transit"]
        and a.delta_risk_days >= b.delta_risk_days - eps["risk"]
        and a.delta_co2_tonnes <= b.delta_co2_tonnes + eps["co2"]
    )
    strictly_better = (
        a.delta_cost_usd < b.delta_cost_usd - eps["cost"]
        or a.delta_transit_days < b.delta_transit_days - eps["transit"]
        or a.delta_risk_days > b.delta_risk_days + eps["risk"]
        or a.delta_co2_tonnes < b.delta_co2_tonnes - eps["co2"]
    )
    return not_worse and strictly_better


def _rationale(option: Option, hold: Option, perishable: bool) -> str:
    if option.kind == "hold":
        if option.risk_level == "green":
            return (
                f"Your booking looks fine: {int(option.prob_delay_over_3 * 100)}% chance of "
                f"losing more than 3 days, no demurrage expected."
            )
        pieces = [f"{int(option.prob_delay_over_3 * 100)}% chance of a 3-day-plus delay"]
        if option.spoilage_probability:
            pieces.append(f"{int(option.spoilage_probability * 100)}% spoilage risk")
        if option.demurrage_usd >= 50:
            pieces.append(f"about ${option.demurrage_usd:,.0f} in demurrage")
        return "Keeping the booking as it stands means " + ", ".join(pieces) + "."

    bits: list[str] = []
    if option.delta_risk_days >= 0.5:
        bits.append(f"cuts expected delay by {option.delta_risk_days:.1f} days")
    elif option.delta_risk_days <= -0.5:
        bits.append(f"adds {abs(option.delta_risk_days):.1f} days of expected delay")
    if perishable and option.spoilage_probability is not None and hold.spoilage_probability is not None:
        bits.append(
            f"drops spoilage risk from {int(hold.spoilage_probability * 100)}% "
            f"to {int(option.spoilage_probability * 100)}%"
        )
    if option.delta_cost_usd > 25:
        bits.append(f"adds ${option.delta_cost_usd:,.0f} in freight and demurrage")
    elif option.delta_cost_usd < -25:
        bits.append(f"cuts freight and demurrage by ${abs(option.delta_cost_usd):,.0f}")
    if option.delta_transit_days >= 0.5:
        bits.append(f"lands {option.delta_transit_days:.0f} days later on paper")
    elif option.delta_transit_days <= -0.5:
        bits.append(f"lands {abs(option.delta_transit_days):.0f} days earlier")
    if option.delta_co2_tonnes <= -0.05:
        bits.append(f"saves {abs(option.delta_co2_tonnes):.2f} t CO₂")
    elif option.delta_co2_tonnes >= 0.05:
        bits.append(f"adds {option.delta_co2_tonnes:.2f} t CO₂")

    lead = option.label if option.kind != "hold" else "This option"
    body = ", ".join(bits[:3]) if bits else "performs much like the current booking"
    net = (
        f" Net expected saving ${option.savings_usd:,.0f}."
        if option.savings_usd > 0
        else f" Net expected cost ${abs(option.savings_usd):,.0f} more."
    )
    return f"{lead}: {body}.{net}"


class Recommender:
    def __init__(self, db: Session, engine: ExposureEngine, sim_date: date):
        self.db = db
        self.engine = engine
        self.sim_date = sim_date
        self.legs = load_legs(db)
        self.ports: dict[str, Port] = engine.ports

    # ------------------------------------------------------------------ build --
    def _evaluate(
        self,
        shipment: Shipment,
        route: list[LegView],
        delay: int,
        option_id: str,
    ) -> Option | None:
        etd = max(shipment.etd, self.sim_date) + timedelta(days=delay)
        plan = Plan(
            legs=route,
            etd=etd,
            teu=shipment.teu,
            perishable=shipment.perishable,
            shelf_life_days=shipment.shelf_life_days,
            value_usd=shipment.value_usd,
            required_by=shipment.required_by,
        )
        try:
            exposure = self.engine.evaluate(plan)
        except KeyError:
            return None
        costs, days_late = _price(plan, exposure, route, shipment.required_by, self.sim_date)
        totals = route_totals(route)
        label, via = _label(
            route, list(shipment.leg_ids), delay, etd, {p: (self.ports[p].short_name or self.ports[p].name) for p in route_nodes(route)}
        )
        nodes = route_nodes(route)

        caveats: list[str] = []
        if shipment.perishable and exposure.spoilage_probability and exposure.spoilage_probability > 0.5:
            caveats.append("Arrival is more likely than not to fall outside the cargo's shelf life.")
        if days_late > 0:
            caveats.append(f"Expected to arrive {days_late:.0f} day(s) after the buyer's deadline.")
        if any(leg.mode == "land" for leg in route):
            caveats.append("Includes a road leg — higher emissions and customs handling.")

        return Option(
            id=option_id,
            kind="hold",  # corrected by the caller
            label=label,
            summary="",
            rationale="",
            leg_ids=[leg.id for leg in route],
            route_ports=nodes,
            route_port_names=[self.ports[n].name for n in nodes],
            via=via,
            etd=etd,
            departure_delay_days=delay,
            scheduled_transit_days=exposure.scheduled_transit_days,
            scheduled_arrival=exposure.scheduled_arrival,
            expected_arrival=exposure.expected_arrival,
            required_by=shipment.required_by,
            days_late=round(days_late, 1),
            delta_cost_usd=0.0,
            delta_transit_days=0.0,
            delta_risk_days=0.0,
            delta_co2_tonnes=0.0,
            freight_usd=round(totals["cost_per_teu"] * shipment.teu, 2),
            co2_tonnes=round(totals["co2_tonnes_per_teu"] * shipment.teu, 3),
            expected_delay_days=exposure.expected_delay_days,
            prob_delay_over_3=exposure.prob_delay_over_3,
            prob_delay_over_7=exposure.prob_delay_over_7,
            prob_miss_deadline=exposure.prob_miss_deadline,
            demurrage_usd=exposure.demurrage_usd,
            spoilage_probability=exposure.spoilage_probability,
            spoilage_band=exposure.spoilage_band,
            risk_level=exposure.risk_level,
            confidence=exposure.confidence,
            costs=costs,
            savings_usd=0.0,
            score=0.0,
            caveats=caveats,
            exposure=exposure,
        )

    def recommend(self, shipment: Shipment, max_alternatives: int = MAX_ALTERNATIVES) -> list[Option]:
        current_route = [self.legs[i] for i in shipment.leg_ids]
        routes: list[list[LegView]] = [current_route]
        seen = {tuple(shipment.leg_ids)}
        for route in candidate_routes(self.db, shipment.origin_id, shipment.dest_id, max_legs=3, max_routes=7):
            key = tuple(leg.id for leg in route)
            if key not in seen:
                seen.add(key)
                routes.append(route)

        # One batched prediction for every port any candidate might touch.
        self.engine.fc.prewarm(
            sorted({p for route in routes for p in route_nodes(route)})
        )

        # --- hold sets the reference point for every delta ---
        hold = self._evaluate(shipment, current_route, 0, "hold")
        if hold is None:
            return []
        hold.kind = "hold"

        candidates: list[Option] = []
        for r_i, route in enumerate(routes):
            same_route = [leg.id for leg in route] == list(shipment.leg_ids)
            departure_options = (
                PERISHABLE_DEPARTURE_OPTIONS if shipment.perishable else DEPARTURE_OPTIONS
            )
            for delay in departure_options:
                if same_route and delay == 0:
                    continue
                option = self._evaluate(shipment, route, delay, f"opt-{r_i}-{delay}")
                if option is None:
                    continue
                if same_route:
                    option.kind = "delay"
                elif delay == 0:
                    option.kind = "reroute"
                else:
                    option.kind = "reroute_delay"
                candidates.append(option)

        for option in candidates + [hold]:
            option.delta_cost_usd = round(
                (option.freight_usd + option.demurrage_usd)
                - (hold.freight_usd + hold.demurrage_usd),
                2,
            )
            option.delta_transit_days = round(
                (option.expected_arrival - hold.expected_arrival).days, 1
            )
            option.delta_risk_days = round(
                hold.expected_delay_days - option.expected_delay_days, 2
            )
            option.delta_co2_tonnes = round(option.co2_tonnes - hold.co2_tonnes, 3)
            option.savings_usd = round(hold.costs.total_usd - option.costs.total_usd, 2)

        candidates.sort(key=lambda o: o.costs.total_usd)

        # --- prune alternatives dominated on all four headline criteria --------
        # The comparison pool includes "hold": an alternative that is worse than
        # doing nothing on cost, timing, risk and emissions has no business on
        # the list either.
        pool = candidates + [hold]
        kept: list[Option] = []
        for option in candidates:
            dominator = next(
                (other for other in pool if other is not option and _dominates(other, option)),
                None,
            )
            if dominator is not None:
                continue
            # Also drop near-duplicates of an option already kept.
            if any(
                abs(option.costs.total_usd - k.costs.total_usd) < 1.0
                and option.leg_ids == k.leg_ids
                for k in kept
            ):
                continue
            kept.append(option)
            if len(kept) == max_alternatives:
                break

        # If everything was pruned, still offer the single best alternative. It
        # cannot itself be dominated by hold: an option that beats hold on all
        # four criteria also has a lower expected total cost.
        if not kept and candidates:
            kept = [candidates[0]]

        shown = [hold] + kept
        for option in shown:
            option.dominated_by = next(
                (o.id for o in shown if o is not option and _dominates(o, option)), None
            )

        # --- rank and score ----------------------------------------------------
        ordered = sorted(shown, key=lambda o: o.costs.total_usd)
        best = ordered[0].costs.total_usd
        worst = ordered[-1].costs.total_usd
        span = max(worst - best, 1.0)
        for i, option in enumerate(ordered):
            option.rank = i + 1
            option.score = round(1.0 - (option.costs.total_usd - best) / span, 3)
            option.recommended = i == 0
            option.summary = _summary(option)
            option.rationale = _rationale(option, hold, shipment.perishable)

        # Hold stays in the list even when it is dominated — it is the status quo
        # and the user is entitled to see what it costs — but it is labelled.
        if hold.dominated_by:
            winner = next(o for o in shown if o.id == hold.dominated_by)
            hold.caveats.insert(
                0,
                f"Strictly worse than “{winner.label}” on cost, timing, risk and emissions.",
            )
        return ordered


def _summary(option: Option) -> str:
    parts = [
        f"${option.delta_cost_usd:+,.0f}",
        f"{option.delta_transit_days:+.0f} d arrival",
        f"{option.delta_risk_days:+.1f} risk days",
        f"{option.delta_co2_tonnes:+.2f} t CO₂",
    ]
    return " · ".join(parts)


def build_recommender(db: Session, engine: ExposureEngine, sim_date: date) -> Recommender:
    return Recommender(db, engine, sim_date)


__all__ = [
    "CostBreakdown",
    "Option",
    "Recommender",
    "build_recommender",
    "CARBON_PRICE_USD_PER_TONNE",
    "DEPARTURE_OPTIONS",
    "_dominates",
]
