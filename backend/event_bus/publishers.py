"""Publisher helper functions for common LOS event types.

These helpers wrap EventBus.publish() with typed constructors so that
call sites don't need to build event dicts manually.
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.event_bus.bus import event_bus
from backend.event_bus.models import (
    ChemicalEvent,
    DecisionEvent,
    EcologicalEvent,
    EventPriority,
    EventType,
    HydrologicalEvent,
    InfrastructureEvent,
    LearningEvent,
    LOSEvent,
    ObservationEvent,
    RecommendationEvent,
    ScientificLoop,
    SystemEvent,
)


async def publish_observation_event(
    lagoon_id: uuid.UUID,
    parameter: str,
    value: float,
    unit: str,
    sensor_id: str | None = None,
    quality_flag: str = "good",
    confidence: float = 1.0,
    correlation_id: uuid.UUID | None = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> str:
    """Publish an observation ingestion event."""
    event = ObservationEvent(
        lagoon_id=lagoon_id,
        event_type=EventType.OBSERVATION_RECEIVED.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload={
            "parameter": parameter,
            "value": value,
            "unit": unit,
            "sensor_id": sensor_id,
            "quality_flag": quality_flag,
        },
    )
    return await event_bus.publish(event)


async def publish_hydrological_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
    confidence: float = 0.8,
    priority: EventPriority = EventPriority.NORMAL,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish a hydrological loop event."""
    event = HydrologicalEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload=payload,
    )
    return await event_bus.publish(event)


async def publish_chemical_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    parameter: str,
    value: float | None,
    threshold: float | None = None,
    trend: str | None = None,
    confidence: float = 0.9,
    priority: EventPriority = EventPriority.HIGH,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish a chemical loop event (DO, ORP, nutrients, pH, etc.)."""
    event = ChemicalEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload={
            "parameter": parameter,
            "value": value,
            "threshold": threshold,
            "trend": trend,
        },
    )
    return await event_bus.publish(event)


async def publish_ecological_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    risk_level: str,
    indicator: str,
    payload: dict[str, Any] | None = None,
    confidence: float = 0.7,
    priority: EventPriority = EventPriority.HIGH,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish an ecological loop event."""
    event = EcologicalEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload={
            "risk_level": risk_level,
            "indicator": indicator,
            **(payload or {}),
        },
    )
    return await event_bus.publish(event)


async def publish_infrastructure_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    asset_id: str | None,
    asset_type: str | None,
    severity: str = "low",
    payload: dict[str, Any] | None = None,
    priority: EventPriority = EventPriority.HIGH,
    confidence: float = 1.0,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish an infrastructure loop event (asset fault, maintenance, etc.)."""
    event = InfrastructureEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload={
            "asset_id": asset_id,
            "asset_type": asset_type,
            "severity": severity,
            **(payload or {}),
        },
    )
    return await event_bus.publish(event)


async def publish_recommendation_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    recommendation_id: str,
    action_category: str | None = None,
    payload: dict[str, Any] | None = None,
    priority: EventPriority = EventPriority.NORMAL,
    confidence: float = 1.0,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish a recommendation lifecycle event."""
    event = RecommendationEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload={
            "recommendation_id": recommendation_id,
            "action_category": action_category,
            **(payload or {}),
        },
    )
    return await event_bus.publish(event)


async def publish_decision_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
    priority: EventPriority = EventPriority.NORMAL,
    confidence: float = 0.8,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish a decision engine event."""
    event = DecisionEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload=payload,
    )
    return await event_bus.publish(event)


async def publish_learning_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    payload: dict[str, Any],
    confidence: float = 1.0,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Publish a learning cycle event."""
    event = LearningEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=EventPriority.LOW,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload=payload,
    )
    return await event_bus.publish(event)


async def publish_system_event(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    component: str,
    message: str,
    error: str | None = None,
    priority: EventPriority = EventPriority.NORMAL,
) -> str:
    """Publish a system-level lifecycle event."""
    event = SystemEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        priority=priority,
        confidence=1.0,
        payload={
            "component": component,
            "message": message,
            "error": error,
        },
    )
    return await event_bus.publish(event)


async def publish_critical_alert(
    lagoon_id: uuid.UUID,
    event_type: EventType,
    loop: ScientificLoop,
    source: str,
    payload: dict[str, Any],
    confidence: float = 0.95,
    correlation_id: uuid.UUID | None = None,
) -> str:
    """Generic critical-priority event publisher for time-sensitive alerts."""
    event = LOSEvent(
        lagoon_id=lagoon_id,
        event_type=event_type.value,
        loop=loop,
        source=source,
        priority=EventPriority.CRITICAL,
        confidence=confidence,
        correlation_id=correlation_id or uuid.uuid4(),
        payload=payload,
    )
    return await event_bus.publish(event)
