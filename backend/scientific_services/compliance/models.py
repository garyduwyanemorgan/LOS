"""Compliance service data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class ComplianceLevel(str, Enum):
    COMPLIANT = "compliant"
    WARNING = "warning"
    VIOLATION = "violation"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ParameterCompliance:
    parameter: str
    value: float | None
    unit: str
    limit_type: str        # "max", "min", "range"
    limit_value: float | None
    limit_max: float | None = None
    limit_min: float | None = None
    level: ComplianceLevel = ComplianceLevel.UNKNOWN
    margin_pct: float | None = None  # headroom as % of limit
    standard: str = ""    # e.g. "UAE Environmental Agency — Lagoon Discharge"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "limit_type": self.limit_type,
            "limit_value": self.limit_value,
            "limit_max": self.limit_max,
            "limit_min": self.limit_min,
            "level": self.level.value,
            "margin_pct": self.margin_pct,
            "standard": self.standard,
            "notes": self.notes,
        }


@dataclass
class ComplianceViolation:
    parameter: str
    value: float
    unit: str
    limit_breached: float
    level: ComplianceLevel
    description: str
    recommended_action: str
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "limit_breached": self.limit_breached,
            "level": self.level.value,
            "description": self.description,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ComplianceStatus:
    lagoon_id: UUID
    timestamp: datetime

    overall_level: ComplianceLevel
    parameters: list[ParameterCompliance] = field(default_factory=list)
    violations: list[ComplianceViolation] = field(default_factory=list)
    warnings_count: int = 0
    violations_count: int = 0
    critical_count: int = 0

    # Internal KPIs
    do_compliance: ParameterCompliance | None = None
    ph_compliance: ParameterCompliance | None = None
    turbidity_compliance: ParameterCompliance | None = None
    nutrient_compliance: ParameterCompliance | None = None

    # Permit / regulatory reference
    regulatory_framework: str = "UAE Environmental Agency"
    permit_reference: str = ""

    confidence: float = 0.0
    data_completeness_pct: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "timestamp": self.timestamp.isoformat(),
            "overall_level": self.overall_level.value,
            "parameters": [p.to_dict() for p in self.parameters],
            "violations": [v.to_dict() for v in self.violations],
            "warnings_count": self.warnings_count,
            "violations_count": self.violations_count,
            "critical_count": self.critical_count,
            "do_compliance": self.do_compliance.to_dict() if self.do_compliance else None,
            "ph_compliance": self.ph_compliance.to_dict() if self.ph_compliance else None,
            "turbidity_compliance": (
                self.turbidity_compliance.to_dict() if self.turbidity_compliance else None
            ),
            "nutrient_compliance": (
                self.nutrient_compliance.to_dict() if self.nutrient_compliance else None
            ),
            "regulatory_framework": self.regulatory_framework,
            "permit_reference": self.permit_reference,
            "confidence": self.confidence,
            "data_completeness_pct": self.data_completeness_pct,
            "notes": self.notes,
        }
