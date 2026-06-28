"""Abstract base class for all LOS scientific models."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass
class ModelOutput:
    """Standardised output from any scientific model."""
    model_name: str
    model_version: str
    lagoon_id: UUID
    computed_at: datetime
    values: dict[str, Any]           # primary output values
    diagnostics: dict[str, Any]      # solver diagnostics, residuals, etc.
    confidence: float                 # 0–1
    uncertainty: dict[str, float]     # per-parameter uncertainty bounds
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "lagoon_id": str(self.lagoon_id),
            "computed_at": self.computed_at.isoformat(),
            "values": self.values,
            "diagnostics": self.diagnostics,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "metadata": self.metadata,
            "warnings": self.warnings,
            "errors": self.errors,
            "runtime_seconds": self.runtime_seconds,
        }

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.confidence > 0.0


class ScientificModel(ABC):
    """
    Abstract base for all LOS scientific models.

    Models are stateless computation units — they receive inputs,
    run calculations, and return ModelOutput. They do not subscribe
    to events (services do that).
    """

    model_name: str = "abstract_model"
    model_version: str = "1.0.0"

    @abstractmethod
    def run(self, inputs: dict[str, Any], lagoon_id: UUID) -> ModelOutput:
        """
        Execute the model with given inputs.

        Must be synchronous and deterministic.
        """

    def validate_inputs(self, inputs: dict[str, Any], required: list[str]) -> list[str]:
        """
        Validate that all required inputs are present and non-None.

        Returns list of missing field names (empty = all present).
        """
        missing = [k for k in required if k not in inputs or inputs[k] is None]
        return missing

    def _make_output(
        self,
        lagoon_id: UUID,
        values: dict[str, Any],
        diagnostics: dict[str, Any] | None = None,
        confidence: float = 1.0,
        uncertainty: dict[str, float] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        runtime_seconds: float = 0.0,
    ) -> ModelOutput:
        return ModelOutput(
            model_name=self.model_name,
            model_version=self.model_version,
            lagoon_id=lagoon_id,
            computed_at=datetime.now(tz=UTC),
            values=values,
            diagnostics=diagnostics or {},
            confidence=confidence,
            uncertainty=uncertainty or {},
            warnings=warnings or [],
            errors=errors or [],
            runtime_seconds=runtime_seconds,
        )
