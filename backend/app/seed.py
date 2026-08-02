"""Deterministic synthetic-world generator.

Running this module builds ``data/portpulse.db`` from scratch:

    python -m app.seed            # build if missing
    python -m app.seed --force    # rebuild from zero

Everything is driven by ``config.RANDOM_SEED`` so two laptops produce
byte-identical demos.

Swap seam
---------
``build_series()`` is the only place that invents operating conditions. Point it
at a terminal-telemetry feed and the forecaster, exposure engine and
recommendation engine keep working unchanged.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
from sqlalchemy.orm import Session

from .config import HISTORY_DAYS, MODEL_DIR, RANDOM_SEED, SEED_TODAY
from .db import engine, session_scope
from .models import (
    Base,
    Chokepoint,
    DemoState,
    Event,
    Leg,
    Persona,
    Port,
    PortDaily,
    Shipment,
)
from .world import (
    CALM_FEED,
    CHOKEPOINTS,
    HISTORY_EPISODES,
    LEG_SPECS,
    PERSONAS,
    PORTS,
    SHIPMENTS,
    leg_id,
    leg_metrics,
)

# Days of "future" baseline generated beyond SEED_TODAY so the demo clock can
# advance without ever running out of deterministic ground truth.
FUTURE_BUFFER_DAYS = 45

HISTORY_START = SEED_TODAY - timedelta(days=HISTORY_DAYS - 1)
SERIES_END = SEED_TODAY + timedelta(days=FUTURE_BUFFER_DAYS)

# Weekly berth-productivity pattern, Monday=0.
WEEKDAY_CONGESTION = np.array([2.2, 2.8, 1.4, 0.2, -0.6, -2.4, -3.6])
WEEKDAY_ARRIVAL_FACTOR = np.array([1.12, 1.08, 1.02, 0.98, 1.05, 0.92, 0.83])


class Observation(dict):
    """A single port-day. A dict subclass so it serialises without ceremony."""


# Length of the "calm before the storm" fade applied at the end of history.
CALM_TAPER_DAYS = 12
CALM_TAPER_STRENGTH = 0.85


def _apply_calm_taper(days: list[date], congestion, structural):
    """Fade stochastic congestion toward its structural level near SEED_TODAY."""
    out = congestion.copy()
    for i, d in enumerate(days):
        gap = (SEED_TODAY - d).days
        if gap < 0 or gap >= CALM_TAPER_DAYS:
            continue
        w = CALM_TAPER_STRENGTH * (1.0 - gap / CALM_TAPER_DAYS)
        out[i] = (1 - w) * congestion[i] + w * structural[i]
    return out


def _episode_profile(day: date, start: date, end: date) -> float:
    """Trapezoidal shape: ramp in over a fifth of the window, decay over half."""
    if day < start or day > end + timedelta(days=14):
        return 0.0
    span = max((end - start).days, 1)
    ramp = max(span // 5, 2)
    offset = (day - start).days
    if offset < 0:
        return 0.0
    if offset < ramp:
        return offset / ramp
    if offset <= span:
        # Slow erosion across the plateau keeps it from looking like a box car.
        return 1.0 - 0.15 * (offset - ramp) / max(span - ramp, 1)
    decay = (offset - span) / 14
    return max(0.0, 0.85 * (1.0 - decay))


@lru_cache(maxsize=1)
def build_series() -> dict[str, dict[date, Observation]]:
    """Generate the full deterministic world series for every port.

    Returns ``{port_id: {day: Observation}}`` covering
    ``HISTORY_START .. SEED_TODAY + FUTURE_BUFFER_DAYS``.
    """
    n_days = (SERIES_END - HISTORY_START).days + 1
    days = [HISTORY_START + timedelta(days=i) for i in range(n_days)]
    doy = np.array([d.timetuple().tm_yday for d in days], dtype=float)
    weekday = np.array([d.weekday() for d in days])

    series: dict[str, dict[date, Observation]] = {}

    for port_index, port in enumerate(PORTS):
        rng = np.random.default_rng(RANDOM_SEED + 1000 + port_index)

        # --- weather: seasonal envelope + persistent (AR1) storm noise ---
        weather_seasonal = 2.1 + port.weather_amp * np.cos(
            2 * np.pi * (doy - port.weather_peak_doy) / 365.25
        )
        w_noise = np.zeros(n_days)
        eps = rng.normal(0, 1.15, n_days)
        for i in range(1, n_days):
            w_noise[i] = 0.62 * w_noise[i - 1] + eps[i]
        # Occasional storm bursts on top of the smooth process.
        bursts = rng.random(n_days) < 0.018
        burst_mag = rng.gamma(2.0, 1.6, n_days) * bursts
        weather = weather_seasonal + w_noise + burst_mag

        # --- episode uplifts ---
        cong_episode = np.zeros(n_days)
        weather_episode = np.zeros(n_days)
        for ep in HISTORY_EPISODES:
            uplift = ep.impact.get(port.id)
            if uplift is None and ep.weather_uplift == 0:
                continue
            profile = np.array([_episode_profile(d, ep.start, ep.end) for d in days])
            if uplift:
                cong_episode += uplift * profile
            if ep.weather_uplift and uplift:
                weather_episode += ep.weather_uplift * profile
        weather = np.clip(weather + weather_episode, 0.0, 10.0)

        # --- congestion ---
        seasonal = 7.0 * np.cos(2 * np.pi * (doy - port.congestion_peak_doy) / 365.25)
        weekly = WEEKDAY_CONGESTION[weekday]
        # Weather bites two days after it blows.
        weather_lag = np.concatenate([np.full(2, weather[0]), weather[:-2]])
        weather_push = 2.15 * (weather_lag - 2.1)
        # Slow drift so the level is not perfectly stationary across 18 months.
        drift = 2.2 * np.sin(2 * np.pi * np.arange(n_days) / 430.0 + port_index)

        resid = np.zeros(n_days)
        eps_c = rng.normal(0, 2.3, n_days)
        for i in range(1, n_days):
            resid[i] = 0.84 * resid[i - 1] + eps_c[i]

        structural = port.base_congestion + seasonal + weekly
        congestion = structural + weather_push + drift + cong_episode + resid

        # The demo opens on a calm world (§7 seed state): over the final days
        # before SEED_TODAY the stochastic part is faded out so every port sits
        # near its structural level. Documented in the README as a deliberate
        # staging choice, not a modelling claim.
        congestion = _apply_calm_taper(days, congestion, structural)
        congestion = np.clip(congestion, 4.0, 99.0)

        # --- waiting days: convex in congestion, nudged by weather ---
        waiting = (
            0.28
            + np.exp((congestion - 54.0) / 22.0)
            + 0.09 * weather
            + rng.normal(0, 0.16, n_days)
        )
        waiting = np.clip(waiting, 0.05, 12.0)

        # --- vessel arrivals ---
        lam = (port.capacity_teu_per_day / 600.0) * WEEKDAY_ARRIVAL_FACTOR[weekday]
        lam = lam * (1.0 + 0.10 * (congestion - port.base_congestion) / 25.0)
        arrivals = rng.poisson(np.clip(lam, 0.4, None))

        series[port.id] = {
            d: Observation(
                congestion_index=round(float(congestion[i]), 2),
                waiting_days=round(float(waiting[i]), 3),
                weather_severity=round(float(weather[i]), 2),
                vessel_arrivals=int(arrivals[i]),
            )
            for i, d in enumerate(days)
        }

    return series


def baseline_observation(port_id: str, day: date) -> Observation:
    """Deterministic ground-truth observation for any day inside the window."""
    port_series = build_series()[port_id]
    if day in port_series:
        return port_series[day]
    # Past the buffer: hold the last generated day (the demo never gets here).
    last_day = max(port_series)
    return port_series[last_day]


# --------------------------------------------------------------------------- #
# Database population
# --------------------------------------------------------------------------- #


def _seed_ports(db: Session) -> None:
    series = build_series()
    for p in PORTS:
        # "Normal" waiting is the median of what this port actually did over the
        # training window, not a formula. Exposure measures excess against it.
        observed = [
            obs["waiting_days"] for day, obs in series[p.id].items() if day <= SEED_TODAY
        ]
        normal_waiting = round(float(np.median(observed)), 3)
        db.add(
            Port(
                id=p.id,
                name=p.name,
                short_name=p.short_name or p.name,
                country=p.country,
                region=p.region,
                lat=p.lat,
                lon=p.lon,
                capacity_teu_per_day=p.capacity_teu_per_day,
                base_congestion=p.base_congestion,
                base_waiting_days=normal_waiting,
                demurrage_usd_per_teu_day=p.demurrage_usd_per_teu_day,
                free_days=p.free_days,
                is_hub=p.is_hub,
                congestion_threshold=p.congestion_threshold,
                monsoon_phase=float(p.weather_peak_doy),
                blurb=p.blurb,
            )
        )


def _seed_chokepoints(db: Session) -> None:
    for c in CHOKEPOINTS:
        db.add(
            Chokepoint(
                id=c.id,
                name=c.name,
                lat=c.lat,
                lon=c.lon,
                base_risk=c.base_risk,
                current_risk=c.base_risk,
                delay_days_at_max_risk=c.delay_days_at_max_risk,
                note=c.note,
            )
        )


def _seed_legs(db: Session) -> None:
    for spec in LEG_SPECS:
        m = leg_metrics(spec)
        db.add(
            Leg(
                id=leg_id(spec),
                origin_id=spec.origin,
                dest_id=spec.dest,
                mode=spec.mode,
                service=spec.service,
                distance_nm=m["distance_nm"],
                transit_days=m["transit_days"],
                cost_per_teu=m["cost_per_teu"],
                co2_tonnes_per_teu=m["co2_tonnes_per_teu"],
                sailings_per_week=spec.sailings_per_week,
                chokepoints=list(spec.chokepoints),
            )
        )


def _seed_history(db: Session) -> None:
    series = build_series()
    rows = []
    for port_id, by_day in series.items():
        for day, obs in by_day.items():
            if day > SEED_TODAY:
                continue  # the future is not observed
            rows.append(
                PortDaily(
                    port_id=port_id,
                    day=day,
                    congestion_index=obs["congestion_index"],
                    waiting_days=obs["waiting_days"],
                    weather_severity=obs["weather_severity"],
                    vessel_arrivals=obs["vessel_arrivals"],
                    scenario=False,
                )
            )
    db.bulk_save_objects(rows)


def _seed_personas(db: Session) -> None:
    for p in PERSONAS:
        db.add(
            Persona(
                id=p.id,
                name=p.name,
                role=p.role,
                org=p.org,
                location=p.location,
                view=p.view,
                home_port_id=p.home_port_id,
                language=p.language,
                avatar=p.avatar,
                blurb=p.blurb,
            )
        )


def _seed_shipments(db: Session) -> None:
    import math

    leg_lookup = {leg_id(spec): spec for spec in LEG_SPECS}
    for s in SHIPMENTS:
        first = leg_lookup[s.legs[0]]
        last = leg_lookup[s.legs[-1]]
        etd = SEED_TODAY + timedelta(days=s.etd_offset_days)
        transit = math.ceil(sum(leg_metrics(leg_lookup[lid])["transit_days"] for lid in s.legs))
        db.add(
            Shipment(
                id=s.id,
                persona_id=s.persona,
                reference=s.reference,
                origin_id=first.origin,
                dest_id=last.dest,
                leg_ids=list(s.legs),
                etd=etd,
                required_by=etd + timedelta(days=transit + s.buffer_days),
                cargo=s.cargo,
                cargo_short=s.cargo_short or s.cargo,
                teu=s.teu,
                perishable=s.perishable,
                shelf_life_days=s.shelf_life_days,
                value_usd=s.value_usd,
                status="booked",
                buyer=s.buyer,
                original_leg_ids=None,
                original_etd=None,
                applied_option=None,
            )
        )


def _seed_events(db: Session) -> None:
    from .world import PORTS_BY_ID

    for ep in HISTORY_EPISODES:
        # Anchor the headline a couple of days into the ramp, when it made the news.
        day = ep.start + timedelta(days=2)
        if ep.impact:
            focus = max(ep.impact, key=lambda k: ep.impact[k])
            port = PORTS_BY_ID[focus]
            lat, lon = port.lat, port.lon
        else:
            focus, lat, lon = None, 0.0, 0.0
        db.add(
            Event(
                id=ep.id,
                day=day,
                type=ep.type,
                severity=ep.severity,
                headline=ep.headline,
                detail=ep.detail,
                port_id=focus,
                chokepoint_id=ep.chokepoint,
                lat=lat,
                lon=lon,
                scenario=False,
            )
        )

    for i, (days_ago, etype, sev, headline, detail, port_id) in enumerate(CALM_FEED):
        port = PORTS_BY_ID[port_id] if port_id else None
        db.add(
            Event(
                id=f"EVC-{i:03d}",
                day=SEED_TODAY - timedelta(days=days_ago),
                type=etype,
                severity=sev,
                headline=headline,
                detail=detail,
                port_id=port_id,
                chokepoint_id=None,
                lat=port.lat if port else 0.0,
                lon=port.lon if port else 0.0,
                scenario=False,
            )
        )


def _seed_demo_state(db: Session) -> None:
    db.add(DemoState(id=1, sim_date=SEED_TODAY, scenario_active=False, scenario_day=0, data_version=1))


def reset_database(db: Session) -> None:
    """Drop every row and re-seed. Used by ``POST /api/demo/reset``."""
    for model in (Event, PortDaily, Shipment, Persona, Leg, Chokepoint, Port, DemoState):
        db.query(model).delete()
    db.flush()
    _seed_ports(db)
    _seed_chokepoints(db)
    _seed_legs(db)
    _seed_history(db)
    _seed_personas(db)
    _seed_shipments(db)
    _seed_events(db)
    _seed_demo_state(db)
    db.flush()


def ensure_seeded(force: bool = False) -> bool:
    """Create tables and seed if empty. Returns True when a seed actually ran.

    ``force`` drops and recreates the schema, so it also picks up model changes.
    """
    if force:
        Base.metadata.drop_all(engine)
        # A rebuilt world invalidates the trained model and every derived cache.
        model_path = MODEL_DIR / "forecaster.joblib"
        model_path.unlink(missing_ok=True)
        build_series.cache_clear()
    Base.metadata.create_all(engine)
    with session_scope() as db:
        already = db.query(Port).count() > 0
        if already and not force:
            return False
        reset_database(db)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the PortPulse demo database.")
    parser.add_argument("--force", action="store_true", help="rebuild even if data exists")
    args = parser.parse_args()
    seeded = ensure_seeded(force=args.force)
    with session_scope() as db:
        counts = {
            "ports": db.query(Port).count(),
            "legs": db.query(Leg).count(),
            "port_daily": db.query(PortDaily).count(),
            "shipments": db.query(Shipment).count(),
            "events": db.query(Event).count(),
        }
    action = "seeded" if seeded else "already present"
    print(f"PortPulse database {action}: {counts}")
    print(f"Simulated today: {SEED_TODAY.isoformat()}  (history from {HISTORY_START.isoformat()})")


if __name__ == "__main__":
    main()
