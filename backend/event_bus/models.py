"""Pydantic models for all LOS event types.

Events flow through Redis Streams and are persisted in the los_events table.
Every event carries a lagoon_id so that consumers can filter by lagoon.
"""

from __future__ import annotations

import enum
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# ─── Enumerations ─────────────────────────────────────────────────────────────

class ScientificLoop(enum.StrEnum):
    """The scientific loop that produced or consumes this event."""

    HYDROLOGICAL = "hydrological"
    CHEMICAL = "chemical"
    ECOLOGICAL = "ecological"
    INFRASTRUCTURE = "infrastructure"
    DECISION = "decision"
    SYSTEM = "system"


class EventPriority(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class EventType(enum.StrEnum):
    # Observation events
    OBSERVATION_RECEIVED = "observation.received"
    OBSERVATION_ANOMALY = "observation.anomaly"
    OBSERVATION_MISSING = "observation.missing"

    # Hydrological loop
    WATER_LEVEL_CHANGE = "hydrological.water_level_change"
    RESIDENCE_TIME_UPDATED = "hydrological.residence_time_updated"
    FLOW_RATE_ANOMALY = "hydrological.flow_rate_anomaly"
    GROUNDWATER_INTRUSION = "hydrological.groundwater_intrusion"
    WATER_BALANCE_CALCULATED = "hydrological.water_balance_calculated"

    # Chemical loop
    DO_CRITICAL_LOW = "chemical.do_critical_low"
    DO_HYPOXIC = "chemical.do_hypoxic"
    NUTRIENT_THRESHOLD_EXCEEDED = "chemical.nutrient_threshold_exceeded"
    PH_OUT_OF_RANGE = "chemical.ph_out_of_range"
    ORP_ANAEROBIC = "chemical.orp_anaerobic"
    AMMONIA_TOXIC = "chemical.ammonia_toxic"
    SULFIDE_DETECTED = "chemical.sulfide_detected"
    CHEMICAL_STATE_UPDATED = "chemical.state_updated"

    # Ecological loop
    ALGAL_BLOOM_RISK = "ecological.algal_bloom_risk"
    ALGAL_BLOOM_DETECTED = "ecological.algal_bloom_detected"
    CYANOBACTERIA_DETECTED = "ecological.cyanobacteria_detected"
    SLUDGE_ACCUMULATION_HIGH = "ecological.sludge_accumulation_high"
    ODOUR_RISK = "ecological.odour_risk"
    ECOLOGICAL_STATE_UPDATED = "ecological.state_updated"

    # Infrastructure loop
    AERATOR_FAULT = "infrastructure.aerator_fault"
    PUMP_FAULT = "infrastructure.pump_fault"
    MAINTENANCE_DUE = "infrastructure.maintenance_due"
    POWER_ANOMALY = "infrastructure.power_anomaly"
    INFRASTRUCTURE_STATE_UPDATED = "infrastructure.state_updated"

    # Decision events
    RECOMMENDATION_GENERATED = "decision.recommendation_generated"
    RECOMMENDATION_APPROVED = "decision.recommendation_approved"
    RECOMMENDATION_REJECTED = "decision.recommendation_rejected"
    INTERVENTION_STARTED = "decision.intervention_started"
    INTERVENTION_COMPLETED = "decision.intervention_completed"

    # Learning events
    LEARNING_CYCLE_STARTED = "learning.cycle_started"
    LEARNING_CYCLE_COMPLETED = "learning.cycle_completed"
    CONFIDENCE_UPDATED = "learning.confidence_updated"
    MODEL_CALIBRATED = "learning.model_calibrated"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    HEALTH_CHECK = "system.health_check"
    LOOP_STARTED = "system.loop_started"
    LOOP_COMPLETED = "system.loop_completed"
    LOOP_ERROR = "system.loop_error"


# ─── Base event model ─────────────────────────────────────────────────────────

class LOSEvent(BaseModel):
    """Base event published to Redis Streams and persisted in los_events.

    Immutable after creation.  All specialised event types inherit this class.
    The model is intentionally NOT frozen so that subclasses can set defaults.
    """

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    lagoon_id: UUID
    loop: ScientificLoop
    source: str = Field(min_length=1, max_length=255)
    priority: EventPriority = EventPriority.NORMAL
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)
    version: str = "1.0"
    event_type: str

    model_config = {"use_enum_values": False}

    def to_redis_payload(self) -> dict[str, str]:
        """Serialise to flat string dict for Redis XADD."""
        priority_val = self.priority.value if isinstance(self.priority, EventPriority) else str(self.priority)
        loop_val = self.loop.value if isinstance(self.loop, ScientificLoop) else str(self.loop)
        event_type_val = self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type)
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat(),
            "lagoon_id": str(self.lagoon_id),
            "loop": loop_val,
            "source": self.source,
            "priority": priority_val,
            "confidence": str(self.confidence),
            "payload": json.dumps(self.payload),
            "correlation_id": str(self.correlation_id),
            "version": self.version,
            "event_type": event_type_val,
        }

    @classmethod
    def from_redis_payload(cls, data: dict[str, str | bytes]) -> LOSEvent:
        """Deserialise from Redis XREAD output."""

        def _s(v: str | bytes | None) -> str:
            if v is None:
                return ""
            return v.decode() if isinstance(v, bytes) else v

        return cls(
            event_id=UUID(_s(data.get("event_id", str(uuid4())))),
            timestamp=datetime.fromisoformat(_s(data["timestamp"])),
            lagoon_id=UUID(_s(data["lagoon_id"])),
            loop=ScientificLoop(_s(data["loop"])),
            source=_s(data["source"]),
            priority=EventPriority(_s(data["priority"])),
            confidence=float(_s(data.get("confidence", "1.0"))),
            payload=json.loads(_s(data.get("payload", "{}"))),
            correlation_id=UUID(_s(data.get("correlation_id", str(uuid4())))),
            version=_s(data.get("version", "1.0")),
            event_type=_s(data["event_type"]),
        )


