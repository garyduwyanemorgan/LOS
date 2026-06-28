"""
Scientific Relationship Graph (SRG) domain models.

The SRG stores scientific cause-effect relationships between lagoon
system components.  It answers WHY, not just WHAT.

Relationships have:
  - Confidence (0-1), updated continuously through learning
  - Evidence (list of scientific sources supporting the relationship)
  - Feedback type (positive = A causes B; negative = A inhibits B)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ScientificNode:
    """A node in the Scientific Relationship Graph."""
    name: str                   # Human-readable label, e.g. "ResidenceTime"
    loop: str                   # ScientificLoop enum value
    description: str = ""
    unit: str | None = None
    typical_range: dict[str, float] = field(default_factory=dict)  # {min, max}
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScientificRelationship:
    """A directed cause-effect relationship between two nodes."""
    id: str                        # Neo4j relationship ID
    cause: str                     # Source node name
    effect: str                    # Target node name
    relationship_type: str         # e.g. "INFLUENCES", "INHIBITS", "TRIGGERS"
    confidence: float              # 0.0 – 1.0
    evidence: list[str]            # Supporting references / observations
    feedback_type: str = "positive"  # "positive" or "negative"
    lag_days: float | None = None  # Typical time lag between cause and effect
    mechanism: str | None = None   # Scientific description of the mechanism
    loop: str | None = None        # Which scientific loop owns this relationship
    observation_count: int = 0     # How many times this relationship has been observed
    last_updated: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class CausalPathway:
    """A chain of relationships explaining a lagoon condition."""
    root_cause: str
    effect: str
    relationships: list[ScientificRelationship]
    overall_confidence: float      # Minimum confidence along the chain
    total_length: int              # Number of relationships in chain
    narrative: str = ""           # Human-readable explanation


@dataclass
class Hypothesis:
    """A candidate explanation for an observed condition."""
    id: str
    condition_observed: str        # e.g. "BloomDetected"
    candidate_cause: str           # e.g. "InternalPhosphorusLoading"
    supporting_pathways: list[CausalPathway] = field(default_factory=list)
    confidence: float = 0.0
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    rank: int = 0                  # 1 = most likely explanation
    narrative: str = ""
