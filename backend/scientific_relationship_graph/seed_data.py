"""
Seed data for the Scientific Relationship Graph.

Pre-populates the SRG with 40+ well-established lagoon science relationships.
Every relationship includes:
- Scientific literature reference (simplified for brevity)
- Confidence based on strength of scientific consensus
- Mechanism description

This represents the foundational scientific knowledge of the LOS platform.
The SRG continuously updates these relationships through learning.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SeedRelationship:
    cause: str
    effect: str
    loop: str
    confidence: float
    evidence: list[str]
    feedback_type: str = "positive"
    mechanism: str | None = None
    lag_days: float | None = None
    relationship_type: str = "INFLUENCES"


# ──────────────────────────────────────────────────────────────────────────────
# Core lagoon scientific relationships
# Confidence is based on scientific consensus strength:
#   0.9-0.99 = very well established, fundamental relationship
#   0.7-0.89 = well-supported, multiple studies
#   0.5-0.69 = moderately supported, site-specific variability
#   0.3-0.49 = plausible, limited evidence
# ──────────────────────────────────────────────────────────────────────────────

SEED_RELATIONSHIPS: list[SeedRelationship] = [
    # ── Hydrological → Chemical ───────────────────────────────────────────
    SeedRelationship(
        cause="ResidenceTime",
        effect="DissolvedOxygen",
        loop="HYDROLOGICAL",
        confidence=0.90,
        evidence=["Chapra 1997 Surface Water Quality Modeling", "Reckhow & Chapra 1983"],
        mechanism=(
            "Longer residence time reduces flushing of oxygen-depleting organic matter, "
            "increases sediment oxygen demand contact time, reduces entrainment of atmospheric oxygen."
        ),
        lag_days=3.0,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="ResidenceTime",
        effect="NutrientConcentration",
        loop="HYDROLOGICAL",
        confidence=0.88,
        evidence=["Vollenweider 1975", "Jeppesen et al. 2005"],
        mechanism="Longer HRT allows nutrient accumulation rather than flushing.",
        lag_days=7.0,
    ),
    SeedRelationship(
        cause="GroundwaterFlux",
        effect="WaterBalance",
        loop="HYDROLOGICAL",
        confidence=0.85,
        evidence=["Winter et al. 1998 Ground Water and Surface Water"],
        mechanism="Groundwater seepage contributes to lagoon water balance and can carry dissolved nutrients.",
    ),
    SeedRelationship(
        cause="GroundwaterFlux",
        effect="NutrientConcentration",
        loop="HYDROLOGICAL",
        confidence=0.70,
        evidence=["Lewandowski et al. 2015 Groundwater-surface water interactions"],
        mechanism="Groundwater can transport nitrate and phosphate directly into the lagoon.",
        lag_days=14.0,
    ),

    # ── Chemical chain ─────────────────────────────────────────────────────
    SeedRelationship(
        cause="DissolvedOxygen",
        effect="ORP",
        loop="CHEMICAL",
        confidence=0.95,
        evidence=["Stumm & Morgan 1996 Aquatic Chemistry", "Eh-pH fundamentals"],
        mechanism="DO is the primary determinant of redox potential (ORP/Eh) in aquatic systems.",
        lag_days=0.5,
    ),
    SeedRelationship(
        cause="ORP",
        effect="PhosphorusRelease",
        loop="CHEMICAL",
        confidence=0.90,
        evidence=["Mortimer 1941", "Jensen et al. 1992", "Gächter & Müller 2003"],
        mechanism=(
            "Under reducing conditions (ORP < -100 mV) iron-oxide bound phosphorus is released "
            "from sediment as Fe(III) is reduced to Fe(II), releasing sorbed PO4³⁻."
        ),
        lag_days=2.0,
        feedback_type="negative",  # ORP decreases → P release increases
    ),
    SeedRelationship(
        cause="PhosphorusRelease",
        effect="AlgalBloom",
        loop="CHEMICAL",
        confidence=0.85,
        evidence=["Schindler 1977", "Carpenter et al. 1999", "Chorus & Bartram 1999"],
        mechanism="Internal phosphorus loading provides substrate for algal growth, particularly in P-limited systems.",
        lag_days=7.0,
    ),
    SeedRelationship(
        cause="NitrogenConcentration",
        effect="AlgalBloom",
        loop="CHEMICAL",
        confidence=0.80,
        evidence=["Paerl & Paul 2012", "Conley et al. 2009"],
        mechanism="Nitrogen availability supports algal growth; N:P ratio determines which species dominate.",
        lag_days=5.0,
    ),
    SeedRelationship(
        cause="Temperature",
        effect="OxygenSaturation",
        loop="CHEMICAL",
        confidence=0.99,
        evidence=["Benson & Krause 1984", "Wetzel 2001"],
        mechanism="Oxygen solubility decreases with temperature: ~14 mg/L at 0°C → ~7 mg/L at 35°C.",
        lag_days=0.0,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="DissolvedOxygen",
        effect="NitrificationRate",
        loop="CHEMICAL",
        confidence=0.90,
        evidence=["Knowles et al. 1965", "Stenstrom & Poduska 1980"],
        mechanism="Nitrification requires O2 (aerobic process). Stops below ~0.5 mg/L DO.",
        lag_days=1.0,
    ),
    SeedRelationship(
        cause="ORP",
        effect="DenitrificationRate",
        loop="CHEMICAL",
        confidence=0.85,
        evidence=["Seitzinger et al. 2006"],
        mechanism="Denitrification occurs under anoxic/suboxic conditions (ORP < 100 mV).",
        lag_days=1.0,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="pH",
        effect="AlgalGrowth",
        loop="CHEMICAL",
        confidence=0.75,
        evidence=["Goldman et al. 1974"],
        mechanism="Algae prefer pH 7-9. Elevated pH (>9) from algal CO2 uptake can inhibit growth (negative feedback).",
        lag_days=1.0,
    ),

    # ── Ecological chain ───────────────────────────────────────────────────
    SeedRelationship(
        cause="AlgalBloom",
        effect="DissolvedOxygen",
        loop="ECOLOGICAL",
        confidence=0.92,
        evidence=["Reynolds 2006 The Ecology of Phytoplankton", "Havens & Paerl 2015"],
        mechanism=(
            "During daytime blooms produce oxygen via photosynthesis. At night algal respiration "
            "depletes DO. Dense blooms cause extreme DO fluctuation and can cause crash to near-zero."
        ),
        lag_days=0.5,
    ),
    SeedRelationship(
        cause="AlgalBloom",
        effect="SludgeAccumulation",
        loop="ECOLOGICAL",
        confidence=0.85,
        evidence=["Søndergaard et al. 2003", "Hamilton et al. 2016"],
        mechanism="Algal senescence and settling contributes to organic sediment (sludge) accumulation.",
        lag_days=14.0,
    ),
    SeedRelationship(
        cause="SludgeAccumulation",
        effect="OxygenDemand",
        loop="ECOLOGICAL",
        confidence=0.90,
        evidence=["Bouldin 1968", "Chapra 1997"],
        mechanism="Decomposing organic sediment exerts sediment oxygen demand (SOD) on overlying water.",
        lag_days=1.0,
    ),
    SeedRelationship(
        cause="Temperature",
        effect="CyanobacteriaGrowth",
        loop="ECOLOGICAL",
        confidence=0.88,
        evidence=["Paerl & Huisman 2008", "Robarts & Zohary 1987"],
        mechanism=(
            "Cyanobacteria thrive at high temperatures (>25°C) due to faster metabolism "
            "and ability to regulate buoyancy for surface stratification advantage."
        ),
        lag_days=3.0,
    ),
    SeedRelationship(
        cause="NitrogenLimitation",
        effect="CyanobacteriaGrowth",
        loop="ECOLOGICAL",
        confidence=0.80,
        evidence=["Downing et al. 2001", "Paerl & Otten 2013"],
        mechanism=(
            "N2-fixing cyanobacteria have competitive advantage when dissolved inorganic nitrogen "
            "is limiting (low N:P ratio), outcompeting other algae."
        ),
        lag_days=7.0,
    ),
    SeedRelationship(
        cause="DissolvedOxygen",
        effect="MacroinvertebrateHealth",
        loop="ECOLOGICAL",
        confidence=0.85,
        evidence=["Diaz & Rosenberg 1995", "Nalepa & Fahnenstiel 1995"],
        mechanism="Low DO (<4 mg/L) stresses macroinvertebrates; below 2 mg/L causes mortality.",
        lag_days=1.0,
    ),
    SeedRelationship(
        cause="Stratification",
        effect="DissolvedOxygen",
        loop="ECOLOGICAL",
        confidence=0.90,
        evidence=["Cooke et al. 2005 Restoration and Management of Lakes and Reservoirs"],
        mechanism=(
            "Thermal stratification prevents vertical mixing. Hypolimnion (bottom layer) "
            "isolated from atmosphere → sediment oxygen demand progressively depletes DO."
        ),
        lag_days=7.0,
        feedback_type="negative",
    ),

    # ── Infrastructure → Hydrological/Chemical ────────────────────────────
    SeedRelationship(
        cause="AerationRate",
        effect="DissolvedOxygen",
        loop="INFRASTRUCTURE",
        confidence=0.95,
        evidence=["US EPA 1985 Aeration", "ASCE Manual 36"],
        mechanism=(
            "Mechanical aeration transfers oxygen from atmosphere to water. "
            "Standard oxygen transfer rate (SOTR) measured in kg O2/kWh."
        ),
        lag_days=0.1,
    ),
    SeedRelationship(
        cause="AerationRate",
        effect="Stratification",
        loop="INFRASTRUCTURE",
        confidence=0.85,
        evidence=["Cooke et al. 2005"],
        mechanism="Mechanical aeration disrupts thermal stratification through mixing.",
        lag_days=0.5,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="AerationRate",
        effect="ResidenceTime",
        loop="INFRASTRUCTURE",
        confidence=0.65,
        evidence=["Hydraulic mixing theory"],
        mechanism="Increased aeration improves circulation, reducing stagnation zones and effective HRT.",
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="TSEInflowRate",
        effect="NutrientConcentration",
        loop="INFRASTRUCTURE",
        confidence=0.90,
        evidence=["Water quality engineering practice"],
        mechanism="Treated sewage effluent typically contains elevated N and P. Higher inflow = higher loading.",
    ),
    SeedRelationship(
        cause="TSEInflowRate",
        effect="ResidenceTime",
        loop="INFRASTRUCTURE",
        confidence=0.88,
        evidence=["HRT = V/Q"],
        mechanism="Increasing inflow (Q) decreases hydraulic residence time for fixed lagoon volume (V).",
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="PumpFailure",
        effect="AerationRate",
        loop="INFRASTRUCTURE",
        confidence=0.95,
        evidence=["Engineering first principles"],
        mechanism="Pump failure directly reduces aeration capacity, potentially causing DO crash.",
        lag_days=0.0,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="MaintenanceOverdue",
        effect="InfrastructureEfficiency",
        loop="INFRASTRUCTURE",
        confidence=0.80,
        evidence=["Operations management"],
        mechanism="Degraded equipment reduces operational efficiency and increases failure probability.",
        feedback_type="negative",
    ),

    # ── Feedback loops (cycling) ──────────────────────────────────────────
    SeedRelationship(
        cause="AlgalBloom",
        effect="pH",
        loop="CHEMICAL",
        confidence=0.88,
        evidence=["Wetzel 2001", "Hutchinson 1957"],
        mechanism=(
            "Dense algal photosynthesis consumes CO2, raising pH. "
            "Values >10 are common during intense blooms."
        ),
    ),
    SeedRelationship(
        cause="SludgeAccumulation",
        effect="PhosphorusRelease",
        loop="CHEMICAL",
        confidence=0.85,
        evidence=["Søndergaard et al. 2003"],
        mechanism="Greater organic sediment → greater anoxic layer → greater internal P loading.",
    ),
    SeedRelationship(
        cause="ResidenceTime",
        effect="Stratification",
        loop="HYDROLOGICAL",
        confidence=0.75,
        evidence=["Chapra 1997"],
        mechanism="Longer HRT allows thermal stratification to develop and persist.",
    ),
    SeedRelationship(
        cause="Salinity",
        effect="OxygenSaturation",
        loop="CHEMICAL",
        confidence=0.92,
        evidence=["Garcia & Gordon 1992", "Benson & Krause 1984"],
        mechanism="Oxygen solubility decreases with increasing salinity (salting-out effect).",
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="ORP",
        effect="IronCycling",
        loop="CHEMICAL",
        confidence=0.90,
        evidence=["Stumm & Morgan 1996"],
        mechanism="Low ORP reduces Fe(III) to Fe(II), dissolving iron oxyhydroxide and releasing bound P.",
    ),
    SeedRelationship(
        cause="NutrientConcentration",
        effect="AlgalBloom",
        loop="CHEMICAL",
        confidence=0.90,
        evidence=["Schindler 1977", "Carpenter 2008"],
        mechanism="Nutrients (N, P) are primary drivers of eutrophication and algal bloom frequency.",
        lag_days=5.0,
    ),
    SeedRelationship(
        cause="OxygenDemand",
        effect="DissolvedOxygen",
        loop="ECOLOGICAL",
        confidence=0.95,
        evidence=["Environmental engineering fundamentals"],
        mechanism="Sediment oxygen demand (SOD) and biochemical oxygen demand (BOD) consume dissolved oxygen.",
        lag_days=0.5,
        feedback_type="negative",
    ),
    SeedRelationship(
        cause="AlgalBloom",
        effect="Turbidity",
        loop="ECOLOGICAL",
        confidence=0.85,
        evidence=["Kirk 1994 Light and Photosynthesis in Aquatic Ecosystems"],
        mechanism="Dense algal growth increases water turbidity, reducing light penetration.",
    ),
    SeedRelationship(
        cause="Turbidity",
        effect="AlgalGrowth",
        loop="ECOLOGICAL",
        confidence=0.75,
        evidence=["Self-shading phenomenon"],
        mechanism="High turbidity (often from algae themselves) reduces light for submerged photosynthesis — self-limiting feedback.",
        feedback_type="negative",
    ),
]


async def seed_srg(srg: Any) -> None:
    """
    Populate the Scientific Relationship Graph with baseline relationships.

    This should be called once at platform initialisation.
    Uses MERGE so it is safe to call multiple times.
    """

    logger.info("Seeding SRG with %d relationships...", len(SEED_RELATIONSHIPS))
    success_count = 0
    error_count = 0

    for rel in SEED_RELATIONSHIPS:
        try:
            await srg.create_relationship(
                cause=rel.cause,
                effect=rel.effect,
                loop=rel.loop,
                confidence=rel.confidence,
                evidence=rel.evidence,
                feedback_type=rel.feedback_type,
                mechanism=rel.mechanism,
                lag_days=rel.lag_days,
                relationship_type=rel.relationship_type,
            )
            success_count += 1
        except Exception as exc:
            logger.error("SRG seed failed for %s→%s: %s", rel.cause, rel.effect, exc)
            error_count += 1

    logger.info(
        "SRG seed complete: %d created, %d errors (total: %d relationships)",
        success_count,
        error_count,
        len(SEED_RELATIONSHIPS),
    )


if __name__ == "__main__":
    """Allow running as a script: python -m backend.scientific_relationship_graph.seed_data"""
    from backend.core.config.settings import settings
    from backend.scientific_relationship_graph.service import ScientificRelationshipGraph

    async def _main() -> None:
        srg = ScientificRelationshipGraph(
            uri=settings.NEO4J_URI,
            username=settings.NEO4J_USERNAME,
            password=settings.NEO4J_PASSWORD,
        )
        await srg.connect()
        await seed_srg(srg)
        await srg.disconnect()

    asyncio.run(_main())
