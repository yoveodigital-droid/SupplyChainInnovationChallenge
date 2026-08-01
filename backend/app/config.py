"""Central configuration and demo-wide constants.

Everything that a future team would need to re-point at real feeds lives behind
these constants or behind the service interfaces in ``app/services``.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PORTPULSE_DATA_DIR", BASE_DIR / "data"))
MODEL_DIR = Path(os.environ.get("PORTPULSE_MODEL_DIR", DATA_DIR / "models"))
DB_PATH = DATA_DIR / "portpulse.db"
DATABASE_URL = os.environ.get("PORTPULSE_DATABASE_URL", f"sqlite:///{DB_PATH}")

# Deterministic everything. The demo must be byte-identical on every laptop.
RANDOM_SEED = 20240611

# The synthetic world is anchored to a fixed "today" so the pitch never drifts.
SEED_TODAY = date(2025, 8, 6)
HISTORY_DAYS = 548  # ~18 months of daily observations per port

# Forecast horizon exposed by the API.
MAX_HORIZON_DAYS = 21

# Risk banding thresholds (shared by API and UI).
RISK_AMBER = 0.30
RISK_RED = 0.60

# Spoilage banding for perishables.
SPOILAGE_AMBER = 0.20
SPOILAGE_RED = 0.45

DISCLAIMER = (
    "Demo running on synthetic data modeled on the Southeast Asia–Gulf corridor."
)

SUPPORTED_LANGUAGES = ("en", "sw")
