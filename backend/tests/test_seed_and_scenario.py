"""Seed determinism, world sanity and the scripted demo scenario."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config import HISTORY_DAYS, SEED_TODAY
from app.models import Chokepoint, Event, Leg, Persona, Port, PortDaily, Shipment
from app.seed import build_series
from app.services import scenario
from app.services.exposure import Plan
from app.world import LEG_SPECS, PORTS, leg_metrics


# --------------------------------------------------------------------------- #
# Seed data
# --------------------------------------------------------------------------- #


def test_world_is_populated(db):
    assert db.scalar(select(func.count()).select_from(Port)) == len(PORTS)
    assert db.scalar(select(func.count()).select_from(Leg)) == len(LEG_SPECS)
    assert db.scalar(select(func.count()).select_from(Persona)) == 3
    assert db.scalar(select(func.count()).select_from(Shipment)) == 9
    assert db.scalar(select(func.count()).select_from(Chokepoint)) == 5


def test_history_is_eighteen_months_for_every_port(db):
    rows = db.execute(
        select(PortDaily.port_id, func.count(PortDaily.id)).group_by(PortDaily.port_id)
    ).all()
    assert len(rows) == len(PORTS)
    assert {count for _, count in rows} == {HISTORY_DAYS}


def test_history_stops_at_simulated_today(db):
    assert db.scalar(select(func.max(PortDaily.day))) == SEED_TODAY


def test_series_generation_is_deterministic():
    build_series.cache_clear()
    first = build_series()["SAJED"][SEED_TODAY]
    build_series.cache_clear()
    second = build_series()["SAJED"][SEED_TODAY]
    assert first == second


def test_observations_are_in_range(db):
    rows = db.execute(select(PortDaily)).scalars().all()
    assert all(2 <= r.congestion_index <= 99 for r in rows)
    assert all(0 <= r.waiting_days <= 12 for r in rows)
    assert all(0 <= r.weather_severity <= 10 for r in rows)
    assert all(r.vessel_arrivals >= 0 for r in rows)


def test_historical_episodes_are_visible_in_the_data(db):
    """The Red Sea episode of Dec 2024 – Feb 2025 must actually show up at
    Jeddah, otherwise the forecaster has never seen a shock."""
    series = build_series()["SAJED"]
    episode = [
        obs["congestion_index"]
        for day, obs in series.items()
        if day.year == 2025 and day.month == 1
    ]
    calm = [
        obs["congestion_index"]
        for day, obs in series.items()
        if day.year == 2024 and day.month in (9, 10)
    ]
    assert sum(episode) / len(episode) > sum(calm) / len(calm) + 8


def test_leg_economics_are_plausible(db):
    for leg in db.execute(select(Leg)).scalars():
        assert leg.distance_nm > 0
        assert leg.transit_days > 0
        assert leg.cost_per_teu > 0
        assert leg.co2_tonnes_per_teu > 0
        # Nothing sails faster than roughly 25 knots.
        assert leg.distance_nm / leg.transit_days < 700


def test_road_legs_are_dirtier_per_mile_than_sea_legs():
    truck = next(leg_metrics(s) for s in LEG_SPECS if s.service == "truck")
    mainline = next(leg_metrics(s) for s in LEG_SPECS if s.service == "mainline")
    assert (
        truck["co2_tonnes_per_teu"] / truck["distance_nm"]
        > mainline["co2_tonnes_per_teu"] / mainline["distance_nm"] * 5
    )


def test_every_shipment_route_is_connected(db):
    legs = {leg.id: leg for leg in db.execute(select(Leg)).scalars()}
    for shipment in db.execute(select(Shipment)).scalars():
        route = [legs[i] for i in shipment.leg_ids]
        assert route[0].origin_id == shipment.origin_id
        assert route[-1].dest_id == shipment.dest_id
        for a, b in zip(route, route[1:]):
            assert a.dest_id == b.origin_id
        assert shipment.required_by > shipment.etd


def test_amina_matches_the_brief(db):
    amina = db.get(Shipment, "SHP-AMN-001")
    assert amina.origin_id == "KEMBA" and amina.dest_id == "SAJED"
    assert amina.perishable and amina.shelf_life_days == 14
    assert amina.teu == 2
    assert amina.etd == SEED_TODAY + timedelta(days=6)


def test_personas_cover_the_three_views(db):
    views = {p.id: p.view for p in db.execute(select(Persona)).scalars()}
    assert views == {"amina": "phone", "rafael": "dashboard", "jeddah_pa": "port"}
    assert db.scalar(
        select(func.count()).select_from(Shipment).where(Shipment.persona_id == "jeddah_pa")
    ) == 0
    assert db.scalar(
        select(func.count()).select_from(Shipment).where(Shipment.persona_id == "rafael")
    ) == 8


# --------------------------------------------------------------------------- #
# Scenario controller
# --------------------------------------------------------------------------- #


def test_seed_state_is_calm(stack):
    """§7 seed state: everything green before the presenter touches anything."""
    for shipment in stack.db.execute(select(Shipment)).scalars():
        plan = Plan(
            legs=[stack.recommender.legs[i] for i in shipment.leg_ids],
            etd=max(shipment.etd, stack.sim_date),
            teu=shipment.teu,
            perishable=shipment.perishable,
            shelf_life_days=shipment.shelf_life_days,
            value_usd=shipment.value_usd,
            required_by=shipment.required_by,
        )
        assert stack.exposure.evaluate(plan).risk_level == "green", shipment.reference


def test_advance_reveals_one_new_day_of_observations(stack):
    before = stack.db.scalar(select(func.count()).select_from(PortDaily))
    stack.advance()
    after = stack.db.scalar(select(func.count()).select_from(PortDaily))
    assert after - before == len(PORTS)
    assert stack.sim_date == SEED_TODAY + timedelta(days=1)
    assert stack.db.scalar(select(func.max(PortDaily.day))) == stack.sim_date


def test_advance_is_idempotent_per_day(stack):
    stack.advance()
    count = stack.db.scalar(
        select(func.count()).select_from(PortDaily).where(PortDaily.day == stack.sim_date)
    )
    assert count == len(PORTS)


def test_trigger_publishes_events_and_raises_chokepoint_risk(stack):
    assert not stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all()
    stack.trigger()
    events = stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all()
    assert events
    assert any(e.chokepoint_id == "bab_el_mandeb" for e in events)
    assert stack.db.get(Chokepoint, "bab_el_mandeb").current_risk > 0.5


def test_trigger_is_not_retroactive(stack):
    """Declaring the scenario must not rewrite observed history — a jury will
    notice if the chart changes shape behind them."""
    before = {
        (r.port_id, r.day): r.congestion_index
        for r in stack.db.execute(select(PortDaily)).scalars()
    }
    stack.trigger()
    after = {
        (r.port_id, r.day): r.congestion_index
        for r in stack.db.execute(select(PortDaily)).scalars()
    }
    assert before == after


def test_scenario_events_arrive_on_schedule(stack):
    stack.trigger()
    day_zero = len(stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all())
    stack.advance()
    day_one = len(stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all())
    stack.advance()
    day_two = len(stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all())
    assert day_zero < day_one < day_two


def test_observations_catch_up_with_the_declared_event(stack):
    stack.trigger()
    stack.advance(3)
    rows = stack.db.execute(
        select(PortDaily).where(PortDaily.port_id == "SAJED").order_by(PortDaily.day.desc()).limit(3)
    ).scalars().all()
    assert all(r.scenario for r in rows)
    assert rows[0].congestion_index > 70


def test_reset_restores_the_seed_state(stack):
    stack.trigger()
    stack.advance(4)
    scenario.reset(stack.db)
    stack.db.flush()
    stack.refresh()
    assert stack.sim_date == SEED_TODAY
    assert not stack.db.execute(select(Event).where(Event.scenario.is_(True))).scalars().all()
    assert stack.db.scalar(select(func.max(PortDaily.day))) == SEED_TODAY
    assert stack.db.get(Chokepoint, "bab_el_mandeb").current_risk < 0.2


def test_clock_cannot_run_past_the_generated_world(stack):
    for _ in range(scenario.MAX_SIM_DAYS + 5):
        scenario.advance_day(stack.db)
    view = scenario.state_view(stack.db)
    assert view.days_advanced == scenario.MAX_SIM_DAYS
    assert not view.can_advance


@pytest.mark.parametrize("port_id", ["SAJED", "OMSLL", "KEMBA"])
def test_no_duplicate_observations(stack, port_id):
    stack.trigger()
    stack.advance(3)
    days = [
        r.day
        for r in stack.db.execute(
            select(PortDaily).where(PortDaily.port_id == port_id)
        ).scalars()
    ]
    assert len(days) == len(set(days))
