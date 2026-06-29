"""SQLAlchemy ORM models for the Lagoons Operating System.

All tables use UUIDs as primary keys.  Timestamps are stored in UTC.
Immutable tables (Observation, LOSEvent) have no update timestamp.
PostGIS geometry columns are declared via GeoAlchemy2.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# ─── Organisation ─────────────────────────────────────────────────────────────

class Organisation(Base):
    __tablename__ = "organisations"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_organisations_slug"),
        CheckConstraint("subscription_tier IN ('free','starter','professional','enterprise')",
                        name="ck_organisations_subscription_tier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    users: Mapped[list[User]] = relationship("User", back_populates="organisation", lazy="select")
    lagoons: Mapped[list[Lagoon]] = relationship("Lagoon", back_populates="organisation", lazy="select")

    def __repr__(self) -> str:
        return f"<Organisation id={self.id} name={self.name!r}>"


# ─── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('SUPERADMIN','ADMIN','ENGINEER','SCIENTIST','OPERATOR','VIEWER')",
            name="ck_users_role",
        ),
        Index("ix_users_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="users")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


# ─── Lagoon ───────────────────────────────────────────────────────────────────

class Lagoon(Base):
    __tablename__ = "lagoons"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_lagoons_org_slug"),
        Index("ix_lagoons_org_id", "org_id"),
        Index("ix_lagoons_geometry", "geometry", postgresql_using="gist"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    # GeoJSON-compatible dict with latitude/longitude centroid
    location: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # PostGIS polygon boundary
    geometry: Mapped[object | None] = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    surface_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    design_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    infrastructure_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    operating_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organisation: Mapped[Organisation] = relationship("Organisation", back_populates="lagoons")
    sensors: Mapped[list[Sensor]] = relationship("Sensor", back_populates="lagoon", lazy="select")
    observations: Mapped[list[Observation]] = relationship("Observation", back_populates="lagoon", lazy="select")
    recommendations: Mapped[list[Recommendation]] = relationship("Recommendation", back_populates="lagoon", lazy="select")
    operating_objectives: Mapped[list[OperatingObjective]] = relationship("OperatingObjective", back_populates="lagoon", lazy="select")

    def __repr__(self) -> str:
        return f"<Lagoon id={self.id} name={self.name!r}>"


# ─── Sensor ───────────────────────────────────────────────────────────────────

class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (
        Index("ix_sensors_lagoon_id", "lagoon_id"),
        Index("ix_sensors_location", "location", postgresql_using="gist"),
        CheckConstraint("status IN ('active','inactive','faulty','calibrating','decommissioned')",
                        name="ck_sensors_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    calibration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calibration_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    calibration_offset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    lagoon: Mapped[Lagoon] = relationship("Lagoon", back_populates="sensors")
    observations: Mapped[list[Observation]] = relationship("Observation", back_populates="sensor", lazy="select")

    def __repr__(self) -> str:
        return f"<Sensor id={self.id} type={self.sensor_type!r} lagoon={self.lagoon_id}>"


# ─── Observation (immutable) ──────────────────────────────────────────────────

class Observation(Base):
    """Immutable time-series data point.

    Once created, observations must never be modified.  Corrections are
    made by creating a new observation with quality_flag='corrected' and
    referencing the original in metadata.
    """

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_lagoon_ts", "lagoon_id", "timestamp"),
        Index("ix_observations_sensor_ts", "sensor_id", "timestamp"),
        Index("ix_observations_parameter", "lagoon_id", "parameter", "timestamp"),
        CheckConstraint("quality_flag IN ('good','suspect','bad','corrected','missing')",
                        name="ck_observations_quality_flag"),
        CheckConstraint("source IN ('sensor','manual','laboratory','model','estimated')",
                        name="ck_observations_source"),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_observations_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True)
    parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="sensor")
    quality_flag: Mapped[str] = mapped_column(String(20), nullable=False, default="good")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lagoon: Mapped[Lagoon] = relationship("Lagoon", back_populates="observations")
    sensor: Mapped[Sensor | None] = relationship("Sensor", back_populates="observations")

    def __repr__(self) -> str:
        return f"<Observation id={self.id} parameter={self.parameter!r} value={self.value}>"


# ─── LaboratoryResult ─────────────────────────────────────────────────────────

class LaboratoryResult(Base):
    __tablename__ = "laboratory_results"
    __table_args__ = (
        Index("ix_lab_results_lagoon_collected", "lagoon_id", "collected_at"),
        Index("ix_lab_results_location", "location", postgresql_using="gist"),
        CheckConstraint("sample_type IN ('water','sediment','soil','biota')",
                        name="ck_lab_results_sample_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    sample_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    quality_control: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    lab_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<LaboratoryResult id={self.id} sample_id={self.sample_id!r}>"


# ─── InfrastructureAsset ──────────────────────────────────────────────────────

class InfrastructureAsset(Base):
    __tablename__ = "infrastructure_assets"
    __table_args__ = (
        Index("ix_infrastructure_lagoon", "lagoon_id"),
        Index("ix_infrastructure_location", "location", postgresql_using="gist"),
        CheckConstraint(
            "asset_type IN ('aerator','pump','inlet','outlet','weir','sensor_array','diffuser','screen','valve','pipeline')",
            name="ck_infrastructure_asset_type",
        ),
        CheckConstraint("status IN ('operational','degraded','faulty','offline','maintenance')",
                        name="ck_infrastructure_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[object | None] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    specifications: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    commissioned_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="operational")
    last_maintenance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    maintenance_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<InfrastructureAsset id={self.id} type={self.asset_type!r} name={self.name!r}>"


# ─── LOSEvent (immutable) ─────────────────────────────────────────────────────

class LOSEvent(Base):
    """Immutable event record — the system's event ledger.

    Events are published to Redis Streams for real-time processing and
    simultaneously persisted here for audit and replay.
    """

    __tablename__ = "los_events"
    __table_args__ = (
        Index("ix_los_events_lagoon_created", "lagoon_id", "created_at"),
        Index("ix_los_events_correlation", "correlation_id"),
        Index("ix_los_events_loop", "loop"),
        Index("ix_los_events_event_type", "event_type"),
        CheckConstraint(
            "loop IN ('hydrological','chemical','ecological','infrastructure','decision','system')",
            name="ck_los_events_loop",
        ),
        CheckConstraint(
            "priority IN ('critical','high','normal','low')",
            name="ck_los_events_priority",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    loop: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<LOSEvent id={self.id} type={self.event_type!r} loop={self.loop!r}>"


# ─── OperatingObjective ───────────────────────────────────────────────────────

class OperatingObjective(Base):
    __tablename__ = "operating_objectives"
    __table_args__ = (
        Index("ix_operating_objectives_lagoon", "lagoon_id"),
        CheckConstraint("weight BETWEEN 0.0 AND 1.0", name="ck_objectives_weight"),
        CheckConstraint("priority BETWEEN 1 AND 10", name="ck_objectives_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    objective_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    lagoon: Mapped[Lagoon] = relationship("Lagoon", back_populates="operating_objectives")

    def __repr__(self) -> str:
        return f"<OperatingObjective id={self.id} name={self.name!r}>"


# ─── Recommendation ───────────────────────────────────────────────────────────

class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_lagoon_status", "lagoon_id", "status"),
        Index("ix_recommendations_created_at", "created_at"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','implemented','cancelled','superseded')",
            name="ck_recommendations_status",
        ),
        CheckConstraint(
            "action_category IN ('aeration','chemical_dosing','water_management','maintenance','investigation','monitoring','dredging','other')",
            name="ck_recommendations_category",
        ),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_recommendations_confidence"),
        CheckConstraint("priority IN ('critical','high','normal','low')", name="ck_recommendations_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    action_category: Mapped[str] = mapped_column(String(100), nullable=False)
    scientific_reason: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_loops: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    expected_timeframe_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alternative_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    operating_objective_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_by_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    lagoon: Mapped[Lagoon] = relationship("Lagoon", back_populates="recommendations")
    interventions: Mapped[list[Intervention]] = relationship("Intervention", back_populates="recommendation", lazy="select")

    def __repr__(self) -> str:
        return f"<Recommendation id={self.id} action={self.action[:50]!r} status={self.status!r}>"


# ─── Intervention ─────────────────────────────────────────────────────────────

class Intervention(Base):
    __tablename__ = "interventions"
    __table_args__ = (
        Index("ix_interventions_lagoon", "lagoon_id"),
        Index("ix_interventions_recommendation", "recommendation_id"),
        CheckConstraint(
            "status IN ('planned','in_progress','completed','failed','cancelled')",
            name="ck_interventions_status",
        ),
        CheckConstraint("outcome_confidence BETWEEN 0.0 AND 1.0", name="ck_interventions_outcome_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    implemented_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    recommendation: Mapped[Recommendation | None] = relationship("Recommendation", back_populates="interventions")

    def __repr__(self) -> str:
        return f"<Intervention id={self.id} status={self.status!r}>"


# ─── ScientificModelRun ───────────────────────────────────────────────────────

class ScientificModelRun(Base):
    __tablename__ = "scientific_model_runs"
    __table_args__ = (
        Index("ix_model_runs_lagoon_created", "lagoon_id", "created_at"),
        Index("ix_model_runs_model_name", "model_name"),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_model_runs_status",
        ),
        CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_model_runs_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    input_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    assumptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    limitations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    execution_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<ScientificModelRun id={self.id} model={self.model_name!r} status={self.status!r}>"


# ─── SharedMemoryEntry ────────────────────────────────────────────────────────

class SharedMemoryEntry(Base):
    """Persistent shared memory — slower than Redis but survives restarts."""

    __tablename__ = "shared_memory_entries"
    __table_args__ = (
        UniqueConstraint("lagoon_id", "memory_type", "loop", "key", name="uq_shared_memory_key"),
        Index("ix_shared_memory_lagoon_type", "lagoon_id", "memory_type"),
        Index("ix_shared_memory_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lagoon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    loop: Mapped[str | None] = mapped_column(String(50), nullable=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<SharedMemoryEntry lagoon={self.lagoon_id} type={self.memory_type!r} key={self.key!r}>"


# ─── AuditLog (immutable) ─────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_user_timestamp", "user_id", "timestamp"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
        Index("ix_audit_log_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} user={self.user_id}>"
