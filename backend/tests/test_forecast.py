"""Forecasting service and the event-propagation overlay."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import MAX_HORIZON_DAYS
from app.services.events import impact_profile, severity_scale
from app.services.forecast import get_bundle

JEDDAH = "SAJED"
SALALAH = "OMSLL"


def test_model_beats_naive_persistence(db):
    """A forecast that cannot beat 'tomorrow looks like today' is not worth
    shipping. Measured on a held-out final 21 days."""
    bundle = get_bundle(db)
    assert bundle.metrics["congestion_mae"] < bundle.metrics["congestion_mae_naive"]
    assert bundle.metrics["waiting_mae"] < bundle.metrics["waiting_mae_naive"]


def test_forecast_shape_and_bounds(stack):
    points = stack.forecaster.forecast(JEDDAH, MAX_HORIZON_DAYS)
    assert len(points) == MAX_HORIZON_DAYS
    assert [p.horizon for p in points] == list(range(1, MAX_HORIZON_DAYS + 1))
    for p in points:
        assert p.day == stack.sim_date + timedelta(days=p.horizon)
        assert 0 <= p.congestion <= 100
        assert p.congestion_low <= p.congestion <= p.congestion_high
        assert p.waiting_low <= p.waiting_days <= p.waiting_high
        assert 0.0 <= p.disruption_probability <= 1.0
        assert 0.0 < p.confidence <= 1.0


def test_confidence_decays_with_horizon(stack):
    points = stack.forecaster.forecast(JEDDAH, MAX_HORIZON_DAYS)
    assert points[0].confidence > points[-1].confidence


def test_intervals_widen_with_horizon(stack):
    points = stack.forecaster.forecast(JEDDAH, MAX_HORIZON_DAYS)
    near = points[0].congestion_high - points[0].congestion_low
    far = points[-1].congestion_high - points[-1].congestion_low
    assert far > near


def test_calm_world_has_low_disruption_probability(stack):
    for port_id in (JEDDAH, SALALAH, "KEMBA", "SGSIN"):
        points = stack.forecaster.forecast(port_id, 14)
        assert max(p.disruption_probability for p in points) < 0.30, port_id
        assert all(p.event_uplift == 0.0 for p in points)


# --------------------------------------------------------------------------- #
# Event propagation
# --------------------------------------------------------------------------- #


def test_impact_profile_ramps_plateaus_and_decays():
    assert impact_profile(-1) == 0.0
    # An incident overnight is already dangerous in the morning: the profile
    # starts at a floor rather than at zero, then ramps as congestion builds.
    assert 0 < impact_profile(0) < 0.5
    assert impact_profile(0) < impact_profile(1) < 1
    assert impact_profile(5) == 1.0
    assert impact_profile(12) == 1.0
    assert 0 < impact_profile(24) < 1
    assert impact_profile(200) == 0.0


def test_severity_scale_is_monotone():
    values = [severity_scale(s) for s in range(6)]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[5] == pytest.approx(1.0)


def test_scenario_lifts_jeddah_and_spares_salalah(stack):
    """Salalah is the corridor's shock absorber: none of its services transit
    Bab el-Mandeb, so a Red Sea security event must leave it alone."""
    before = {
        p: stack.forecaster.forecast(p, 10)[-1].congestion for p in (JEDDAH, SALALAH)
    }
    stack.trigger()
    after = {
        p: stack.forecaster.forecast(p, 10)[-1].congestion for p in (JEDDAH, SALALAH)
    }
    jeddah_lift = after[JEDDAH] - before[JEDDAH]
    salalah_lift = after[SALALAH] - before[SALALAH]
    assert jeddah_lift > 20, "Jeddah should spike hard"
    # Salalah still relays cargo through the strait, so it is not untouched —
    # but nothing *arrives* there via Bab el-Mandeb, so it must stay well clear
    # of its own disruption threshold and take a fraction of Jeddah's hit.
    assert salalah_lift < 0.35 * jeddah_lift
    threshold = stack.forecaster.bundle.port_thresholds[SALALAH]
    assert after[SALALAH] < threshold - 10


def test_event_uplift_is_reported_separately(stack):
    stack.trigger()
    point = stack.forecaster.forecast(JEDDAH, 10)[-1]
    assert point.event_uplift > 0
    assert point.congestion == pytest.approx(
        point.congestion_baseline + point.event_uplift, abs=0.05
    )
    assert point.event_drivers, "an uplift must name the events that caused it"
    assert sum(d["points"] for d in point.event_drivers) == pytest.approx(
        point.event_uplift, abs=0.05
    )


def test_active_event_widens_the_band_and_lowers_confidence(stack):
    before = stack.forecaster.forecast(JEDDAH, 10)[-1]
    stack.trigger()
    after = stack.forecaster.forecast(JEDDAH, 10)[-1]
    assert (after.congestion_high - after.congestion_low) > (
        before.congestion_high - before.congestion_low
    )
    assert after.confidence < before.confidence


def test_chokepoint_risk_rises_only_where_declared(stack):
    stack.trigger()
    bab = stack.forecaster.overlay.chokepoint_risk(stack.db, "bab_el_mandeb", stack.sim_date + timedelta(days=5))
    malacca = stack.forecaster.overlay.chokepoint_risk(stack.db, "malacca", stack.sim_date + timedelta(days=5))
    assert bab > 0.7
    assert malacca < 0.1


# --------------------------------------------------------------------------- #
# Explanations
# --------------------------------------------------------------------------- #


def test_explanation_is_plain_language_and_ranked(stack):
    contributions = stack.forecaster.explain(JEDDAH, 7)
    assert contributions
    magnitudes = [abs(c.effect) for c in contributions if c.feature != "declared_event"]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for c in contributions:
        assert c.label and c.label[0].isupper()
        assert c.direction in ("raises", "lowers")


def test_declared_events_lead_the_explanation(stack):
    stack.trigger()
    contributions = stack.forecaster.explain(JEDDAH, 7)
    assert contributions[0].feature == "declared_event"
    assert "Declared disruption" in contributions[0].label


def test_point_beyond_horizon_widens_rather_than_pretending(stack):
    inside = stack.forecaster.point(JEDDAH, stack.sim_date + timedelta(days=MAX_HORIZON_DAYS))
    outside = stack.forecaster.point(JEDDAH, stack.sim_date + timedelta(days=MAX_HORIZON_DAYS + 10))
    assert outside.confidence < inside.confidence
    assert (outside.congestion_high - outside.congestion_low) > (
        inside.congestion_high - inside.congestion_low
    )