# ─── Specialised event types ──────────────────────────────────────────────────

class ObservationEvent(LOSEvent):
    """Fired when a new observation is ingested."""

    loop: ScientificLoop = ScientificLoop.SYSTEM
    source: str = "observation-ingester"
    event_type: str = EventType.OBSERVATION_RECEIVED.value


class HydrologicalEvent(LOSEvent):
    """Event from the Hydrological scientific loop."""

    loop: ScientificLoop = ScientificLoop.HYDROLOGICAL
    source: str = "hydrological-loop"


class ChemicalEvent(LOSEvent):
    """Event from the Chemical scientific loop."""

    loop: ScientificLoop = ScientificLoop.CHEMICAL
    source: str = "chemical-loop"


class EcologicalEvent(LOSEvent):
    """Event from the Ecological scientific loop."""

    loop: ScientificLoop = ScientificLoop.ECOLOGICAL
    source: str = "ecological-loop"


class InfrastructureEvent(LOSEvent):
    """Event from the Infrastructure scientific loop."""

    loop: ScientificLoop = ScientificLoop.INFRASTRUCTURE
    source: str = "infrastructure-loop"


class DecisionEvent(LOSEvent):
    """Event from the Decision Engine."""

    loop: ScientificLoop = ScientificLoop.DECISION
    source: str = "decision-engine"


class RecommendationEvent(LOSEvent):
    """Fired when a recommendation changes status (approved/rejected/implemented)."""

    loop: ScientificLoop = ScientificLoop.DECISION
    source: str = "recommendation-service"
    event_type: str = EventType.RECOMMENDATION_APPROVED.value


class LearningEvent(LOSEvent):
    """Fired during the learning cycle when knowledge is updated."""

    loop: ScientificLoop = ScientificLoop.SYSTEM
    source: str = "learning-engine"
    event_type: str = EventType.LEARNING_CYCLE_COMPLETED.value


class SystemEvent(LOSEvent):
    """System-level lifecycle and health events."""

    loop: ScientificLoop = ScientificLoop.SYSTEM
    source: str = "los-system"
    event_type: str = EventType.SYSTEM_STARTUP.value


# Alias used in __init__.py imports
LOSEventMessage = LOSEvent
