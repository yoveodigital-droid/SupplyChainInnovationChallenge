"""Pydantic v2 response models — the public API contract."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

Model = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #


class PortOut(BaseModel):
    model_config = Model

    id: str
    name: str
    short_name: str
    country: str
    region: str
    lat: float
    lon: float
    capacity_teu_per_day: int
    base_congestion: float
    base_waiting_days: float
    demurrage_usd_per_teu_day: float
    free_days: int
    is_hub: bool
    congestion_threshold: float
    blurb: str


class PortStatusOut(PortOut):
    """Port plus where it stands today and where it is heading."""

    congestion_now: float
    waiting_now: float
    weather_now: float
    congestion_7d: float
    disruption_probability_7d: float
    confidence_7d: float
    risk_level: str


class ChokepointOut(BaseModel):
    model_config = Model

    id: str
    name: str
    lat: float
    lon: float
    base_risk: float
    current_risk: float
    delay_days_at_max_risk: float
    note: str
    risk_level: str = "green"


class LegOut(BaseModel):
    model_config = Model

    id: str
    origin_id: str
    dest_id: str
    mode: str
    service: str
    distance_nm: float
    transit_days: float
    cost_per_teu: float
    co2_tonnes_per_teu: float
    sailings_per_week: float
    chokepoints: list[str]


class PersonaOut(BaseModel):
    model_config = Model

    id: str
    name: str
    role: str
    org: str
    location: str
    view: str
    home_port_id: str | None
    language: str
    avatar: str
    blurb: str
    shipment_count: int = 0


class EventOut(BaseModel):
    model_config = Model

    id: str
    day: date
    type: str
    severity: int
    headline: str
    detail: str
    port_id: str | None
    chokepoint_id: str | None
    lat: float
    lon: float
    source: str
    scenario: bool


# --------------------------------------------------------------------------- #
# Forecasting
# --------------------------------------------------------------------------- #


class ObservationOut(BaseModel):
    day: date
    congestion_index: float
    waiting_days: float
    weather_severity: float
    vessel_arrivals: int


class EventDriverOut(BaseModel):
    headline: str
    points: float


class ForecastPointOut(BaseModel):
    model_config = Model

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
    congestion_baseline: float
    event_uplift: float
    event_drivers: list[EventDriverOut] = Field(default_factory=list)


class ContributionOut(BaseModel):
    model_config = Model

    feature: str
    label: str
    effect: float
    direction: str


class ForecastOut(BaseModel):
    port_id: str
    port_name: str
    as_of: date
    horizon_days: int
    congestion_threshold: float
    points: list[ForecastPointOut]
    explanation: list[ContributionOut]
    model_note: str


class PortPressureOut(BaseModel):
    """Everything the port-authority view needs in one call."""

    port: PortStatusOut
    as_of: date
    history: list[ObservationOut]
    forecast: list[ForecastPointOut]
    explanation: list[ContributionOut]
    upstream_events: list[EventOut]
    inbound_shipments: int
    summary: str
    peak_day: date | None
    peak_congestion: float


# --------------------------------------------------------------------------- #
# Shipments and exposure
# --------------------------------------------------------------------------- #


class ShipmentOut(BaseModel):
    model_config = Model

    id: str
    persona_id: str
    reference: str
    origin_id: str
    dest_id: str
    origin_name: str
    dest_name: str
    leg_ids: list[str]
    etd: date
    required_by: date
    cargo: str
    cargo_short: str
    teu: float
    perishable: bool
    shelf_life_days: int | None
    value_usd: float
    status: str
    buyer: str
    applied_option: str | None
    rerouted: bool
    risk_level: str
    risk_score: float
    expected_delay_days: float
    spoilage_probability: float | None


class CallOut(BaseModel):
    model_config = Model

    port_id: str
    port_name: str
    port_short_name: str
    day: date
    role: str
    service: str
    forecast_congestion: float
    forecast_waiting: float
    normal_waiting: float
    delay_days: float
    disruption_probability: float
    confidence: float
    risk_level: str


class LegExposureOut(BaseModel):
    model_config = Model

    leg_id: str
    origin_id: str
    dest_id: str
    mode: str
    service: str
    depart: date
    arrive: date
    transit_days: float
    chokepoints: list[str]
    chokepoint_risk: float
    chokepoint_delay_days: float
    connection_delay_days: float
    risk_level: str


class DelayBin(BaseModel):
    days: int
    probability: float
    plus: bool = False


class DriverOut(BaseModel):
    kind: str
    label: str
    days: float


class ExposureOut(BaseModel):
    model_config = Model

    shipment_id: str
    etd: date
    required_by: date
    scheduled_transit_days: float
    scheduled_arrival: date
    expected_delay_days: float
    delay_p10: float
    delay_p90: float
    expected_arrival: date
    prob_delay_over_3: float
    prob_delay_over_7: float
    prob_miss_deadline: float
    demurrage_usd: float
    demurrage_days: float
    spoilage_probability: float | None
    spoilage_band: str | None
    expected_spoilage_loss_usd: float
    risk_score: float
    risk_level: str
    confidence: float
    calls: list[CallOut]
    legs: list[LegExposureOut]
    drivers: list[DriverOut]
    delay_distribution: list[DelayBin]


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #


class CostBreakdownOut(BaseModel):
    model_config = Model

    freight_usd: float
    demurrage_usd: float
    spoilage_loss_usd: float
    late_penalty_usd: float
    holding_usd: float
    carbon_usd: float
    total_usd: float


class OptionOut(BaseModel):
    model_config = Model

    id: str
    kind: str
    label: str
    summary: str
    rationale: str
    leg_ids: list[str]
    route_ports: list[str]
    route_port_names: list[str]
    via: list[str]
    etd: date
    departure_delay_days: int
    scheduled_transit_days: float
    scheduled_arrival: date
    expected_arrival: date
    required_by: date
    days_late: float
    delta_cost_usd: float
    delta_transit_days: float
    delta_risk_days: float
    delta_co2_tonnes: float
    freight_usd: float
    co2_tonnes: float
    expected_delay_days: float
    prob_delay_over_3: float
    prob_delay_over_7: float
    prob_miss_deadline: float
    demurrage_usd: float
    spoilage_probability: float | None
    spoilage_band: str | None
    risk_level: str
    confidence: float
    costs: CostBreakdownOut
    savings_usd: float
    score: float
    rank: int
    recommended: bool
    dominated_by: str | None
    caveats: list[str]


class RecommendationsOut(BaseModel):
    shipment_id: str
    as_of: date
    options: list[OptionOut]
    objective: str
    assumptions: dict[str, float | str]


# --------------------------------------------------------------------------- #
# Alerts and feedback
# --------------------------------------------------------------------------- #


class ChipOut(BaseModel):
    key: str
    label: str
    tone: str


class ChatMessageOut(BaseModel):
    model_config = Model

    id: str
    sender: str
    kind: str
    text: str
    chips: list[ChipOut] = Field(default_factory=list)
    option_id: str | None = None
    recommended: bool = False


class AlertOut(BaseModel):
    model_config = Model

    shipment_id: str
    language: str
    risk_level: str
    alert_text: str
    alert_chars: int
    within_limit: bool
    messages: list[ChatMessageOut]
    quick_replies: list[str]


class FeedbackIn(BaseModel):
    shipment_id: str
    helpful: bool
    note: str = ""


class FeedbackOut(BaseModel):
    model_config = Model

    id: int
    shipment_id: str
    helpful: bool
    note: str
    sim_date: date | None


# --------------------------------------------------------------------------- #
# Demo control and metadata
# --------------------------------------------------------------------------- #


class DemoStateOut(BaseModel):
    model_config = Model

    sim_date: date
    seed_date: date
    days_advanced: int
    scenario_active: bool
    scenario_day: int
    scenario_start: date | None
    data_version: int
    can_advance: bool


class AcceptIn(BaseModel):
    option_id: str


class AcceptOut(BaseModel):
    shipment: ShipmentOut
    message: ChatMessageOut
    exposure: ExposureOut


class MetaOut(BaseModel):
    name: str
    tagline: str
    disclaimer: str
    languages: list[str]
    risk_thresholds: dict[str, float]
    max_horizon_days: int
    model: dict[str, float | int | str]
    demo: DemoStateOut
