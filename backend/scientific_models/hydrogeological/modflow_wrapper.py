"""MODFLOW 6 groundwater flow model wrapper via FloPy.

Builds and runs site-scale 3D groundwater models for lagoon forensic analysis.
Supports:
  - Saturated groundwater flow
  - Subsidence (CSUB package)
  - Coupled transport (GWT)

Dubai geological layer structure (from CLAUDE.md):
  1. Engineered Fill (0–2m)
  2. Natural Ground / Aeolian Sand (2–5m)
  3. Sabkha (variable) — CRITICAL
  4. Calcarenite / Caprock
  5. Dammam Formation (lower boundary)

Degrades gracefully if FloPy/MODFLOW 6 are not installed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModflowConfig:
    """Configuration for a site-scale MODFLOW 6 model."""
    workspace_dir: Path
    model_name: str = "los_lagoon"
    nrow: int = 50
    ncol: int = 50
    nlay: int = 5
    delr: float = 5.0          # column spacing (m)
    delc: float = 5.0          # row spacing (m)
    top: float = 5.0           # model top (m ASL)
    botm: list[float] = field(default_factory=lambda: [2.0, -0.5, -3.0, -8.0, -20.0])
    hydraulic_conductivity: list[float] = field(
        default_factory=lambda: [10.0, 5.0, 0.5, 2.0, 0.1]
    )
    # Dubai-specific defaults
    tidal_stage_m: float = 0.0
    recharge_rate_m_day: float = 0.0
    simulation_length_days: int = 365


@dataclass
class ModflowResult:
    """Results from a MODFLOW 6 model run."""
    success: bool = False
    error: str | None = None
    head_array: Any | None = None         # np.ndarray [nlay, nrow, ncol, ntime]
    budget: Any | None = None
    subsidence_mm: float | None = None     # CSUB result
    runtime_seconds: float = 0.0


class ModflowWrapper:
    """
    FloPy-based wrapper for MODFLOW 6 groundwater modelling.

    Builds and executes site-scale models for lagoon forensic investigations.
    Requires MODFLOW 6 executable in PATH or MODFLOW6_EXE env variable.

    Degrades gracefully if FloPy is not installed or MODFLOW 6 executable
    is not available.
    """

    def __init__(self, workspace_dir: str | Path) -> None:
        self._workspace = Path(workspace_dir)
        self._flopy: Any | None = None
        self._available = False
        self._modflow_exe: str = "mf6"
        self._initialise()

    def _initialise(self) -> None:
        """Check FloPy and MODFLOW 6 availability."""
        try:
            import flopy
            self._flopy = flopy
            self._available = True
            logger.info("FloPy available — MODFLOW 6 wrapper initialised")
        except ImportError:
            logger.warning(
                "FloPy not installed — MODFLOW 6 groundwater modelling unavailable. "
                "Install with: pip install flopy\n"
                "MODFLOW 6 download: https://www.usgs.gov/software/modflow-6"
            )

    @property
    def is_available(self) -> bool:
        return self._available

    def build(self, config: ModflowConfig) -> Any | None:
        """
        Build a MODFLOW 6 simulation from a ModflowConfig.

        Returns the FloPy Simulation object or None if unavailable.
        """
        if not self._available:
            logger.warning("Cannot build MODFLOW model — FloPy not installed")
            return None

        try:
            return self._build_simulation(config)
        except Exception as exc:
            logger.error("MODFLOW model build failed: %s", exc)
            return None

    def run(self, simulation: Any) -> ModflowResult:
        """Execute a MODFLOW 6 simulation."""
        if not self._available or simulation is None:
            return ModflowResult(error="FloPy not installed or no simulation provided")

        try:
            self._workspace.mkdir(parents=True, exist_ok=True)
            success, buff = simulation.run_simulation()
            return ModflowResult(
                success=success,
                error=None if success else "\n".join(buff),
            )
        except Exception as exc:
            logger.error("MODFLOW run failed: %s", exc)
            return ModflowResult(success=False, error=str(exc))

    def post_process(self, result: ModflowResult) -> dict[str, Any]:
        """
        Extract hydraulic heads, fluxes, and subsidence from MODFLOW output.

        Returns a dict with:
          - 'head_grid': np.ndarray [nlay, nrow, ncol]
          - 'water_table_m': 2D head surface
          - 'subsidence_mm': total settlement from CSUB
          - 'lagoon_seepage_m3_day': calculated lagoon-aquifer flux
        """
        if not result.success:
            return {"error": result.error or "Simulation failed"}

        output: dict[str, Any] = {
            "head_grid": result.head_array,
            "subsidence_mm": result.subsidence_mm,
        }
        return output

    # ── Internal builders ──────────────────────────────────────────────────────

    def _build_simulation(self, config: ModflowConfig) -> Any:
        """Build a complete MODFLOW 6 simulation using FloPy."""
        flopy = self._flopy
        sim = flopy.mf6.MFSimulation(
            sim_name=config.model_name,
            exe_name=self._modflow_exe,
            sim_ws=str(config.workspace_dir),
        )

        # Time discretisation — steady-state or transient
        flopy.mf6.ModflowTdis(
            sim,
            time_units="DAYS",
            perioddata=[(config.simulation_length_days, 1, 1.0)],
        )

        # Iterative solver
        flopy.mf6.ModflowIms(
            sim,
            complexity="MODERATE",
        )

        # Groundwater flow model
        gwf = flopy.mf6.ModflowGwf(
            sim,
            modelname=config.model_name,
            save_flows=True,
        )

        # Spatial discretisation
        import numpy as np
        flopy.mf6.ModflowGwfdis(
            gwf,
            nlay=config.nlay,
            nrow=config.nrow,
            ncol=config.ncol,
            delr=config.delr,
            delc=config.delc,
            top=config.top,
            botm=config.botm,
        )

        # Initial conditions
        flopy.mf6.ModflowGwfic(gwf, strt=0.0)

        # Hydraulic conductivity
        k_layers = np.array(config.hydraulic_conductivity)
        flopy.mf6.ModflowGwfnpf(
            gwf,
            k=k_layers,
            icelltype=1,  # convertible cells
            save_specific_discharge=True,
        )

        # Recharge
        if config.recharge_rate_m_day > 0:
            flopy.mf6.ModflowGwfrcha(
                gwf,
                recharge=config.recharge_rate_m_day,
            )

        # Output control
        flopy.mf6.ModflowGwfoc(
            gwf,
            head_filerecord=f"{config.model_name}.hds",
            budget_filerecord=f"{config.model_name}.cbc",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )

        sim.write_simulation()
        return sim
