"""Forecasting service.

Gradient-boosted regressors predict port congestion index and vessel waiting
days 1–21 days ahead, with 80% prediction intervals, a disruption probability
and a confidence score.

Design notes
------------
* **One global model per (target, quantile), horizon as a feature.** With 28
  ports × 18 months there is not enough data per port for 28 separate models,
  and a global model lets a port borrow shock-shape information from its peers.
  Horizon is an input rather than 21 separate models, so the intervals stay
  monotone in horizon and training stays fast.
* **Direct multi-horizon**, not recursive: no error compounding.
* **Quantile regression** gives honest intervals rather than a fabricated
  ± band.
* Training uses only *seeded* history (``scenario == False``). The live demo
  scenario changes the observations fed in at inference time, so the forecast
  reacts to the shock without ever retraining mid-pitch.

Swap seam
---------
``load_observations()`` is the only DB read. Point it at a real telemetry table
and nothing downstream changes.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import MAX_HORIZON_DAYS, MODEL_DIR, RANDOM_SEED, SEED_TODAY
from ..models import Port, PortDaily
from .events import EventOverlay

MODEL_PATH = Path(MODEL_DIR) / "forecaster.joblib"
MODEL_VERSION = 5

# Horizons sampled during training. Horizon is a model feature, so any value in
# 1..MAX_HORIZON_DAYS can still be predicted.
TRAIN_HORIZONS = (1, 2, 3, 5, 7, 10, 14, 17, 21)
QUANTILES = (0.1, 0.9)
Z80 = 2.5631  # width of the 10th–90th percentile band of a standard normal

CONGESTION_LAGS = (0, 1, 2, 4, 6, 13, 20, 27)
WAITING_LAGS = (0, 2, 6)
WEATHER_LAGS = (0, 2, 6)

FEATURE_LABELS = {
    "c_lag0": "congestion today",
    "c_lag1": "congestion yesterday",
    "c_lag2": "congestion 3 days ago",
    "c_lag4": "congestion 5 days ago",
    "c_lag6": "congestion last week",
    "c_lag13": "congestion 2 weeks ago",
    "c_lag20": "congestion 3 weeks ago",
    "c_lag27": "congestion 4 weeks ago",
    "c_ma3": "3-day congestion average",
    "c_ma7": "7-day congestion average",
    "c_ma14": "14-day congestion average",
    "c_ma28": "28-day congestion average",
    "c_sd7": "recent volatility",
    "c_trend7": "week-on-week trend",
    "c_trend_ma": "short vs medium-term trend",
    "w_lag0": "waiting time today",
    "w_lag2": "waiting time 3 days ago",
    "w_lag6": "waiting time last week",
    "w_ma7": "7-day waiting-time average",
    "wx_lag0": "weather today",
    "wx_lag2": "weather 3 days ago",
    "wx_lag6": "weather last week",
    "wx_ma7": "7-day weather average",
    "arr_ma7": "recent vessel arrivals",
    "horizon": "how far ahead we are looking",
    "doy_sin": "time of year",
    "doy_cos": "time of year",
    "weekday": "day of the week",
    "port_code": "which port",
    "base_congestion": "this port's normal level",
    "capacity": "this port's size",
}

# Semantic groups used by the "How was this predicted?" tooltip.
FEATURE_GROUPS: dict[str, list[str]] = {
    "recent_congestion": [f"c_lag{k}" for k in CONGESTION_LAGS] + ["c_ma3", "c_ma7"],
    "congestion_trend": ["c_trend7", "c_trend_ma", "c_ma14", "c_ma28", "c_sd7"],
    "waiting_times": [f"w_lag{k}" for k in WAITING_LAGS] + ["w_ma7"],
    "weather": [f"wx_lag{k}" for k in WEATHER_LAGS] + ["wx_ma7"],
    "vessel_arrivals": ["arr_ma7"],
    "season": ["doy_sin", "doy_cos"],
    "weekday": ["weekday"],
    "port_baseline": ["base_congestion"],
}

GROUP_LABELS: dict[str, str] = {
    "recent_congestion": "Congestion reported at this port over the last few days",
    "congestion_trend": "Whether congestion is building or easing week on week",
    "waiting_times": "Vessel waiting times currently being reported",
    "weather": "Weather severity now and over the past week",
    "vessel_arrivals": "How many vessels have been arriving lately",
    "season": "Time of year (monsoon, peak-season and holiday patterns)",
    "weekday": "Day of the week the vessel is due",
    "port_baseline": "This port's normal operating level",
}

ORIGIN_FEATURES: list[str] = (
    [f"c_lag{k}" for k in CONGESTION_LAGS]
    + ["c_ma3", "c_ma7", "c_ma14", "c_ma28", "c_sd7", "c_trend7", "c_trend_ma"]
    + [f"w_lag{k}" for k in WAITING_LAGS]
    + ["w_ma7"]
    + [f"wx_lag{k}" for k in WEATHER_LAGS]
    + ["wx_ma7", "arr_ma7"]
)
STATIC_FEATURES = ["port_code", "base_congestion", "capacity"]
TARGET_FEATURES = ["horizon", "doy_sin", "doy_cos", "weekday"]
FEATURE_COLUMNS = ORIGIN_FEATURES + STATIC_FEATURES + TARGET_FEATURES


# --------------------------------------------------------------------------- #
# Data access (the swap seam)
# --------------------------------------------------------------------------- #


def load_observations(
    db: Session,
    seeded_only: bool = False,
    since: date | None = None,
    until: date | None = None,
) -> pd.DataFrame:
    stmt = select(
        PortDaily.port_id,
        PortDaily.day,
        PortDaily.congestion_index,
        PortDaily.waiting_days,
        PortDaily.weather_severity,
        PortDaily.vessel_arrivals,
    )
    if seeded_only:
        # Training is pinned to the seed window: the model must be identical
        # however far the presenter has advanced the demo clock, and it must
        # never learn from days the scenario has already touched.
        stmt = stmt.where(PortDaily.scenario.is_(False), PortDaily.day <= SEED_TODAY)
    if since is not None:
        stmt = stmt.where(PortDaily.day >= since)
    if until is not None:
        stmt = stmt.where(PortDaily.day <= until)
    rows = db.execute(stmt).all()
    frame = pd.DataFrame(rows, columns=["port_id", "day", "congestion", "waiting", "weather", "arrivals"])
    frame["day"] = pd.to_datetime(frame["day"])
    return frame.sort_values(["port_id", "day"]).reset_index(drop=True)


def load_port_static(db: Session) -> pd.DataFrame:
    rows = db.execute(
        select(Port.id, Port.base_congestion, Port.capacity_teu_per_day, Port.congestion_threshold)
    ).all()
    return pd.DataFrame(rows, columns=["port_id", "base_congestion", "capacity", "threshold"])


# --------------------------------------------------------------------------- #
# Feature engineering — shared by training and inference
# --------------------------------------------------------------------------- #


def build_origin_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Features known at forecast origin ``t`` (uses observations up to and including t)."""
    out = []
    for port_id, grp in frame.groupby("port_id", sort=True):
        g = grp.sort_values("day").reset_index(drop=True)
        f = pd.DataFrame({"port_id": port_id, "day": g["day"]})
        for k in CONGESTION_LAGS:
            f[f"c_lag{k}"] = g["congestion"].shift(k)
        for k in WAITING_LAGS:
            f[f"w_lag{k}"] = g["waiting"].shift(k)
        for k in WEATHER_LAGS:
            f[f"wx_lag{k}"] = g["weather"].shift(k)
        for w in (3, 7, 14, 28):
            f[f"c_ma{w}"] = g["congestion"].rolling(w, min_periods=1).mean()
        f["c_sd7"] = g["congestion"].rolling(7, min_periods=2).std().fillna(0.0)
        f["w_ma7"] = g["waiting"].rolling(7, min_periods=1).mean()
        f["wx_ma7"] = g["weather"].rolling(7, min_periods=1).mean()
        f["arr_ma7"] = g["arrivals"].rolling(7, min_periods=1).mean()
        f["c_trend7"] = f["c_lag0"] - f["c_lag6"]
        f["c_trend_ma"] = f["c_ma3"] - f["c_ma14"]
        out.append(f)
    return pd.concat(out, ignore_index=True)


