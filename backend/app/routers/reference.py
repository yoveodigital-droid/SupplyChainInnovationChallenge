"""Reference data: ports, legs, chokepoints, personas, event feed."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from ..config import RISK_AMBER, RISK_RED
from ..deps import Context, get_context
from ..models import Chokepoint, Event, Leg, Persona, Port, PortDaily, Shipment
from ..services.events import RISK_LOOKAHEAD_DAYS
from ..schemas import (
    ChokepointOut,
    EventOut,
    LegOut,
    PersonaOut,
    PortOut,
    PortStatusOut,
)

router = APIRouter(tags=["reference"])


def _band(p: float) -> str:
    return "red" if p >= RISK_RED else "amber" if p >= RISK_AMBER else "green"


def port_status(ctx: Context, port: Port) -> PortStatusOut:
    latest = ctx.db.execute(
        select(PortDaily)
        .where(PortDaily.port_id == port.id, PortDaily.day <= ctx.sim_date)
        .order_by(PortDaily.day.desc())
        .limit(1)
    ).scalar_one_or_none()
    point = ctx.forecaster.forecast(port.id, 7)[-1]
    return PortStatusOut(
        **PortOut.model_validate(port).model_dump(),
        congestion_now=round(latest.congestion_index, 2) if latest else port.base_congestion,
        waiting_now=round(latest.waiting_days, 2) if latest else port.base_waiting_days,
        weather_now=round(latest.weather_severity, 2) if latest else 0.0,
        congestion_7d=point.congestion,
        disruption_probability_7d=point.disruption_probability,
        confidence_7d=point.confidence,
        risk_level=_band(point.disruption_probability),
    )


@router.get("/ports", response_model=list[PortStatusOut])
def list_ports(ctx: Context = Depends(get_context)) -> list[PortStatusOut]:
    ports = ctx.db.execute(select(Port).order_by(Port.name)).scalars().all()
    return [port_status(ctx, p) for p in ports]


@router.get("/ports/{port_id}", response_model=PortStatusOut)
def get_port(port_id: str, ctx: Context = Depends(get_context)) -> PortStatusOut:
    port = ctx.db.get(Port, port_id)
    if port is None:
        raise HTTPException(404, f"unknown port {port_id}")
    return port_status(ctx, port)


@router.get("/legs", response_model=list[LegOut])
def list_legs(ctx: Context = Depends(get_context)) -> list[LegOut]:
    legs = ctx.db.execute(select(Leg).order_by(Leg.id)).scalars().all()
    return [LegOut.model_validate(leg) for leg in legs]


@router.get("/chokepoints", response_model=list[ChokepointOut])
def list_chokepoints(ctx: Context = Depends(get_context)) -> list[ChokepointOut]:
    out = []
    for cp in ctx.db.execute(select(Chokepoint).order_by(Chokepoint.name)).scalars():
        risk = ctx.overlay.chokepoint_risk(
            ctx.db, cp.id, ctx.sim_date + timedelta(days=RISK_LOOKAHEAD_DAYS)
        )
        model = ChokepointOut.model_validate(cp)
        model.current_risk = risk
        model.risk_level = _band(risk)
        out.append(model)
    return out


@router.get("/personas", response_model=list[PersonaOut])
def list_personas(ctx: Context = Depends(get_context)) -> list[PersonaOut]:
    counts = dict(
        ctx.db.execute(
            select(Shipment.persona_id, func.count(Shipment.id)).group_by(Shipment.persona_id)
        ).all()
    )
    order = {"amina": 0, "rafael": 1, "jeddah_pa": 2}
    personas = ctx.db.execute(select(Persona)).scalars().all()
    personas.sort(key=lambda p: order.get(p.id, 99))
    out = []
    for p in personas:
        model = PersonaOut.model_validate(p)
        model.shipment_count = int(counts.get(p.id, 0))
        out.append(model)
    return out


@router.get("/events", response_model=list[EventOut])
def list_events(
    limit: int = Query(25, ge=1, le=200),
    days: int = Query(60, ge=1, le=600),
    port_id: str | None = None,
    ctx: Context = Depends(get_context),
) -> list[EventOut]:
    stmt = (
        select(Event)
        .where(Event.day <= ctx.sim_date, Event.day >= ctx.sim_date - timedelta(days=days))
        .order_by(Event.day.desc(), Event.severity.desc())
        .limit(limit)
    )
    if port_id:
        stmt = stmt.where(Event.port_id == port_id)
    return [EventOut.model_validate(e) for e in ctx.db.execute(stmt).scalars()]
