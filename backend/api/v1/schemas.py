"""Pydantic request/response schemas for the LOS API.

All user-facing validation and serialisation lives here.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

# ── Common ───────────────────────────────────────────────────────────────────

class PaginationMeta(BaseModel):
    skip: int
    limit: int
    total: int | None = None


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


# ── Auth ─────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    role: str
    org_id: UUID | None = None
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None

    model_config = {"from_attributes": True}


# ── Organisation ─────────────────────────────────────────────────────────────

class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    country: str = Field(min_length=2, max_length=100)


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    country: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lagoon ───────────────────────────────────────────────────────────────────

class LagoonCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    surface_area_m2: float = Field(gt=0.0, le=1_000_000_000.0)
    volume_m3: float = Field(gt=0.0, le=100_000_000_000.0)
    max_depth_m: float | None = Field(default=None, gt=0.0, le=500.0)
    mean_depth_m: float | None = Field(default=None, gt=0.0, le=500.0)
    catchment_area_m2: float | None = Field(default=None, gt=0.0)
    operational_mode: str = Field(default="normal", pattern="^(normal|monitoring|maintenance|emergency)$")
    timezone: str = Field(default="UTC", max_length=50)
    salinity_type: str = Field(
        default="brackish",
        pattern="^(freshwater|brackish|marine|hypersaline)$",
    )
    metadata: dict[str, Any] | None = None


class LagoonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    surface_area_m2: float | None = Field(default=None, gt=0.0)
    volume_m3: float | None = Field(default=None, gt=0.0)
    max_depth_m: float | None = Field(default=None, gt=0.0)
    mean_depth_m: float | None = Field(default=None, gt=0.0)
    operational_mode: str | None = Field(
        default=None, pattern="^(normal|monitoring|maintenance|emergency)$"
    )
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class LagoonResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    latitude: float
    longitude: float
    surface_area_m2: float
    volume_m3: float
    max_depth_m: float | None = None
    mean_depth_m: float | None = None
    operational_mode: str
    timezone: str
    salinity_type: str
    is_active: bool
    org_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class OperatingObjectiveCreate(BaseModel):
    parameter: str = Field(min_length=1, max_length=100)
    target: float
    tolerance: float = Field(ge=0.0)
    objective_type: str = Field(
        default="water_quality",
        pattern="^(water_quality|ecological|infrastructure|compliance|operational)$",
    )
    priority: int = Field(default=5, ge=1, le=10)
    description: str | None = Field(default=None, max_length=500)


class OperatingObjectiveResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    parameter: str
    target: float
    tolerance: float
    objective_type: str
    priority: int
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LagoonStatusResponse(BaseModel):
    lagoon_id: UUID
    lagoon_name: str | None = None
    timestamp: datetime
    loop_states: dict[str, Any]
    confidence_scores: dict[str, float]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    recent_events: list[dict[str, Any]]
    objectives: list[dict[str, Any]]
    operational_mode: str
    alert_level: str = Field(pattern="^(normal|advisory|warning|critical)$")


# ── Sensor ───────────────────────────────────────────────────────────────────

class SensorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sensor_type: str = Field(min_length=1, max_length=100)
    parameter: str = Field(min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=200)
    model_number: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    location_description: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    depth_m: float | None = Field(default=None, ge=0.0, le=100.0)
    sampling_interval_s: int = Field(default=900, ge=1, le=86400)
    unit: str = Field(min_length=1, max_length=50)
    detection_limit: float | None = None
    accuracy: float | None = Field(default=None, ge=0.0)


class SensorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    location_description: str | None = Field(default=None, max_length=500)
    sampling_interval_s: int | None = Field(default=None, ge=1, le=86400)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class SensorCalibrationCreate(BaseModel):
    calibration_date: datetime
    calibrated_by: str = Field(min_length=2, max_length=200)
    reference_standard: str | None = Field(default=None, max_length=200)
    offset: float = Field(default=0.0)
    gain: float = Field(default=1.0, gt=0.0)
    notes: str | None = Field(default=None, max_length=1000)
    next_calibration_due: datetime | None = None


class SensorResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    name: str
    sensor_type: str
    parameter: str
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    location_description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    depth_m: float | None = None
    sampling_interval_s: int
    unit: str
    detection_limit: float | None = None
    accuracy: float | None = None
    is_active: bool
    last_reading_at: datetime | None = None
    last_calibration_at: datetime | None = None
    created_at: datetime
    metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


# ── Observation ───────────────────────────────────────────────────────────────

class ObservationCreate(BaseModel):
    parameter: str = Field(min_length=1, max_length=100)
    value: float
    unit: str | None = Field(default=None, max_length=50)
    timestamp: datetime
    sensor_id: UUID | None = None
    depth_m: float | None = Field(default=None, ge=0.0, le=100.0)
    quality_flag: str = Field(
        default="good",
        pattern="^(good|suspect|bad|missing|estimated)$",
    )
    source: str = Field(default="manual", max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class BulkObservationCreate(BaseModel):
    observations: list[ObservationCreate] = Field(min_length=1, max_length=10000)

    @field_validator("observations")
    @classmethod
    def no_duplicate_timestamps(cls, obs: list[ObservationCreate]) -> list[ObservationCreate]:
        seen = set()
        for o in obs:
            key = (o.parameter, o.timestamp.isoformat())
            if key in seen:
                raise ValueError(f"Duplicate observation for {o.parameter} at {o.timestamp}")
            seen.add(key)
        return obs


class ObservationResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    parameter: str
    value: float
    unit: str | None = None
    timestamp: datetime
    sensor_id: UUID | None = None
    depth_m: float | None = None
    quality_flag: str
    source: str
    submitted_by: UUID | None = None
    ingested_at: datetime
    notes: str | None = None

    model_config = {"from_attributes": True}


class BulkIngestResponse(BaseModel):
    accepted: int
    rejected: int
    rejected_details: list[dict[str, Any]] = Field(default_factory=list)


class LatestReadingsResponse(BaseModel):
    lagoon_id: UUID
    timestamp: datetime
    readings: dict[str, Any]


class TimeSeriesResponse(BaseModel):
    lagoon_id: UUID
    parameter: str
    start: datetime
    end: datetime
    count: int
    data: list[dict[str, Any]]


class StatisticsResponse(BaseModel):
    lagoon_id: UUID
    parameter: str
    period_days: int
    count: int
    statistics: dict[str, float] | None = None


# ── Event ─────────────────────────────────────────────────────────────────────

class EventResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    event_type: str
    severity: str
    payload: dict[str, Any]
    source_loop: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None

    model_config = {"from_attributes": True}


# ── Recommendation ────────────────────────────────────────────────────────────

class RecommendationApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class RecommendationRejectRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class RecommendationResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    title: str
    description: str
    rationale: str | None = None
    intervention_type: str
    priority: int
    estimated_impact: dict[str, Any] | None = None
    status: str
    created_by_loop: str | None = None
    reviewed_by: UUID | None = None
    review_notes: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DecisionCycleResponse(BaseModel):
    lagoon_id: UUID
    status: str
    message: str
    triggered_at: datetime


# ── Intervention ──────────────────────────────────────────────────────────────

class InterventionCreate(BaseModel):
    intervention_type: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=2000)
    scheduled_date: datetime | None = None
    executed_by: str | None = Field(default=None, max_length=200)
    cost_estimate: float | None = Field(default=None, ge=0.0)
    recommendation_id: UUID | None = None
    parameters_targeted: list[str] = Field(default_factory=list)
    expected_outcome: str | None = Field(default=None, max_length=1000)


class InterventionUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=5, max_length=2000)
    status: str | None = Field(
        default=None,
        pattern="^(planned|in_progress|completed|cancelled|deferred)$",
    )
    executed_at: datetime | None = None
    outcome_description: str | None = Field(default=None, max_length=2000)
    actual_cost: float | None = Field(default=None, ge=0.0)
    effectiveness_score: float | None = Field(default=None, ge=0.0, le=1.0)


class InterventionResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    intervention_type: str
    description: str
    status: str
    scheduled_date: datetime | None = None
    executed_at: datetime | None = None
    executed_by: str | None = None
    cost_estimate: float | None = None
    actual_cost: float | None = None
    effectiveness_score: float | None = None
    recommendation_id: UUID | None = None
    outcome_description: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Simulation ────────────────────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    simulation_type: str = Field(
        pattern="^(hydrological|chemical|ecological|combined|modflow|phreeqc|hydrus)$"
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    start_date: datetime
    end_date: datetime
    scenario_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def end_after_start(self) -> SimulationRequest:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class SimulationResponse(BaseModel):
    id: UUID
    lagoon_id: UUID
    simulation_type: str
    status: str = Field(pattern="^(queued|running|completed|failed|cancelled)$")
    scenario_name: str | None = None
    description: str | None = None
    start_date: datetime
    end_date: datetime
    submitted_by: UUID
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None
    task_id: str | None = None

    model_config = {"from_attributes": True}


# ── Report ────────────────────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    report_type: str = Field(
        pattern="^(executive|scientific|compliance|operational)$"
    )
    period_days: int = Field(default=30, ge=1, le=365)
    format: str = Field(default="markdown", pattern="^(markdown|html|pdf)$")


class ReportResponse(BaseModel):
    id: UUID | None = None
    lagoon_id: UUID
    report_type: str
    period_days: int
    format: str
    content: str
    generated_at: datetime
    generated_by: UUID | None = None


# ── User Management ───────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    full_name: str = Field(min_length=2, max_length=200)
    role: str = Field(pattern="^(admin|manager|operator|scientist|viewer)$")
    org_id: UUID | None = None
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: str | None = Field(
        default=None, pattern="^(admin|manager|operator|scientist|viewer)$"
    )
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# ── Admin / System ────────────────────────────────────────────────────────────

class LoopStatusResponse(BaseModel):
    loop_name: str
    service_name: str
    status: str
    last_run: datetime | None = None
    run_count: int
    error_count: int
    confidence: float | None = None


class SystemHealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    database: str
    redis: str
    neo4j: str
    worker_queue_depth: int | None = None
    active_loops: int
    loop_statuses: list[LoopStatusResponse]
    uptime_seconds: float | None = None


class WorkerStatusResponse(BaseModel):
    worker_id: str
    hostname: str
    status: str
    active_tasks: list[dict[str, Any]]
    queue: str
    heartbeat_at: datetime | None = None


# ── Pagination wrappers ───────────────────────────────────────────────────────

class PaginatedLagoons(BaseModel):
    items: list[LagoonResponse]
    meta: PaginationMeta


class PaginatedSensors(BaseModel):
    items: list[SensorResponse]
    meta: PaginationMeta


class PaginatedObservations(BaseModel):
    items: list[ObservationResponse]
    meta: PaginationMeta


class PaginatedEvents(BaseModel):
    items: list[EventResponse]
    meta: PaginationMeta


class PaginatedRecommendations(BaseModel):
    items: list[RecommendationResponse]
    meta: PaginationMeta


class PaginatedInterventions(BaseModel):
    items: list[InterventionResponse]
    meta: PaginationMeta


class PaginatedSimulations(BaseModel):
    items: list[SimulationResponse]
    meta: PaginationMeta


class PaginatedUsers(BaseModel):
    items: list[UserResponse]
    meta: PaginationMeta
