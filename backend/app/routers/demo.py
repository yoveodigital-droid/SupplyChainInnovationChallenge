"""Demo clock, scenario control and prediction feedback."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feedback
from ..schemas import DemoStateOut, FeedbackIn, FeedbackOut
from ..services import scenario

router = APIRouter(tags=["demo"])


@router.get("/demo/state", response_model=DemoStateOut)
def demo_state(db: Session = Depends(get_db)) -> DemoStateOut:
    return DemoStateOut.model_validate(scenario.state_view(db))


@router.post("/demo/advance", response_model=DemoStateOut)
def demo_advance(db: Session = Depends(get_db)) -> DemoStateOut:
    view = scenario.advance_day(db)
    db.commit()
    return DemoStateOut.model_validate(view)


@router.post("/demo/trigger", response_model=DemoStateOut)
def demo_trigger(db: Session = Depends(get_db)) -> DemoStateOut:
    view = scenario.trigger(db)
    db.commit()
    return DemoStateOut.model_validate(view)


@router.post("/demo/reset", response_model=DemoStateOut)
def demo_reset(db: Session = Depends(get_db)) -> DemoStateOut:
    view = scenario.reset(db)
    db.commit()
    return DemoStateOut.model_validate(view)


@router.post("/feedback", response_model=FeedbackOut)
def submit_feedback(body: FeedbackIn, db: Session = Depends(get_db)) -> FeedbackOut:
    state = scenario.get_state(db)
    row = Feedback(
        shipment_id=body.shipment_id,
        helpful=body.helpful,
        note=body.note[:240],
        sim_date=state.sim_date,
    )
    db.add(row)
    db.commit()
    return FeedbackOut.model_validate(row)


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(db: Session = Depends(get_db)) -> list[FeedbackOut]:
    rows = db.execute(select(Feedback).order_by(Feedback.id.desc()).limit(50)).scalars()
    return [FeedbackOut.model_validate(r) for r in rows]
