"""Per-request assembly of the service stack.

Every read endpoint needs the same three things bound to the same simulated
"today": a forecaster, an exposure engine and a recommender. Building them is
cheap (the trained model is cached in-process) and keeps each request
internally consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import Depends
from sqlalchemy.orm import Session

from .db import get_db
from .services.events import EventOverlay
from .services.exposure import ExposureEngine
from .services.forecast import PortForecaster
from .services.recommend import Recommender
from .services.scenario import state_view


@dataclass
class Context:
    db: Session
    sim_date: date
    data_version: int
    overlay: EventOverlay
    forecaster: PortForecaster
    exposure: ExposureEngine
    recommender: Recommender


def get_context(db: Session = Depends(get_db)) -> Context:
    state = state_view(db)
    overlay = EventOverlay(db, state.sim_date)
    forecaster = PortForecaster(db, state.sim_date, state.data_version, overlay=overlay)
    exposure = ExposureEngine(db, forecaster)
    recommender = Recommender(db, exposure, state.sim_date)
    return Context(
        db=db,
        sim_date=state.sim_date,
        data_version=state.data_version,
        overlay=overlay,
        forecaster=forecaster,
        exposure=exposure,
        recommender=recommender,
    )
