"""PortPulse API.

Runs entirely offline: SQLite on disk, a scikit-learn model trained once at
startup and cached, no outbound calls of any kind.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import DISCLAIMER, MAX_HORIZON_DAYS, RISK_AMBER, RISK_RED, SUPPORTED_LANGUAGES
from .db import session_scope
from .deps import Context, get_context
from .routers import demo, forecasts, reference, shipments
from .schemas import DemoStateOut, MetaOut
from .seed import ensure_seeded
from .services.forecast import get_bundle

log = logging.getLogger("portpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    seeded = ensure_seeded()
    log.info("database %s", "seeded" if seeded else "already present")
    with session_scope() as db:
        bundle = get_bundle(db)
        log.info(
            "forecaster ready: %s rows, holdout MAE %.2f (naive %.2f)",
            bundle.trained_rows,
            bundle.metrics.get("congestion_mae", 0.0),
            bundle.metrics.get("congestion_mae_naive", 0.0),
        )
    yield


app = FastAPI(
    title="PortPulse API",
    version="0.1.0",
    summary="Supply-chain disruption early warning and adaptive rerouting for SME exporters.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo runs on one laptop; no auth, no credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reference.router, prefix="/api")
app.include_router(forecasts.router, prefix="/api")
app.include_router(shipments.router, prefix="/api")
app.include_router(demo.router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/meta", response_model=MetaOut, tags=["meta"])
def meta(ctx: Context = Depends(get_context)) -> MetaOut:
    bundle = get_bundle(ctx.db)
    from .services.scenario import state_view

    return MetaOut(
        name="PortPulse",
        tagline="Disruption early warning and adaptive rerouting for small exporters.",
        disclaimer=DISCLAIMER,
        languages=list(SUPPORTED_LANGUAGES),
        risk_thresholds={"amber": RISK_AMBER, "red": RISK_RED},
        max_horizon_days=MAX_HORIZON_DAYS,
        model={
            "algorithm": "HistGradientBoostingRegressor + quantile intervals",
            "training_rows": bundle.trained_rows,
            "trained_through": bundle.trained_through.isoformat(),
            "congestion_mae": round(bundle.metrics.get("congestion_mae", 0.0), 3),
            "congestion_mae_naive": round(bundle.metrics.get("congestion_mae_naive", 0.0), 3),
            "waiting_mae": round(bundle.metrics.get("waiting_mae", 0.0), 3),
            "waiting_mae_naive": round(bundle.metrics.get("waiting_mae_naive", 0.0), 3),
        },
        demo=DemoStateOut.model_validate(state_view(ctx.db)),
    )
