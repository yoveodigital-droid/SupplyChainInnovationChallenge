"""Shipment endpoints: exposure, recommendations, alerts, accept/revert."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..config import SUPPORTED_LANGUAGES
from ..deps import Context, get_context
from ..models import Persona, Port, Shipment
from ..schemas import (
    AcceptIn,
    AcceptOut,
    AlertOut,
    ChatMessageOut,
    ExposureOut,
    OptionOut,
    RecommendationsOut,
    ShipmentOut,
)
from ..services.alerts import compose_alert, compose_confirmation
from ..services.exposure import Exposure, Plan
from ..services.recommend import (
    CARBON_PRICE_USD_PER_TONNE,
    HOLDING_COST_RATE_PER_DAY,
    LATE_PENALTY_RATE_PER_DAY,
    Option,
)

router = APIRouter(tags=["shipments"])


def _plan(ctx: Context, shipment: Shipment) -> Plan:
    return Plan(
        legs=[ctx.recommender.legs[i] for i in shipment.leg_ids],
        etd=max(shipment.etd, ctx.sim_date),
        teu=shipment.teu,
        perishable=shipment.perishable,
        shelf_life_days=shipment.shelf_life_days,
        value_usd=shipment.value_usd,
        required_by=shipment.required_by,
    )


def _exposure(ctx: Context, shipment: Shipment) -> Exposure:
    return ctx.exposure.evaluate(_plan(ctx, shipment))


def _shipment_out(ctx: Context, shipment: Shipment, exposure: Exposure) -> ShipmentOut:
    ports = ctx.exposure.ports
    return ShipmentOut(
        **{
            k: getattr(shipment, k)
            for k in (
                "id", "persona_id", "reference", "origin_id", "dest_id", "leg_ids", "etd",
                "required_by", "cargo", "cargo_short", "teu", "perishable", "shelf_life_days", "value_usd",
                "status", "buyer", "applied_option",
            )
        },
        origin_name=ports[shipment.origin_id].name,
        dest_name=ports[shipment.dest_id].name,
        rerouted=shipment.applied_option is not None,
        risk_level=exposure.risk_level,
        risk_score=exposure.risk_score,
        expected_delay_days=exposure.expected_delay_days,
        spoilage_probability=exposure.spoilage_probability,
    )


def _exposure_out(ctx: Context, shipment: Shipment, exposure: Exposure) -> ExposureOut:
    return ExposureOut(
        shipment_id=shipment.id,
        required_by=shipment.required_by,
        delay_distribution=ctx.exposure.delay_distribution(exposure),
        **{
            k: getattr(exposure, k)
            for k in (
                "etd", "scheduled_transit_days", "scheduled_arrival", "expected_delay_days",
                "delay_p10", "delay_p90", "expected_arrival", "prob_delay_over_3",
                "prob_delay_over_7", "prob_miss_deadline", "demurrage_usd", "demurrage_days",
                "spoilage_probability", "spoilage_band", "expected_spoilage_loss_usd",
                "risk_score", "risk_level", "confidence", "calls", "legs", "drivers",
            )
        },
    )


def _get(ctx: Context, shipment_id: str) -> Shipment:
    shipment = ctx.db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(404, f"unknown shipment {shipment_id}")
    return shipment


@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(
    persona: str | None = None, ctx: Context = Depends(get_context)
) -> list[ShipmentOut]:
    stmt = select(Shipment).order_by(Shipment.etd, Shipment.id)
    if persona:
        if ctx.db.get(Persona, persona) is None:
            raise HTTPException(404, f"unknown persona {persona}")
        stmt = stmt.where(Shipment.persona_id == persona)
    out = []
    for shipment in ctx.db.execute(stmt).scalars():
        out.append(_shipment_out(ctx, shipment, _exposure(ctx, shipment)))
    # Riskiest first — a forwarder opens the list to triage, not to browse.
    out.sort(key=lambda s: (-s.risk_score, s.etd))
    return out


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, ctx: Context = Depends(get_context)) -> ShipmentOut:
    shipment = _get(ctx, shipment_id)
    return _shipment_out(ctx, shipment, _exposure(ctx, shipment))


@router.get("/shipments/{shipment_id}/exposure", response_model=ExposureOut)
def get_exposure(shipment_id: str, ctx: Context = Depends(get_context)) -> ExposureOut:
    shipment = _get(ctx, shipment_id)
    return _exposure_out(ctx, shipment, _exposure(ctx, shipment))


def _options(ctx: Context, shipment: Shipment) -> list[Option]:
    return ctx.recommender.recommend(shipment)


@router.get("/shipments/{shipment_id}/recommendations", response_model=RecommendationsOut)
def get_recommendations(
    shipment_id: str, ctx: Context = Depends(get_context)
) -> RecommendationsOut:
    shipment = _get(ctx, shipment_id)
    options = _options(ctx, shipment)
    return RecommendationsOut(
        shipment_id=shipment.id,
        as_of=ctx.sim_date,
        options=[OptionOut.model_validate(o) for o in options],
        objective=(
            "Minimise expected total landed cost: freight + demurrage + expected spoilage "
            "loss + late-delivery penalty + inventory holding + carbon. Options dominated "
            "on cost, timing, risk and emissions by another shown option are pruned."
        ),
        assumptions={
            "carbon_price_usd_per_tonne": CARBON_PRICE_USD_PER_TONNE,
            "holding_cost_rate_per_day": HOLDING_COST_RATE_PER_DAY,
            "late_penalty_rate_per_day_perishable": LATE_PENALTY_RATE_PER_DAY["perishable"],
            "late_penalty_rate_per_day_dry": LATE_PENALTY_RATE_PER_DAY["dry"],
            "note": "All figures are modelled on synthetic corridor data.",
        },
    )


@router.get("/shipments/{shipment_id}/alert", response_model=AlertOut)
def get_alert(
    shipment_id: str,
    lang: str = Query("en"),
    ctx: Context = Depends(get_context),
) -> AlertOut:
    shipment = _get(ctx, shipment_id)
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, f"unsupported language {lang}")
    exposure = _exposure(ctx, shipment)
    options = _options(ctx, shipment)
    return AlertOut.model_validate(compose_alert(shipment, exposure, options, lang))


@router.post("/shipments/{shipment_id}/accept", response_model=AcceptOut)
def accept_option(
    shipment_id: str,
    body: AcceptIn,
    lang: str = Query("en"),
    ctx: Context = Depends(get_context),
) -> AcceptOut:
    shipment = _get(ctx, shipment_id)
    options = _options(ctx, shipment)
    option = next((o for o in options if o.id == body.option_id), None)
    if option is None:
        raise HTTPException(404, f"unknown option {body.option_id}")

    if option.kind != "hold":
        if shipment.original_leg_ids is None:
            shipment.original_leg_ids = list(shipment.leg_ids)
            shipment.original_etd = shipment.etd
        shipment.leg_ids = list(option.leg_ids)
        shipment.etd = option.etd
        shipment.dest_id = option.route_ports[-1]
        shipment.applied_option = option.label
        shipment.status = "rerouted"
        ctx.db.flush()

    exposure = _exposure(ctx, shipment)
    message = compose_confirmation(shipment, exposure, option, lang)
    ctx.db.commit()
    return AcceptOut(
        shipment=_shipment_out(ctx, shipment, exposure),
        message=ChatMessageOut.model_validate(message),
        exposure=_exposure_out(ctx, shipment, exposure),
    )


@router.post("/shipments/{shipment_id}/revert", response_model=ShipmentOut)
def revert(shipment_id: str, ctx: Context = Depends(get_context)) -> ShipmentOut:
    shipment = _get(ctx, shipment_id)
    if shipment.original_leg_ids:
        shipment.leg_ids = list(shipment.original_leg_ids)
        shipment.etd = shipment.original_etd
        shipment.dest_id = ctx.recommender.legs[shipment.leg_ids[-1]].dest_id
        shipment.original_leg_ids = None
        shipment.original_etd = None
        shipment.applied_option = None
        shipment.status = "booked"
        ctx.db.commit()
    return _shipment_out(ctx, shipment, _exposure(ctx, shipment))
