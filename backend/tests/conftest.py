"""Test fixtures.

Tests run against a throwaway database in a temp directory but share the
trained-model cache with the dev environment, so the suite does not retrain a
gradient-boosting model on every run.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="portpulse-tests-"))

# Must be set before anything imports app.config.
os.environ.setdefault("PORTPULSE_DATA_DIR", str(_TMP))
os.environ.setdefault("PORTPULSE_MODEL_DIR", str(_BACKEND / "data" / "models"))
os.environ.setdefault("PORTPULSE_DATABASE_URL", f"sqlite:///{_TMP / 'portpulse.db'}")

from app.db import session_scope  # noqa: E402
from app.seed import ensure_seeded  # noqa: E402
from app.services import scenario  # noqa: E402
from app.services.exposure import ExposureEngine  # noqa: E402
from app.services.forecast import PortForecaster  # noqa: E402
from app.services.recommend import Recommender  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seeded() -> None:
    ensure_seeded(force=True)


@pytest.fixture
def db():
    """A session on a freshly re-seeded database."""
    with session_scope() as session:
        scenario.reset(session)
        session.commit()
        yield session


class Stack:
    """Forecaster + exposure engine + recommender bound to the current sim date."""

    def __init__(self, session):
        self.db = session
        self.refresh()

    def refresh(self) -> None:
        state = scenario.state_view(self.db)
        self.sim_date = state.sim_date
        self.forecaster = PortForecaster(self.db, state.sim_date, state.data_version)
        self.exposure = ExposureEngine(self.db, self.forecaster)
        self.recommender = Recommender(self.db, self.exposure, state.sim_date)

    def trigger(self) -> None:
        scenario.trigger(self.db)
        self.db.flush()
        self.refresh()

    def advance(self, days: int = 1) -> None:
        for _ in range(days):
            scenario.advance_day(self.db)
        self.db.flush()
        self.refresh()


@pytest.fixture
def stack(db) -> Stack:
    return Stack(db)


@pytest.fixture
def client():
    """FastAPI test client on the same throwaway database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with session_scope() as session:
        scenario.reset(session)
        session.commit()
    with TestClient(app) as test_client:
        yield test_client
