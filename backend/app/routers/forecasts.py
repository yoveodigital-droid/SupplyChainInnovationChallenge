"""Forecast endpoints, including the port-authority pressure view."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..config import MAX_HORIZON_DAYS
from ..deps import Context, get_context
from ..models import Event, Port, PortDaily, Shipment
from ..schemas import (
    ContributionOut,
    EventOut,
    ForecastOut,
    ForecastPointOut,
    ObservationOut,
    PortPressureOut,
)
from ..services.forecast import get_bundle
from .reference import port_status

router = APIRouter(tags=["forecasts"])

MODEL_NOTE = (
    "Gradient-boosted regressors (scikit-learn) trained on 18 months of daily port "
    "observations, with 10th/90th-percentile quantile models for the band. Declared "
    "disruption events are added on top via the port-graph propagation model and "
    "reported separately as 'event uplift'."
)


def _history(ctx: Context, port_id: str, days: int) -> list[ObservationOut]:
    rows = ctx.db.execute(
        select(PortDaily)
        .where(
            PortDaily.port_id == port_id,
            PortDaily.day <= ctx.sim_date,
            PortDaily.day > ctx.sim_date - timedelta(days=days),
        )
        .order_by(PortDaily.day)
    ).scalars()
    return [
        ObservationOut(
            day=r.day,
            congestion_index=round(r.congestion_index, 2),
            waiting_days=round(r.waiting_days, 2),
            weather_severity=round(r.weather_severity, 2),
            vessel_arrivals=r.vessel_arrivals,
        )
        for r in rows
    ]


@router.get("/ports/{port_id}/history", response_model=list[ObservationOut])
def port_history(
    port_id: str,
    days: int = Query(120, ge=7, le=548),
    ctx: Context = Depends(get_context),
) -> list[ObservationOut]:
    if ctx.db.get(Port, port_id) is None:
        raise HTTPException(404, f"unknown port {port_id}")
    return _history(ctx, port_id, days)


@router.get("/ports/{port_id}/forecast", response_model=ForecastOut)
def port_forecast(
    port_id: str,
    horizon: int = Query(MAX_HORIZON_DAYS, ge=1, le=MAX_HORIZON_DAYS),
    explain_horizon: int | None = Query(None, ge=1, le=MAX_HORIZON_DAYS),
    ctx: Context = Depends(get_context),
) -> ForecastOut:
    port = ctx.db.get(Port, port_id)
    if port is None:
        raise HTTPException(404, f"unknown port {port_id}")
    points = ctx.forecaster.forecast(port_id, horizon)
    explain_at = explain_horizon or min(7, horizon)
    return ForecastOut(
        port_id=port_id,
        port_name=port.name,
        as_of=ctx.sim_date,
        horizon_days=horizon,
        congestion_threshold=port.congestion_threshold,
        points=[ForecastPointOut.model_validate(p) for p in points],
        explanation=[
            ContributionOut.model_validate(c) for c in ctx.forecaster.explain(port_id, explain_at)
        ],
        model_note=MODEL_NOTE,
    )


@router.get("/ports/{port_id}/explain", response_model=list[ContributionOut])
def port_explain(
    port_id: str,
    horizon: int = Query(7, ge=1, le=MAX_HORIZON_DAYS),
    ctx: Context = Depends(get_context),
) -> list[ContributionOut]:
    if ctx.db.get(Port, port_id) is None:
        raise HTTPException(404, f"unknown port {port_id}")
    return [ContributionOut.model_validate(c) for c in ctx.forecaster.explain(port_id, horizon)]


def _plain_summary(port: Port, points, inbound: int, peak_day, peak: float) -> str:
    over = [p for p in points if p.congestion >= port.congestion_threshold]
    worst_wait = max(p.waiting_days for p in points)
    if not over:
        return (
            f"{port.name} looks manageable for the next {len(points)} days. Congestion peaks "
            f"around {peak:.0f} on {peak_day:%-d %b}, below the {port.congestion_threshold:.0f} "
            f"disruption threshold, and berth waiting stays under {worst_wait:.1f} days. "
            f"{inbound} tracked shipments are inbound."
        )
    first = over[0]
    return (
        f"Expect pressure at {port.name} from {first.day:%-d %b}: congestion crosses the "
        f"{port.congestion_threshold:.0f} threshold on {len(over)} of the next {len(points)} days "
        f"and peaks near {peak:.0f} on {peak_day:%-d %b}. Berth waiting reaches about "
        f"{worst_wait:.1f} days at the worst point, with {inbound} tracked shipments inbound. "
        f"Model confidence at the peak is {int(round(next(p.confidence for p in points if p.day == peak_day) * 100))}%."
    )


@router.get("/ports/{port_id}/pressure", response_model=PortPressureOut)
def port_pressure(
    port_id: str,
    horizon: int = Query(14, ge=1, le=MAX_HORIZON_DAYS),
    history_days: int = Query(60, ge=7, le=548),
    ctx: Context = Depends(get_context),
) -> PortPressureOut:
    port = ctx.db.get(Port, port_id)
    if port is None:
        raise HTTPException(404, f"unknown port {port_id}")

    points = ctx.forecaster.forecast(port_id, horizon)
    peak = max(points, key=lambda p: p.congestion)
    inbound = ctx.db.execute(
        select(Shipment).where(Shipment.dest_id == port_id)
    ).scalars().all()

    events = ctx.db.execute(
        select(Event)
        .where(Event.day <= ctx.sim_date, Event.day >= ctx.sim_date - timedelta(days=30))
        .order_by(Event.day.desc(), Event.severity.desc())
        .limit(12)
    ).scalars().all()
    # Upstream = anything at this port, at a chokepoint it depends on, or at a
    # port that feeds it.
    upstream_ports = {
        leg.origin_id for leg in ctx.recommender.legs.values() if leg.dest_id == port_id
    } | {port_id}
    relevant = [
        e for e in events if e.chokepoint_id is not None or e.port_id in upstream_ports
    ]

    return PortPressureOut(
        port=port_status(ctx, port),
        as_of=ctx.sim_date,
        history=_history(ctx, port_id, history_days),
        forecast=[ForecastPointOut.model_validate(p) for p in points],
        explanation=[ContributionOut.model_validate(c) for c in ctx.forecaster.explain(port_id, 7)],
        upstream_events=[EventOut.model_validate(e) for e in relevant],
        inbound_shipments=len(inbound),
        summary=_plain_summary(port, points, len(inbound), peak.day, peak.congestion),
        peak_day=peak.day,
        peak_congestion=peak.congestion,
    )


@router.get("/model", tags=["meta"])
def model_card(ctx: Context = Depends(get_context)) -> dict:
    bundle = get_bundle(ctx.db)
    return {
        "version": bundle.version,
        "algorithm": "HistGradientBoostingRegressor (squared error + 0.1/0.9 quantile)",
        "training_rows": bundle.trained_rows,
        "trained_through": bundle.trained_through.isoformat(),
        "holdout_metrics": {k: round(v, 3) for k, v in bundle.metrics.items()},
        "note": MODEL_NOTE,
    }
