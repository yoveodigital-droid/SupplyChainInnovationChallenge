"""Exposure engine: delay distribution, demurrage and spoilage."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest

from app.models import Port, Shipment
from app.services.exposure import Plan, _expected_excess, _tail

AMINA = "SHP-AMN-001"
RICE = "SHP-RAF-103"


def _plan(stack, shipment_id: str) -> Plan:
    s = stack.db.get(Shipment, shipment_id)
    return Plan(
        legs=[stack.recommender.legs[i] for i in s.leg_ids],
        etd=max(s.etd, stack.sim_date),
        teu=s.teu,
        perishable=s.perishable,
        shelf_life_days=s.shelf_life_days,
        value_usd=s.value_usd,
        required_by=s.required_by,
    )


def test_calm_world_exposure_is_small(stack):
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    assert e.expected_delay_days < 2.0
    assert e.risk_level == "green"
    assert e.demurrage_usd == 0.0
    assert e.spoilage_probability == pytest.approx(0.0, abs=0.02)


def test_disruption_raises_delay_demurrage_and_spoilage(stack):
    before = stack.exposure.evaluate(_plan(stack, AMINA))
    stack.trigger()
    stack.advance()
    after = stack.exposure.evaluate(_plan(stack, AMINA))
    assert after.expected_delay_days > before.expected_delay_days + 3
    assert after.demurrage_usd > before.demurrage_usd
    assert after.spoilage_probability > 0.5
    assert after.spoilage_band == "red"
    assert after.risk_level == "red"


def test_delay_quantiles_are_ordered(stack):
    stack.trigger()
    stack.advance()
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    assert 0 <= e.delay_p10 <= e.expected_delay_days <= e.delay_p90
    assert e.delay_sigma > 0


def test_probabilities_are_consistent(stack):
    stack.trigger()
    stack.advance()
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    assert e.prob_delay_over_3 >= e.prob_delay_over_7
    assert 0.0 <= e.prob_miss_deadline <= 1.0


def test_delay_distribution_is_a_distribution(stack):
    stack.trigger()
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    bins = stack.exposure.delay_distribution(e)
    total = sum(b["probability"] for b in bins)
    assert total == pytest.approx(1.0, abs=0.01)
    assert all(b["probability"] >= 0 for b in bins)


def test_demurrage_uses_the_destination_rate_and_free_days(stack):
    stack.trigger()
    stack.advance()
    plan = _plan(stack, AMINA)
    e = stack.exposure.evaluate(plan)
    port: Port = stack.exposure.ports[plan.legs[-1].dest_id]
    expected_days = _expected_excess(e.expected_delay_days, e.delay_sigma, float(port.free_days))
    assert e.demurrage_days == pytest.approx(expected_days, abs=0.02)
    # demurrage_days is reported rounded, so allow a couple of dollars of slack.
    assert e.demurrage_usd == pytest.approx(
        e.demurrage_days * port.demurrage_usd_per_teu_day * plan.teu, abs=5.0
    )


def test_no_demurrage_when_delay_is_far_inside_free_days(stack):
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    port = stack.exposure.ports["SAJED"]
    assert e.expected_delay_days < port.free_days
    assert e.demurrage_usd < 5.0


def test_spoilage_compares_delay_against_remaining_shelf_life(stack):
    stack.trigger()
    stack.advance()
    plan = _plan(stack, AMINA)
    e = stack.exposure.evaluate(plan)
    slack = plan.shelf_life_days - e.scheduled_transit_days
    assert e.spoilage_probability == pytest.approx(
        _tail(e.expected_delay_days, e.delay_sigma, slack), abs=0.01
    )


def test_dry_cargo_has_no_spoilage(stack):
    e = stack.exposure.evaluate(_plan(stack, RICE))
    assert e.spoilage_probability is None
    assert e.spoilage_band is None
    assert e.expected_spoilage_loss_usd == 0.0


def test_every_port_call_is_accounted_for(stack):
    plan = _plan(stack, RICE)
    e = stack.exposure.evaluate(plan)
    assert len(e.calls) == len(plan.legs) + 1
    assert e.calls[0].role == "load"
    assert e.calls[-1].role == "discharge"
    assert [c.role for c in e.calls[1:-1]] == ["transship"] * (len(plan.legs) - 1)
    assert len(e.legs) == len(plan.legs)


def test_feeder_calls_queue_longer_than_mainline_calls(stack):
    """Berth priority is a real effect and the model must show it."""
    stack.trigger()
    stack.advance()
    day = stack.sim_date + timedelta(days=8)
    feeder = stack.exposure._call("SAJED", day, "discharge", "feeder")
    mainline = stack.exposure._call("SAJED", day, "discharge", "mainline")
    truck = stack.exposure._call("SAJED", day, "discharge", "truck")
    assert feeder.delay_days > mainline.delay_days > truck.delay_days
    assert truck.delay_days == 0.0


def test_priority_relay_hub_waives_connection_waiting(stack):
    stack.trigger()
    stack.advance()
    assert "OMSLL" in stack.exposure.priority_hubs
    legs = stack.recommender.legs
    plan = Plan(
        legs=[legs["KEMBA-OMSLL"], legs["OMSLL-SAJED"]],
        etd=stack.sim_date + timedelta(days=6),
        teu=2,
    )
    e = stack.exposure.evaluate(plan)
    assert all(leg.connection_delay_days == 0.0 for leg in e.legs)


def test_chokepoint_delay_appears_on_the_right_legs(stack):
    stack.trigger()
    stack.advance()
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    red_sea = [leg for leg in e.legs if "bab_el_mandeb" in leg.chokepoints]
    assert red_sea, "Mombasa–Jeddah must transit Bab el-Mandeb"
    assert all(leg.chokepoint_delay_days > 0 for leg in red_sea)
    assert all(leg.chokepoint_risk > 0.5 for leg in red_sea)


def test_drivers_explain_the_delay(stack):
    stack.trigger()
    stack.advance()
    e = stack.exposure.evaluate(_plan(stack, AMINA))
    assert e.drivers
    assert sum(d["days"] for d in e.drivers) <= e.expected_delay_days + 0.6
    assert e.drivers == sorted(e.drivers, key=lambda d: d["days"], reverse=True)


def test_helper_maths():
    # E[max(0, X-a)] for a normal centred well above the threshold.
    assert _expected_excess(10.0, 1.0, 4.0) == pytest.approx(6.0, abs=0.01)
    # Symmetric tail at the mean.
    assert _tail(5.0, 2.0, 5.0) == pytest.approx(0.5, abs=1e-3)
    # Monotone in the threshold.
    assert _tail(5.0, 2.0, 3.0) > _tail(5.0, 2.0, 7.0)


def test_empty_plan_is_rejected(stack):
    with pytest.raises(ValueError):
        stack.exposure.evaluate(Plan(legs=[], etd=stack.sim_date, teu=1))


def test_longer_route_has_more_uncertainty(stack):
    """Variance accumulates across calls; a three-leg route cannot be more
    certain than a one-leg one under the same conditions."""
    stack.trigger()
    short = stack.exposure.evaluate(_plan(stack, AMINA))
    long = stack.exposure.evaluate(_plan(stack, RICE))
    assert long.delay_sigma > short.delay_sigma
    assert not math.isnan(long.delay_sigma)
