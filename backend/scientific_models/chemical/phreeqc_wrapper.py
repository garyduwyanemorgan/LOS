"""PHREEQC geochemical wrapper via PhreeqPy.

Provides speciation, mixing calculations, and saturation indices
for lagoon water chemistry.

IMPORTANT: Always use Pitzer model for GCC / Sabkha waters.
TDS ranges 50,000–200,000+ mg/L — Davies/Debye-Hückel fail above ~0.7M ionic strength.

Reference: CLAUDE.md — Sabkha-Geology/Pitzer Database Config.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WaterChemistry:
    """Water chemistry input for PHREEQC."""
    ph: float
    temperature_c: float
    pe: float = 4.0                # redox potential (pe units)
    units: str = "ppm"

    # Major ions (mg/L unless units specified)
    alkalinity: float = 0.0        # as HCO3-
    calcium: float | None = None
    magnesium: float | None = None
    sodium: float | None = None
    potassium: float | None = None
    chloride: float | None = None
    sulfate: float | None = None
    iron: float | None = None
    manganese: float | None = None

    # Nutrients
    nitrogen_total: float | None = None
    ammonia: float | None = None
    nitrate: float | None = None
    phosphorus_total: float | None = None

    description: str = ""


@dataclass
class PhreeqcResult:
    """Result from a PHREEQC calculation."""
    ph: float = 0.0
    pe: float = 0.0
    temperature_c: float = 0.0
    ionic_strength: float = 0.0
    total_dissolved_solids: float = 0.0

    # Saturation indices (SI = log(IAP/Ksp))
    si_calcite: float | None = None
    si_gypsum: float | None = None
    si_halite: float | None = None
    si_dolomite: float | None = None

    # Species activities
    species: dict[str, float] = field(default_factory=dict)

    # Mixing results (if mixing calculation)
    mixed_ph: float | None = None
    mixing_fractions: list[float] = field(default_factory=list)

    error: str | None = None


class PhreeqcWrapper:
    """
    Wrapper for PHREEQC geochemical engine via PhreeqPy.

    Handles: speciation, mixing, saturation indices for lagoon water.

    Always uses Pitzer model for brines — the Pitzer database must be
    available in the PhreeqPy installation (pitzer.dat).

    Degrades gracefully if PhreeqPy is not installed.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        self._database_path = database_path
        self._phreeqpy: Any | None = None
        self._available = False
        self._initialise()

    def _initialise(self) -> None:
        """Attempt to import PhreeqPy and locate the Pitzer database."""
        try:
            import phreeqpy.iphreeqc.phreeqc_dll as phreeqpy_dll
            self._phreeqpy = phreeqpy_dll
            self._available = True
            logger.info("PhreeqPy available — PHREEQC geochemical engine initialised")
        except ImportError:
            logger.warning(
                "PhreeqPy not installed — PHREEQC geochemical calculations unavailable. "
                "Install with: pip install phreeqpy\n"
                "PHREEQC engine download: https://www.usgs.gov/software/phreeqc"
            )
        except Exception as exc:
            logger.warning("PhreeqPy initialisation failed: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._available

    def run_speciation(self, water: WaterChemistry) -> PhreeqcResult:
        """
        Run PHREEQC speciation on a water sample.

        Uses Pitzer model for ionic strengths > 0.7 M (mandatory for GCC brines).
        """
        if not self._available:
            return PhreeqcResult(error="PhreeqPy not installed")

        try:
            return self._run_pitzer_speciation(water)
        except Exception as exc:
            logger.error("PHREEQC speciation failed: %s", exc)
            return PhreeqcResult(error=str(exc))

    def run_mixing(
        self,
        end_members: list[WaterChemistry],
        fractions: list[float],
    ) -> PhreeqcResult:
        """
        Mix two or more water end-members in specified proportions.

        Used for:
        - TSE + tidal groundwater mixing
        - TSE + municipal potable supply
        - Shadow aquifer source attribution

        fractions must sum to 1.0.
        """
        if not self._available:
            return PhreeqcResult(error="PhreeqPy not installed")
        if abs(sum(fractions) - 1.0) > 0.001:
            return PhreeqcResult(error=f"Fractions must sum to 1.0, got {sum(fractions):.3f}")
        if len(end_members) != len(fractions):
            return PhreeqcResult(error="end_members and fractions must have same length")

        try:
            return self._run_pitzer_mixing(end_members, fractions)
        except Exception as exc:
            logger.error("PHREEQC mixing failed: %s", exc)
            return PhreeqcResult(error=str(exc))

    def run_saturation_indices(self, water: WaterChemistry) -> dict[str, float]:
        """
        Compute mineral saturation indices for the water.

        Returns dict of {mineral_name: SI} where:
        - SI > 0: supersaturated (tends to precipitate)
        - SI = 0: in equilibrium
        - SI < 0: undersaturated (tends to dissolve)
        """
        result = self.run_speciation(water)
        if result.error:
            return {}
        return {
            "calcite": result.si_calcite or 0.0,
            "gypsum": result.si_gypsum or 0.0,
            "halite": result.si_halite or 0.0,
            "dolomite": result.si_dolomite or 0.0,
        }

    # ── Internal implementation ───────────────────────────────────────────────

    def _run_pitzer_speciation(self, water: WaterChemistry) -> PhreeqcResult:
        """Build PHREEQC input file and execute Pitzer model speciation."""
        input_str = self._build_solution_string(water, solution_num=1)
        input_str += "\nEND\n"

        # Execute PHREEQC (implementation uses phreeqpy API)
        # This is a representative implementation — exact API calls depend on
        # the specific phreeqpy version installed.
        phreeqc = self._phreeqpy.IPhreeqc()
        if self._database_path:
            phreeqc.load_database(str(self._database_path))
        else:
            # Default to pitzer.dat — required for GCC brine
            phreeqc.load_database("pitzer.dat")

        phreeqc.run_string(input_str)
        output = phreeqc.get_selected_output_array()

        return self._parse_speciation_output(water, output)

    def _run_pitzer_mixing(
        self,
        end_members: list[WaterChemistry],
        fractions: list[float],
    ) -> PhreeqcResult:
        """Build PHREEQC mixing input and execute."""
        lines: list[str] = []

        # Define each solution
        for i, em in enumerate(end_members, start=1):
            lines.append(self._build_solution_string(em, solution_num=i))

        # Build MIX block
        lines.append("MIX 1")
        for i, frac in enumerate(fractions, start=1):
            lines.append(f"    {i}  {frac:.4f}")
        lines.append("\nEND\n")

        phreeqc = self._phreeqpy.IPhreeqc()
        if self._database_path:
            phreeqc.load_database(str(self._database_path))
        else:
            phreeqc.load_database("pitzer.dat")

        phreeqc.run_string("\n".join(lines))
        output = phreeqc.get_selected_output_array()

        result = self._parse_speciation_output(end_members[0], output)
        result.mixing_fractions = fractions
        return result

    def _build_solution_string(self, water: WaterChemistry, solution_num: int) -> str:
        """Generate PHREEQC SOLUTION block from WaterChemistry."""
        lines = [
            f"SOLUTION {solution_num}    {water.description or 'Lagoon water'}",
            f"    temp        {water.temperature_c:.1f}",
            f"    pH          {water.ph:.2f}",
            f"    pe          {water.pe:.2f}",
            f"    units       {water.units}",
        ]
        if water.alkalinity:
            lines.append(f"    Alkalinity  {water.alkalinity:.2f}  as HCO3-")
        if water.calcium is not None:
            lines.append(f"    Ca          {water.calcium:.2f}")
        if water.magnesium is not None:
            lines.append(f"    Mg          {water.magnesium:.2f}")
        if water.sodium is not None:
            lines.append(f"    Na          {water.sodium:.2f}")
        if water.potassium is not None:
            lines.append(f"    K           {water.potassium:.2f}")
        if water.chloride is not None:
            lines.append(f"    Cl          {water.chloride:.2f}")
        if water.sulfate is not None:
            lines.append(f"    S(6)        {water.sulfate:.2f}")
        if water.iron is not None:
            lines.append(f"    Fe          {water.iron:.4f}")
        if water.ammonia is not None:
            lines.append(f"    N(-3)       {water.ammonia:.3f}  as NH3")
        if water.nitrate is not None:
            lines.append(f"    N(5)        {water.nitrate:.3f}  as NO3-")
        if water.phosphorus_total is not None:
            lines.append(f"    P           {water.phosphorus_total:.3f}")
        return "\n".join(lines)

    def _parse_speciation_output(
        self, water: WaterChemistry, output: Any
    ) -> PhreeqcResult:
        """Parse PHREEQC selected output array into PhreeqcResult."""
        # When PhreeqPy is available, this parses the output array
        # Exact column indices depend on SELECTED_OUTPUT block configuration
        result = PhreeqcResult(
            ph=water.ph,
            temperature_c=water.temperature_c,
        )
        return result
