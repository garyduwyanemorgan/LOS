"""Infrastructure state models for pumps, aeration, and maintenance tracking."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class EquipmentStatus(StrEnum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class MaintenancePriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    ROUTINE = "routine"
    DEFERRED = "deferred"


@dataclass
class PumpState:
    equipment_id: str
    name: str
    status: EquipmentStatus
    flow_rate_m3_hr: float | None
    design_flow_rate_m3_hr: float
    efficiency_pct: float | None
    power_kw: float | None
    hours_since_service: float
    service_interval_hours: float
    vibration_mm_s: float | None  # vibration amplitude (alarm > 4.5 mm/s)
    temperature_c: float | None
    maintenance_due: bool

    def to_dict(self) -> dict:
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "status": self.status.value,
            "flow_rate_m3_hr": self.flow_rate_m3_hr,
            "design_flow_rate_m3_hr": self.design_flow_rate_m3_hr,
            "efficiency_pct": self.efficiency_pct,
            "power_kw": self.power_kw,
            "hours_since_service": self.hours_since_service,
            "service_interval_hours": self.service_interval_hours,
            "vibration_mm_s": self.vibration_mm_s,
            "temperature_c": self.temperature_c,
            "maintenance_due": self.maintenance_due,
        }


@dataclass
class AeratorState:
    equipment_id: str
    name: str
    aeration_type: str  # "surface", "diffused", "jet"
    status: EquipmentStatus
    oxygen_transfer_rate_kg_hr: float | None
    design_otr_kg_hr: float
    power_kw: float | None
    coverage_area_m2: float
    do_at_outlet_mg_l: float | None
    hours_since_service: float
    service_interval_hours: float
    maintenance_due: bool

    def to_dict(self) -> dict:
        return {
            "equipment_id": self.equipment_id,
            "name": self.name,
            "aeration_type": self.aeration_type,
            "status": self.status.value,
            "oxygen_transfer_rate_kg_hr": self.oxygen_transfer_rate_kg_hr,
            "design_otr_kg_hr": self.design_otr_kg_hr,
            "power_kw": self.power_kw,
            "coverage_area_m2": self.coverage_area_m2,
            "do_at_outlet_mg_l": self.do_at_outlet_mg_l,
            "hours_since_service": self.hours_since_service,
            "service_interval_hours": self.service_interval_hours,
            "maintenance_due": self.maintenance_due,
        }


@dataclass
class MaintenanceItem:
    item_id: str
    equipment_id: str
    equipment_name: str
    task: str
    priority: MaintenancePriority
    due_date: datetime | None
    overdue_by_days: float
    estimated_downtime_hours: float
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "equipment_id": self.equipment_id,
            "equipment_name": self.equipment_name,
            "task": self.task,
            "priority": self.priority.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "overdue_by_days": self.overdue_by_days,
            "estimated_downtime_hours": self.estimated_downtime_hours,
            "notes": self.notes,
        }


@dataclass
class InfrastructureState:
    lagoon_id: UUID
    timestamp: datetime

    # Equipment states
    pumps: list[PumpState] = field(default_factory=list)
    aerators: list[AeratorState] = field(default_factory=list)

    # Aggregate metrics
    total_aeration_capacity_kg_hr: float = 0.0
    active_aeration_kg_hr: float = 0.0
    aeration_coverage_pct: float = 0.0
    total_circulation_m3_hr: float = 0.0
    active_circulation_m3_hr: float = 0.0
    circulation_efficiency_pct: float = 0.0

    # Maintenance
    maintenance_items: list[MaintenanceItem] = field(default_factory=list)
    overdue_maintenance_count: int = 0
    next_maintenance_due: datetime | None = None
    infrastructure_health_score: float = 0.0  # 0–1

    # Energy
    total_power_consumption_kw: float = 0.0
    energy_efficiency_score: float = 0.0  # 0–1

    # Metadata
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "timestamp": self.timestamp.isoformat(),
            "pumps": [p.to_dict() for p in self.pumps],
            "aerators": [a.to_dict() for a in self.aerators],
            "total_aeration_capacity_kg_hr": self.total_aeration_capacity_kg_hr,
            "active_aeration_kg_hr": self.active_aeration_kg_hr,
            "aeration_coverage_pct": self.aeration_coverage_pct,
            "total_circulation_m3_hr": self.total_circulation_m3_hr,
            "active_circulation_m3_hr": self.active_circulation_m3_hr,
            "circulation_efficiency_pct": self.circulation_efficiency_pct,
            "maintenance_items": [m.to_dict() for m in self.maintenance_items],
            "overdue_maintenance_count": self.overdue_maintenance_count,
            "next_maintenance_due": (
                self.next_maintenance_due.isoformat() if self.next_maintenance_due else None
            ),
            "infrastructure_health_score": self.infrastructure_health_score,
            "total_power_consumption_kw": self.total_power_consumption_kw,
            "energy_efficiency_score": self.energy_efficiency_score,
            "confidence": self.confidence,
            "notes": self.notes,
        }
