"""Hydrological state models."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class HydrologicalState:
    lagoon_id: UUID
    timestamp: datetime
    water_level_m: float | None
    volume_m3: float | None
    inflow_m3_day: float | None
    outflow_m3_day: float | None
    residence_time_days: float | None
    delta_storage_m3_day: float | None
    evaporation_mm_day: float | None
    groundwater_flux_m3_day: float | None
    hydraulic_connectivity_score: float | None
    water_balance_error_pct: float | None
    surface_area_m2: float | None = None
    tidal_exchange_m3_cycle: float | None = None
    et0_mm_day: float | None = None
    data_completeness_pct: float = 0.0
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "timestamp": self.timestamp.isoformat(),
            "water_level_m": self.water_level_m,
            "volume_m3": self.volume_m3,
            "inflow_m3_day": self.inflow_m3_day,
            "outflow_m3_day": self.outflow_m3_day,
            "residence_time_days": self.residence_time_days,
            "delta_storage_m3_day": self.delta_storage_m3_day,
            "evaporation_mm_day": self.evaporation_mm_day,
            "groundwater_flux_m3_day": self.groundwater_flux_m3_day,
            "hydraulic_connectivity_score": self.hydraulic_connectivity_score,
            "water_balance_error_pct": self.water_balance_error_pct,
            "surface_area_m2": self.surface_area_m2,
            "tidal_exchange_m3_cycle": self.tidal_exchange_m3_cycle,
            "et0_mm_day": self.et0_mm_day,
            "data_completeness_pct": self.data_completeness_pct,
            "confidence": self.confidence,
            "notes": self.notes,
        }