def _calendar(days: pd.Series) -> pd.DataFrame:
    doy = days.dt.dayofyear.astype(float)
    return pd.DataFrame(
        {
            "doy_sin": np.sin(2 * np.pi * doy / 365.25),
            "doy_cos": np.cos(2 * np.pi * doy / 365.25),
            "weekday": days.dt.weekday.astype(float),
        },
        index=days.index,
    )


def _port_codes(port_ids: list[str]) -> dict[str, int]:
    return {pid: i for i, pid in enumerate(sorted(port_ids))}


def build_training_table(frame: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
    origin = build_origin_features(frame)
    origin = origin.merge(static[["port_id", "base_congestion", "capacity"]], on="port_id")
    codes = _port_codes(static["port_id"].tolist())
    origin["port_code"] = origin["port_id"].map(codes).astype(float)

    truth = frame[["port_id", "day", "congestion", "waiting"]].rename(
        columns={"day": "target_day", "congestion": "y_congestion", "waiting": "y_waiting"}
    )

    blocks = []
    for h in TRAIN_HORIZONS:
        block = origin.copy()
        block["horizon"] = float(h)
        block["target_day"] = block["day"] + pd.Timedelta(days=h)
        block = block.merge(truth, on=["port_id", "target_day"], how="inner")
        blocks.append(block)

    table = pd.concat(blocks, ignore_index=True)
    table = pd.concat([table, _calendar(table["target_day"])], axis=1)
    return table.dropna(subset=FEATURE_COLUMNS + ["y_congestion", "y_waiting"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Model bundle
# --------------------------------------------------------------------------- #


@dataclass
class ForecastBundle:
    version: int
    # Signature of the data the model was fitted on. A cached model whose
    # signature no longer matches the database is silently wrong — it happens
    # whenever the demo clock has moved since training — so it is rejected.
    signature: tuple
    models: dict[str, HistGradientBoostingRegressor]
    port_codes: dict[str, int]
    feature_medians: dict[str, float]
    port_congestion_std: dict[str, float]
    port_thresholds: dict[str, float]
    trained_rows: int
    trained_through: date
    metrics: dict[str, float] = field(default_factory=dict)


def _make_model(loss: str, quantile: float | None = None) -> HistGradientBoostingRegressor:
    kwargs = dict(
        loss=loss,
        max_iter=260,
        learning_rate=0.07,
        max_depth=6,
        min_samples_leaf=25,
        l2_regularization=0.6,
        early_stopping=False,
        random_state=RANDOM_SEED,
    )
    if quantile is not None:
        kwargs["quantile"] = quantile
    return HistGradientBoostingRegressor(**kwargs)


def training_signature(db: Session) -> tuple:
    from sqlalchemy import func

    rows, last_day = db.execute(
        select(func.count(PortDaily.id), func.max(PortDaily.day)).where(
            PortDaily.scenario.is_(False), PortDaily.day <= SEED_TODAY
        )
    ).one()
    return (int(rows or 0), str(last_day))


def train(db: Session) -> ForecastBundle:
    """Fit the forecaster on seeded history. Deterministic given the seed."""
    frame = load_observations(db, seeded_only=True)
    static = load_port_static(db)
    table = build_training_table(frame, static)

    x = table[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    models: dict[str, HistGradientBoostingRegressor] = {}
    metrics: dict[str, float] = {}

    # Hold out the last 21 target-days as an honest sanity check for the README.
    cutoff = table["target_day"].max() - pd.Timedelta(days=21)
    is_train = (table["target_day"] <= cutoff).to_numpy()

    for target in ("congestion", "waiting"):
        y = table[f"y_{target}"].to_numpy(dtype=np.float32)
        median = _make_model("squared_error")
        median.fit(x, y)
        models[f"{target}_p50"] = median
        for q in QUANTILES:
            m = _make_model("quantile", q)
            m.fit(x, y)
            models[f"{target}_p{int(q * 100)}"] = m

        holdout = _make_model("squared_error")
        holdout.fit(x[is_train], y[is_train])
        pred = holdout.predict(x[~is_train])
        truth = y[~is_train]
        metrics[f"{target}_mae"] = float(np.mean(np.abs(pred - truth)))
        naive = table.loc[~is_train, "c_lag0" if target == "congestion" else "w_lag0"].to_numpy()
        metrics[f"{target}_mae_naive"] = float(np.mean(np.abs(naive - truth)))

    congestion_std = frame.groupby("port_id")["congestion"].std().to_dict()
    bundle = ForecastBundle(
        version=MODEL_VERSION,
        signature=training_signature(db),
        models=models,
        port_codes=_port_codes(static["port_id"].tolist()),
        feature_medians={c: float(table[c].median()) for c in FEATURE_COLUMNS},
        port_congestion_std={k: float(v) for k, v in congestion_std.items()},
        port_thresholds=dict(zip(static["port_id"], static["threshold"].astype(float))),
        trained_rows=int(len(table)),
        trained_through=frame["day"].max().date(),
        metrics=metrics,
    )
    return bundle


_BUNDLE: ForecastBundle | None = None
_BUNDLE_LOCK = threading.Lock()


def get_bundle(db: Session, force_retrain: bool = False) -> ForecastBundle:
    """Load the cached model from disk, training it once if needed."""
    global _BUNDLE
    if _BUNDLE is not None and not force_retrain:
        return _BUNDLE
    with _BUNDLE_LOCK:
        return _load_or_train(db, force_retrain)


def _load_or_train(db: Session, force_retrain: bool) -> ForecastBundle:
    global _BUNDLE
    if _BUNDLE is not None and not force_retrain:
        return _BUNDLE
    if MODEL_PATH.exists() and not force_retrain:
        try:
            bundle = joblib.load(MODEL_PATH)
            if (
                getattr(bundle, "version", None) == MODEL_VERSION
                and getattr(bundle, "signature", None) == training_signature(db)
            ):
                _BUNDLE = bundle
                return bundle
        except Exception:  # pragma: no cover - corrupt cache, just retrain
            pass
    bundle = train(db)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    _BUNDLE = bundle
    return bundle


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #


@dataclass
class ForecastPoint:
    port_id: str
    day: date
    horizon: int
    congestion: float
    congestion_low: float
    congestion_high: float
    waiting_days: float
    waiting_low: float
    waiting_high: float
    disruption_probability: float
    confidence: float
    expected_arrivals: float
    # Split of the headline number: statistical baseline vs declared events.
    congestion_baseline: float = 0.0
    event_uplift: float = 0.0
    event_drivers: list = field(default_factory=list)


@dataclass
class Contribution:
    feature: str
    label: str
    effect: float
    direction: str


@dataclass
class _Snapshot:
    """Everything derived from the observation table for one simulated day.

    Rebuilding this per request cost ~1.5s, which is far too slow for a live
    demo where a persona switch fires several calls at once. It only changes
    when the clock moves or the scenario fires, and ``data_version`` tracks
    exactly that, so it is cached process-wide.
    """

    frame: pd.DataFrame
    origin: pd.DataFrame
    static: pd.DataFrame
    arrival_profile: dict


_SNAPSHOTS: dict[tuple[date, int], _Snapshot] = {}
_SNAPSHOT_LIMIT = 4
_SNAPSHOT_LOCK = threading.Lock()

# Inference only needs enough history to fill the longest lag (27 days), the
# longest rolling window (28 days) and the 8-week arrival profile. Feeding it
# all 18 months made every request re-derive features it would throw away.
INFERENCE_WINDOW_DAYS = 70


class PortForecaster:
    """Bound to one snapshot of observations; caches per-port forecasts."""

    def __init__(
        self,
        db: Session,
        as_of: date,
        data_version: int = 0,
        overlay: "EventOverlay | None" = None,
    ):
        self.db = db
        self.as_of = as_of
        self.data_version = data_version
        self.overlay = overlay if overlay is not None else EventOverlay(db, as_of)
        self.bundle = get_bundle(db)
        snapshot = self._snapshot(db, as_of, data_version)
        self.frame = snapshot.frame
        self._origin = snapshot.origin
        self._static = snapshot.static
        self._arrival_profile = snapshot.arrival_profile
        # Full 1..MAX_HORIZON forecast per port; shorter horizons are slices.
        self._full: dict[str, list[ForecastPoint]] = {}

    @classmethod
    def _snapshot(cls, db: Session, as_of: date, data_version: int) -> _Snapshot:
        """Build (or reuse) the derived-feature snapshot for one simulated day.

        Serialised behind a lock: every demo action mints a new data_version and
        the UI immediately fires several requests at once. Without the lock they
        all miss the cache together and each rebuilds the same frame, which is
        how a 200 ms action turned into an eight-second stall.
        """
        key = (as_of, data_version)
        cached = _SNAPSHOTS.get(key)
        if cached is not None:
            return cached
        with _SNAPSHOT_LOCK:
            cached = _SNAPSHOTS.get(key)
            if cached is not None:
                return cached
            start = as_of - timedelta(days=INFERENCE_WINDOW_DAYS)
            frame = load_observations(db, since=start, until=as_of)
            origin = build_origin_features(frame)
            origin = origin[origin["day"] == pd.Timestamp(as_of)].set_index("port_id")
            snapshot = _Snapshot(
                frame=frame,
                origin=origin,
                static=load_port_static(db).set_index("port_id"),
                arrival_profile=cls._build_arrival_profile(frame),
            )
            while len(_SNAPSHOTS) >= _SNAPSHOT_LIMIT:
                _SNAPSHOTS.pop(next(iter(_SNAPSHOTS)))
            _SNAPSHOTS[key] = snapshot
            return snapshot

    # -- arrivals: seasonal-naive weekday profile, nudged by forecast congestion.
    @staticmethod
    def _build_arrival_profile(frame: pd.DataFrame) -> dict[tuple[str, int], float]:
        recent = frame[frame["day"] >= frame["day"].max() - pd.Timedelta(days=56)].copy()
        recent["weekday"] = recent["day"].dt.weekday
        grouped = recent.groupby(["port_id", "weekday"])["arrivals"].mean()
        return {(pid, int(wd)): float(v) for (pid, wd), v in grouped.items()}

    def _feature_matrix(self, port_id: str, horizons: list[int]) -> np.ndarray:
        if port_id not in self._origin.index:
            raise KeyError(f"no observations for port {port_id} as of {self.as_of}")
        origin_row = self._origin.loc[port_id]
        static = self._static.loc[port_id]
        rows = []
        for h in horizons:
            target_day = self.as_of + timedelta(days=h)
            doy = target_day.timetuple().tm_yday
            values = []
            for col in ORIGIN_FEATURES:
                v = origin_row.get(col)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    v = self.bundle.feature_medians[col]
                values.append(float(v))
            values.append(float(self.bundle.port_codes.get(port_id, 0)))
            values.append(float(static["base_congestion"]))
            values.append(float(static["capacity"]))
            values.append(float(h))
            values.append(math.sin(2 * math.pi * doy / 365.25))
            values.append(math.cos(2 * math.pi * doy / 365.25))
            values.append(float(target_day.weekday()))
            rows.append(values)
        return np.asarray(rows, dtype=np.float32)

    def _confidence(self, port_id: str, width: float, horizon: int) -> float:
        """0–1 score blending interval width, horizon and data recency."""
        std = max(self.bundle.port_congestion_std.get(port_id, 8.0), 1.0)
        sharpness = max(0.0, 1.0 - width / (3.2 * std))
        horizon_term = math.exp(-horizon / 34.0)
        gap = 0 if port_id in self._origin.index else 30
        recency = max(0.0, 1.0 - gap / 14.0)
        score = 0.55 * sharpness + 0.30 * horizon_term + 0.15 * recency
        return round(float(min(max(score, 0.05), 0.98)), 3)

    def prewarm(self, port_ids: list[str]) -> None:
        """Predict every requested port in one batch.

        Model inference is dominated by per-call overhead, not by arithmetic:
        28 ports × 21 horizons × 6 models issued one at a time is thousands of
        tiny predicts. Issuing six predicts over one tall matrix instead turns a
        one-second endpoint into a few tens of milliseconds.
        """
        wanted = [p for p in port_ids if p in self._origin.index and p not in self._full]
        if not wanted:
            return
        horizons = list(range(1, MAX_HORIZON_DAYS + 1))
        blocks = [self._feature_matrix(port_id, horizons) for port_id in wanted]
        x = np.concatenate(blocks, axis=0)
        m = self.bundle.models
        preds = {
            name: m[name].predict(x)
            for name in (
                "congestion_p50", "congestion_p10", "congestion_p90",
                "waiting_p50", "waiting_p10", "waiting_p90",
            )
        }
        span = len(horizons)
        for i, port_id in enumerate(wanted):
            sl = slice(i * span, (i + 1) * span)
            self._full[port_id] = self._assemble(
                port_id,
                horizons,
                {name: values[sl] for name, values in preds.items()},
            )

    def forecast(self, port_id: str, horizon: int = MAX_HORIZON_DAYS) -> list[ForecastPoint]:
        horizon = int(max(1, min(horizon, MAX_HORIZON_DAYS)))
        if port_id not in self._full:
            self.prewarm([port_id])
        cached = self._full.get(port_id)
        if cached is not None:
            return cached[:horizon]

        horizons = list(range(1, horizon + 1))
        x = self._feature_matrix(port_id, horizons)
        m = self.bundle.models
        return self._assemble(
            port_id,
            horizons,
            {
                "congestion_p50": m["congestion_p50"].predict(x),
                "congestion_p10": m["congestion_p10"].predict(x),
                "congestion_p90": m["congestion_p90"].predict(x),
                "waiting_p50": m["waiting_p50"].predict(x),
                "waiting_p10": m["waiting_p10"].predict(x),
                "waiting_p90": m["waiting_p90"].predict(x),
            },
        )

    def _assemble(
        self, port_id: str, horizons: list[int], preds: dict
    ) -> list[ForecastPoint]:
        """Turn raw model output into forecast points with intervals and overlay."""
        c50, c10, c90 = preds["congestion_p50"], preds["congestion_p10"], preds["congestion_p90"]
        w50, w10, w90 = preds["waiting_p50"], preds["waiting_p10"], preds["waiting_p90"]

        # Quantile models are fit independently; enforce ordering.
        c10, c90 = np.minimum(c10, c50), np.maximum(c90, c50)
        w10, w90 = np.minimum(w10, w50), np.maximum(w90, w50)

        threshold = self.bundle.port_thresholds.get(port_id, 70.0)
        base_level = float(self._static.loc[port_id]["base_congestion"])
        points: list[ForecastPoint] = []
        for i, h in enumerate(horizons):
            day = self.as_of + timedelta(days=h)

            baseline_c = float(c50[i])
            impact = self.overlay.congestion_uplift(port_id, day)
            uplift = impact.congestion
            c_mid = baseline_c + uplift
            w_uplift = self.overlay.waiting_uplift(baseline_c, port_id, day)
            w_mid = float(w50[i]) + w_uplift

            # An active event widens the band as well as raising the level:
            # nobody should claim precision about an unfolding disruption.
            widen = 1.0 + min(abs(uplift) / 30.0, 0.8)
            lo_c = c_mid - (baseline_c - float(c10[i])) * widen
            hi_c = c_mid + (float(c90[i]) - baseline_c) * widen
            lo_w = w_mid - (float(w50[i]) - float(w10[i])) * widen
            hi_w = w_mid + (float(w90[i]) - float(w50[i])) * widen

            width = float(hi_c - lo_c)
            sigma = max(width / Z80, 1.5)
            prob = 1.0 - _normal_cdf((threshold - c_mid) / sigma)

            base_arr = self._arrival_profile.get((port_id, day.weekday()), 4.0)
            congestion_lift = 1.0 + 0.12 * (c_mid - base_level) / 25.0
            points.append(
                ForecastPoint(
                    port_id=port_id,
                    day=day,
                    horizon=h,
                    congestion=round(min(max(c_mid, 2.0), 99.0), 2),
                    congestion_low=round(min(max(lo_c, 0.0), 99.0), 2),
                    congestion_high=round(min(max(hi_c, 2.0), 100.0), 2),
                    waiting_days=round(max(w_mid, 0.05), 3),
                    waiting_low=round(max(lo_w, 0.0), 3),
                    waiting_high=round(max(hi_w, 0.05), 3),
                    disruption_probability=round(float(min(max(prob, 0.0), 1.0)), 4),
                    confidence=self._confidence(port_id, width, h),
                    expected_arrivals=round(max(base_arr * congestion_lift, 0.0), 2),
                    congestion_baseline=round(baseline_c, 2),
                    event_uplift=round(uplift, 2),
                    event_drivers=[{"headline": hl, "points": pts} for hl, pts in impact.drivers],
                )
            )
        return points

    def point(self, port_id: str, day: date) -> ForecastPoint:
        """Forecast for a specific calendar day, clamped to the model horizon."""
        h = (day - self.as_of).days
        if h <= 0:
            h = 1
        capped = min(h, MAX_HORIZON_DAYS)
        pt = self.forecast(port_id, capped)[capped - 1]
        if h <= MAX_HORIZON_DAYS:
            return pt
        # Beyond the horizon we hold the level but widen the band, and say so.
        stretch = 1.0 + 0.05 * (h - MAX_HORIZON_DAYS)
        mid_c, mid_w = pt.congestion, pt.waiting_days
        return ForecastPoint(
            port_id=port_id,
            day=day,
            horizon=h,
            congestion=mid_c,
            congestion_low=round(mid_c - (mid_c - pt.congestion_low) * stretch, 2),
            congestion_high=round(mid_c + (pt.congestion_high - mid_c) * stretch, 2),
            waiting_days=mid_w,
            waiting_low=round(max(mid_w - (mid_w - pt.waiting_low) * stretch, 0.0), 3),
            waiting_high=round(mid_w + (pt.waiting_high - mid_w) * stretch, 3),
            disruption_probability=pt.disruption_probability,
            confidence=round(pt.confidence * max(0.35, 1.0 - 0.06 * (h - MAX_HORIZON_DAYS)), 3),
            expected_arrivals=pt.expected_arrivals,
            congestion_baseline=pt.congestion_baseline,
            event_uplift=pt.event_uplift,
            event_drivers=pt.event_drivers,
        )

    # -- honesty affordance: "How was this predicted?" -----------------------
    def explain(self, port_id: str, horizon: int, top_k: int = 4) -> list[Contribution]:
        """Local attribution by *group* ablation.

        Each semantic group of features is replaced by its training median and
        the prediction is re-run; the shift is that group's contribution in
        congestion-index points. Groups rather than raw columns because the lags
        are strongly correlated — ablating one at a time understates all of
        them and reads as noise to a human.
        """
        horizon = int(max(1, min(horizon, MAX_HORIZON_DAYS)))
        x = self._feature_matrix(port_id, [horizon])
        model = self.bundle.models["congestion_p50"]
        base = float(model.predict(x)[0])

        variants, names = [], []
        for group, columns in FEATURE_GROUPS.items():
            row = x[0].copy()
            for col in columns:
                row[FEATURE_COLUMNS.index(col)] = np.float32(self.bundle.feature_medians[col])
            variants.append(row)
            names.append(group)
        preds = model.predict(np.asarray(variants, dtype=np.float32))

        contributions = [
            Contribution(
                feature=name,
                label=GROUP_LABELS[name],
                effect=round(base - float(p), 2),
                direction="raises" if base - float(p) > 0 else "lowers",
            )
            for name, p in zip(names, preds)
        ]
        contributions.sort(key=lambda c: abs(c.effect), reverse=True)
        ranked = [c for c in contributions if abs(c.effect) >= 0.1][:top_k]

        # Declared events sit outside the statistical model, so they are listed
        # first and labelled as such rather than folded into a lag.
        day = self.as_of + timedelta(days=horizon)
        event_terms = [
            Contribution(
                feature="declared_event",
                label=f"Declared disruption: {headline}",
                effect=points,
                direction="raises" if points > 0 else "lowers",
            )
            for headline, points in self.overlay.congestion_uplift(port_id, day).drivers
        ]
        return event_terms + ranked


def clear_forecast_snapshots() -> None:
    """Drop cached observation snapshots (used after a reseed)."""
    _SNAPSHOTS.clear()


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def normal_tail_probability(mean: float, sigma: float, threshold: float) -> float:
    """P(X > threshold) for X ~ Normal(mean, sigma). Shared with the exposure engine."""
    sigma = max(sigma, 1e-6)
    return 1.0 - _normal_cdf((threshold - mean) / sigma)
