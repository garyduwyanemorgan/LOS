"""Pydantic models for the Shared Memory layer.

Shared memory stores interpreted operational experience, not raw data.
These models define the structure of what each memory tier holds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ShortTermMemory(BaseModel):
    """Current operational state for a lagoon — stored in Redis with TTL.

    Refreshed every loop cycle.  Represents the system's best current
    understanding of lagoon conditions.
    """

    lagoon_id: UUID
    key: str
    value: Any
    ttl_seconds: int = 3600
    stored_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = {"arbitrary_types_allowed": True}


class WorkingMemory(BaseModel):
    """Active hypothesis under evaluation — stored in Redis with TTL.

    Created when a scientific loop identifies a potential condition.
    Cleared when the hypothesis is confirmed, rejected, or times out.
    """

    lagoon_id: UUID
    hypothesis_id: str = Field(default_factory=lambda: str(uuid4()))
    condition: str = Field(description="The condition being evaluated, e.g. 'algal_bloom_imminent'")
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    expires_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    loop: str = ""


class LongTermMemoryEntry(BaseModel):
    """Persistent knowledge entry stored in PostgreSQL.

    Long-term memory survives restarts and represents accumulated
    understanding that does not expire.
    """

    id: UUID = Field(default_factory=uuid4)
    lagoon_id: UUID
    memory_type: str = Field(description="Category: 'knowledge', 'pattern', 'baseline', 'learning'")
    loop: str | None = None
    key: str
    value: dict[str, Any]
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ScientificMemoryEntry(BaseModel):
    """Current state of a scientific loop — stored in Redis with 6h TTL.

    Each loop writes its state here after every cycle so that other loops
    and the Decision Engine can read it without querying the database.
    """

    lagoon_id: UUID
    loop: str = Field(description="ScientificLoop value: hydrological, chemical, etc.")
    key: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = {"arbitrary_types_allowed": True}


class OperationalMemoryEntry(BaseModel):
    """Record of a significant operational event — stored in PostgreSQL.

    Used by the Decision Engine to avoid repeating the same recommendation
    or intervention within a short time window.
    """

    id: UUID = Field(default_factory=uuid4)
    lagoon_id: UUID
    event_type: str
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    expires_at: datetime | None = None


class LearningRecord(BaseModel):
    """Record of a recommendation outcome used for continuous improvement.

    The learning engine reads these to update SRG relationship confidences
    and improve future recommendation accuracy.
    """

    id: UUID = Field(default_factory=uuid4)
    lagoon_id: UUID
    recommendation_id: UUID
    predicted_outcome: str
    actual_outcome: str
    confidence_delta: float = Field(
        description="Change in system confidence: positive = prediction correct, negative = wrong"
    )
    success: bool
    action_category: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    @property
    def was_accurate(self) -> bool:
        """True if the prediction matched the actual outcome."""
        return self.confidence_delta >= 0.0


class LagoonMemorySummary(BaseModel):
    """Aggregated view of all memory tiers for a lagoon.

    Returned by SharedMemoryService.get_lagoon_summary().
    """

    lagoon_id: UUID
    scientific_memory: dict[str, dict[str, Any]] = Field(default_factory=dict)
    working_memory: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    recent_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    learning_records_count: int = 0
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
