"""SQLAlchemy ORM models — the PortPulse domain.

Swap seam: every table here is populated by ``app/seed.py`` today. A production
team replaces the *writers* (seed / ingestion jobs) and keeps the readers
(``app/services/*``) untouched.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Port(Base):
    __tablename__ = "ports"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # UN/LOCODE
    name: Mapped[str] = mapped_column(String(64))
    short_name: Mapped[str] = mapped_column(String(32), default="")
    country: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    capacity_teu_per_day: Mapped[int] = mapped_column(Integer)
    base_congestion: Mapped[float] = mapped_column(Float)
    base_waiting_days: Mapped[float] = mapped_column(Float)
    demurrage_usd_per_teu_day: Mapped[float] = mapped_column(Float)
    free_days: Mapped[int] = mapped_column(Integer, default=4)
    is_hub: Mapped[bool] = mapped_column(Boolean, default=False)
    # Port-specific congestion level above which operations are "disrupted".
    congestion_threshold: Mapped[float] = mapped_column(Float)
    monsoon_phase: Mapped[float] = mapped_column(Float, default=0.0)
    blurb: Mapped[str] = mapped_column(String(240), default="")

    daily: Mapped[list["PortDaily"]] = relationship(back_populates="port")


class Chokepoint(Base):
    """Maritime chokepoints. Legs reference these; events raise their risk."""

    __tablename__ = "chokepoints"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    base_risk: Mapped[float] = mapped_column(Float, default=0.05)
    current_risk: Mapped[float] = mapped_column(Float, default=0.05)
    # Extra transit days (mean) imposed on a leg when risk is at 1.0.
    delay_days_at_max_risk: Mapped[float] = mapped_column(Float, default=3.0)
    note: Mapped[str] = mapped_column(String(240), default="")


class Leg(Base):
    """A directed port-to-port service leg (sea or land)."""

    __tablename__ = "legs"
    __table_args__ = (UniqueConstraint("origin_id", "dest_id", "mode", name="uq_leg"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    origin_id: Mapped[str] = mapped_column(ForeignKey("ports.id"))
    dest_id: Mapped[str] = mapped_column(ForeignKey("ports.id"))
    mode: Mapped[str] = mapped_column(String(8), default="sea")  # sea | land
    service: Mapped[str] = mapped_column(String(16), default="mainline")  # mainline | feeder | truck
    distance_nm: Mapped[float] = mapped_column(Float)
    transit_days: Mapped[float] = mapped_column(Float)
    cost_per_teu: Mapped[float] = mapped_column(Float)
    co2_tonnes_per_teu: Mapped[float] = mapped_column(Float)
    sailings_per_week: Mapped[float] = mapped_column(Float, default=2.0)
    chokepoints: Mapped[list] = mapped_column(JSON, default=list)

    origin: Mapped[Port] = relationship(foreign_keys=[origin_id])
    dest: Mapped[Port] = relationship(foreign_keys=[dest_id])


class PortDaily(Base):
    """Daily observed operating conditions per port (the forecaster's training set)."""

    __tablename__ = "port_daily"
    __table_args__ = (UniqueConstraint("port_id", "day", name="uq_port_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    port_id: Mapped[str] = mapped_column(ForeignKey("ports.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    congestion_index: Mapped[float] = mapped_column(Float)
    waiting_days: Mapped[float] = mapped_column(Float)
    weather_severity: Mapped[float] = mapped_column(Float)
    vessel_arrivals: Mapped[int] = mapped_column(Integer)
    # True for rows written by the live scenario controller rather than the seed.
    scenario: Mapped[bool] = mapped_column(Boolean, default=False)

    port: Mapped[Port] = relationship(back_populates="daily")


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(64))
    org: Mapped[str] = mapped_column(String(96))
    location: Mapped[str] = mapped_column(String(64))
    view: Mapped[str] = mapped_column(String(24))  # phone | dashboard | port
    home_port_id: Mapped[str | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    avatar: Mapped[str] = mapped_column(String(8), default="🙂")
    blurb: Mapped[str] = mapped_column(String(240), default="")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    reference: Mapped[str] = mapped_column(String(32))
    origin_id: Mapped[str] = mapped_column(ForeignKey("ports.id"))
    dest_id: Mapped[str] = mapped_column(ForeignKey("ports.id"))
    leg_ids: Mapped[list] = mapped_column(JSON, default=list)
    etd: Mapped[date] = mapped_column(Date)
    # Latest arrival the buyer will accept without a late-delivery penalty.
    required_by: Mapped[date] = mapped_column(Date)
    cargo: Mapped[str] = mapped_column(String(48))
    cargo_short: Mapped[str] = mapped_column(String(32), default="")
    teu: Mapped[float] = mapped_column(Float)
    perishable: Mapped[bool] = mapped_column(Boolean, default=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="booked")
    buyer: Mapped[str] = mapped_column(String(96), default="")
    # Set when a persona accepts a recommendation during the demo.
    original_leg_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    original_etd: Mapped[date | None] = mapped_column(Date, nullable=True)
    applied_option: Mapped[str | None] = mapped_column(String(48), nullable=True)


class Event(Base):
    """Disruption / news feed item."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(24))  # security | weather | labor | congestion | policy
    severity: Mapped[int] = mapped_column(Integer)  # 1..5
    headline: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(String(400), default="")
    port_id: Mapped[str | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    chokepoint_id: Mapped[str | None] = mapped_column(ForeignKey("chokepoints.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(48), default="PortPulse synthetic feed")
    scenario: Mapped[bool] = mapped_column(Boolean, default=False)


class DemoState(Base):
    """Single-row table holding the simulated clock."""

    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sim_date: Mapped[date] = mapped_column(Date)
    scenario_active: Mapped[bool] = mapped_column(Boolean, default=False)
    scenario_day: Mapped[int] = mapped_column(Integer, default=0)
    scenario_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Bumped whenever observations change, so forecast caches invalidate.
    data_version: Mapped[int] = mapped_column(Integer, default=1)


class Feedback(Base):
    """Thumbs up/down on an alert — the trust feedback loop."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[str] = mapped_column(String(24))
    helpful: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sim_date: Mapped[date | None] = mapped_column(Date, nullable=True)
