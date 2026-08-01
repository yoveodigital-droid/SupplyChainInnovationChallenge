"""Recommendation engine — the module that most needs to be right.

Covers the acceptance criteria from the brief:
  * perishable prioritisation
  * "hold current plan" is always present
  * CO2 is computed for every alternative
  * no shown alternative is dominated on all four criteria by another shown one
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import Shipment
from app.services.recommend import (
    DEPARTURE_OPTIONS,
    PERISHABLE_DEPARTURE_OPTIONS,
    Recommender,
    _dominates,
)

AMINA = "SHP-AMN-001"
RICE = "SHP-RAF-103"  # dry cargo, 3 legs, Laem Chabang -> Singapore -> Colombo -> Jeddah
MACHINERY = "SHP-RAF-106"


def _rec(stack, shipment_id: str):
    shipment = stack.db.get(Shipment, shipment_id)
    return shipment, stack.recommender.recommend(shipment)


# --------------------------------------------------------------------------- #
# Structural invariants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shipment_id", [AMINA, RICE, MACHINERY])
def test_hold_option_always_present(stack, shipment_id):
    """The status quo must always be on the table, quantified, before and after
    a disruption. A tool that only ever says 'change something' is a salesman."""
    for phase in ("calm", "disrupted"):
        _, options = _rec(stack, shipment_id)
        holds = [o for o in options if o.kind == "hold"]
        assert len(holds) == 1, f"{phase}: expected exactly one hold option"
        hold = holds[0]
        assert hold.label == "Hold current plan"
        assert hold.delta_cost_usd == 0.0
        assert hold.delta_risk_days == 0.0
        assert hold.delta_co2_tonnes == 0.0
        assert hold.rationale, "hold must explain what it costs"
        if phase == "calm":
            stack.trigger()
            stack.advance()


def test_hold_is_the_reference_point(stack):
    """Every delta is measured against hold, so hold's own deltas are zero and
    its absolute numbers are self-consistent."""
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    hold = next(o for o in options if o.kind == "hold")
    for option in options:
        assert option.delta_risk_days == pytest.approx(
            hold.expected_delay_days - option.expected_delay_days, abs=0.02
        )
        assert option.delta_co2_tonnes == pytest.approx(
            option.co2_tonnes - hold.co2_tonnes, abs=0.002
        )
        assert option.savings_usd == pytest.approx(
            hold.costs.total_usd - option.costs.total_usd, abs=0.02
        )


@pytest.mark.parametrize("shipment_id", [AMINA, RICE, MACHINERY])
def test_co2_computed_for_every_alternative(stack, shipment_id):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, shipment_id)
    for option in options:
        assert option.co2_tonnes > 0, f"{option.label} has no emissions figure"
        assert option.costs.carbon_usd == pytest.approx(option.co2_tonnes * 95.0, rel=1e-3)
        # CO2 must track the actual route, not be copied from the baseline.
        assert option.delta_co2_tonnes == pytest.approx(
            option.co2_tonnes - next(o for o in options if o.kind == "hold").co2_tonnes,
            abs=0.002,
        )


def test_land_leg_costs_more_carbon_than_the_sea_alternative(stack):
    """Sanity check on the emissions model: trucking is dirtier per TEU-mile."""
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    road = [o for o in options if any(i.endswith("-LAND") for i in o.leg_ids)]
    sea_only = [o for o in options if not any(i.endswith("-LAND") for i in o.leg_ids)]
    if road and sea_only:
        assert max(o.co2_tonnes for o in road) > min(o.co2_tonnes for o in sea_only)


# --------------------------------------------------------------------------- #
# Pareto dominance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("shipment_id", [AMINA, RICE, MACHINERY])
def test_no_shown_alternative_is_dominated(stack, shipment_id):
    """No alternative may be strictly worse than another shown option on cost,
    timing, risk-days and emissions all at once — showing one would waste the
    reader's attention. 'Hold' is exempt: it is the mandatory status quo, and
    when it is dominated we say so explicitly instead of hiding it."""
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, shipment_id)
    alternatives = [o for o in options if o.kind != "hold"]
    for option in alternatives:
        for other in options:
            if other is option:
                continue
            assert not _dominates(other, option), (
                f"{option.label!r} is dominated by {other.label!r}"
            )


def test_dominated_hold_is_labelled_not_hidden(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    hold = next(o for o in options if o.kind == "hold")
    if hold.dominated_by:
        assert any("Strictly worse" in c for c in hold.caveats)


def test_dominance_helper_is_a_strict_partial_order(stack):
    stack.trigger()
    _, options = _rec(stack, AMINA)
    for a in options:
        assert not _dominates(a, a), "an option cannot dominate itself"
        for b in options:
            if _dominates(a, b):
                assert not _dominates(b, a), "dominance must be antisymmetric"


# --------------------------------------------------------------------------- #
# Perishable prioritisation
# --------------------------------------------------------------------------- #


def test_perishable_cargo_prioritises_spoilage_over_freight_cost(stack):
    """For mangoes the engine must be willing to pay more freight to protect the
    cargo; the winning option is allowed to be the pricier one."""
    stack.trigger()
    stack.advance()
    shipment, options = _rec(stack, AMINA)
    assert shipment.perishable
    top = next(o for o in options if o.rank == 1)
    hold = next(o for o in options if o.kind == "hold")

    assert top.kind != "hold", "a red perishable shipment must get an alternative"
    assert top.spoilage_probability is not None
    assert top.spoilage_probability < hold.spoilage_probability
    assert top.costs.spoilage_loss_usd < hold.costs.spoilage_loss_usd
    # The recommendation is driven by avoided loss, not by being cheapest.
    assert top.savings_usd > 0


def test_perishable_spoilage_dominates_the_objective(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    hold = next(o for o in options if o.kind == "hold")
    assert hold.costs.spoilage_loss_usd > hold.costs.freight_usd, (
        "for a threatened perishable, expected spoilage loss should outweigh freight"
    )


def test_dry_cargo_is_not_charged_a_spoilage_term(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, MACHINERY)
    for option in options:
        assert option.spoilage_probability is None
        assert option.costs.spoilage_loss_usd == 0.0


def test_perishable_departure_delay_is_capped(stack):
    """A harvest-linked booking cannot slip a week; dry cargo can."""
    stack.trigger()
    _, perishable_options = _rec(stack, AMINA)
    _, dry_options = _rec(stack, RICE)
    assert max(o.departure_delay_days for o in perishable_options) <= max(
        PERISHABLE_DEPARTURE_OPTIONS
    )
    assert max(DEPARTURE_OPTIONS) > max(PERISHABLE_DEPARTURE_OPTIONS)
    assert all(o.departure_delay_days in DEPARTURE_OPTIONS for o in dry_options)


# --------------------------------------------------------------------------- #
# Ranking behaviour
# --------------------------------------------------------------------------- #


def test_calm_world_recommends_holding(stack):
    """No disruption, no churn: the engine must be willing to say 'do nothing'."""
    _, options = _rec(stack, AMINA)
    top = next(o for o in options if o.rank == 1)
    assert top.kind == "hold"
    assert top.risk_level == "green"


def test_ranking_is_by_expected_total_cost(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    totals = [o.costs.total_usd for o in sorted(options, key=lambda o: o.rank)]
    assert totals == sorted(totals)
    assert sum(1 for o in options if o.recommended) == 1
    assert next(o for o in options if o.recommended).rank == 1


def test_scores_are_normalised(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    assert max(o.score for o in options) == pytest.approx(1.0)
    assert min(o.score for o in options) == pytest.approx(0.0)
    assert all(0.0 <= o.score <= 1.0 for o in options)


def test_cost_breakdown_sums_to_total(stack):
    stack.trigger()
    stack.advance()
    for shipment_id in (AMINA, RICE):
        _, options = _rec(stack, shipment_id)
        for o in options:
            c = o.costs
            parts = (
                c.freight_usd + c.demurrage_usd + c.spoilage_loss_usd
                + c.late_penalty_usd + c.holding_usd + c.carbon_usd
            )
            assert parts == pytest.approx(c.total_usd, abs=0.05)


def test_options_are_distinct_and_actionable(stack):
    stack.trigger()
    stack.advance()
    _, options = _rec(stack, AMINA)
    assert 2 <= len(options) <= 4
    signatures = {(tuple(o.leg_ids), o.etd) for o in options}
    assert len(signatures) == len(options), "duplicate options shown"
    for o in options:
        assert o.rationale.strip(), "every option needs a plain-language reason"
        assert o.route_ports[0] == options[0].route_ports[0]
        assert len(o.route_port_names) == len(o.route_ports)


def test_departure_delay_never_precedes_today(stack):
    """A shipment whose ETD has already passed must be re-planned from today,
    never scheduled into the past."""
    shipment = stack.db.get(Shipment, AMINA)
    shipment.etd = stack.sim_date - timedelta(days=2)
    stack.db.flush()
    stack.refresh()
    _, options = _rec(stack, AMINA)
    for option in options:
        assert option.etd >= stack.sim_date


def test_rerouting_changes_the_route(stack):
    stack.trigger()
    stack.advance()
    shipment, options = _rec(stack, AMINA)
    reroutes = [o for o in options if o.kind in ("reroute", "reroute_delay")]
    for option in reroutes:
        assert option.leg_ids != list(shipment.leg_ids)
        assert option.route_ports[-1] == shipment.dest_id
        assert len(option.route_ports) >= 2


def test_recommender_is_deterministic(stack):
    stack.trigger()
    stack.advance()
    shipment = stack.db.get(Shipment, AMINA)
    first = Recommender(stack.db, stack.exposure, stack.sim_date).recommend(shipment)
    second = Recommender(stack.db, stack.exposure, stack.sim_date).recommend(shipment)
    assert [o.id for o in first] == [o.id for o in second]
    assert [o.costs.total_usd for o in first] == [o.costs.total_usd for o in second]
