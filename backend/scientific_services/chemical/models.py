"""Chemical state models."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class ChemicalState:
    lagoon_id: UUID
    timestamp: datetime

    # Core water quality
    ph: float | None
    do_mg_l: float | None
    do_saturation_pct: float | None
    orp_mv: float | None
    redox_class: str | None
    conductivity_us_cm: float | None
    temperature_c: float | None
    turbidity_ntu: float | None
    salinity_ppt: float | None

    # Nutrients
    tn_mg_l: float | None
    tp_mg_l: float | None
    nh4_mg_l: float | None
    nh3_mg_l: float | None
    no3_mg_l: float | None
    no2_mg_l: float | None
    po4_mg_l: float | None
    toc_mg_l: float | None
    bod5_mg_l: float | None
    cod_mg_l: float | None

    # Trophic classification
    trophic_state: str | None
    internal_loading_risk: str | None
    chlorophyll_a_ug_l: float | None

    # Carbonate system
    alkalinity_meq_l: float | None
    hco3_mg_l: float | None
    co3_mg_l: float | None
    co2_mg_l: float | None
    tic_mg_l: float | None
    langelier_index: float | None

    # Ions
    ca_mg_l: float | None
    mg_mg_l: float | None
    na_mg_l: float | None
    cl_mg_l: float | None
    so4_mg_l: float | None

    # Quality metadata
    data_completeness_pct: float = 0.0
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lagoon_id": str(self.lagoon_id),
            "timestamp": self.timestamp.isoformat(),
            "ph": self.ph,
            "do_mg_l": self.do_mg_l,
            "do_saturation_pct": self.do_saturation_pct,
            "orp_mv": self.orp_mv,
            "redox_class": self.redox_class,
            "conductivity_us_cm": self.conductivity_us_cm,
            "temperature_c": self.temperature_c,
            "turbidity_ntu": self.turbidity_ntu,
            "salinity_ppt": self.salinity_ppt,
            "tn_mg_l": self.tn_mg_l,
            "tp_mg_l": self.tp_mg_l,
            "nh4_mg_l": self.nh4_mg_l,
            "nh3_mg_l": self.nh3_mg_l,
            "no3_mg_l": self.no3_mg_l,
            "no2_mg_l": self.no2_mg_l,
            "po4_mg_l": self.po4_mg_l,
            "toc_mg_l": self.toc_mg_l,
            "bod5_mg_l": self.bod5_mg_l,
            "cod_mg_l": self.cod_mg_l,
            "trophic_state": self.trophic_state,
            "internal_loading_risk": self.internal_loading_risk,
            "chlorophyll_a_ug_l": self.chlorophyll_a_ug_l,
            "alkalinity_meq_l": self.alkalinity_meq_l,
            "hco3_mg_l": self.hco3_mg_l,
            "co3_mg_l": self.co3_mg_l,
            "co2_mg_l": self.co2_mg_l,
            "tic_mg_l": self.tic_mg_l,
            "langelier_index": self.langelier_index,
            "ca_mg_l": self.ca_mg_l,
            "mg_mg_l": self.mg_mg_l,
            "na_mg_l": self.na_mg_l,
            "cl_mg_l": self.cl_mg_l,
            "so4_mg_l": self.so4_mg_l,
            "data_completeness_pct": self.data_completeness_pct,
            "confidence": self.confidence,
            "notes": self.notes,
        }
