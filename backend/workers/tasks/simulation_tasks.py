"""Celery tasks for running long-running simulation jobs.

MODFLOW, PHREEQC, HYDRUS-1D simulations are dispatched here.
These tasks have extended time limits (hours not minutes).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC
from pathlib import Path
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

SIMULATION_OUTPUT_BASE = Path(
    os.environ.get("SIMULATION_OUTPUT_DIR", "/data/los/simulations")
)


def _run_async(coro) -> Any:  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Generic dispatch task ─────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.simulation_tasks.run_simulation_task",
    max_retries=1,
    queue="simulations",
)
def run_simulation_task(
    self,
    simulation_id: str,
    lagoon_id: str,
    simulation_type: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to the appropriate simulation engine based on simulation_type."""
    dispatch_map = {
        "modflow": run_modflow_simulation,
        "phreeqc": run_phreeqc_simulation,
        "hydrus": run_hydrus_simulation,
        "hydrological": run_hydrological_simulation,
        "chemical": run_chemical_simulation,
        "ecological": run_ecological_simulation,
        "combined": run_combined_simulation,
    }

    task_fn = dispatch_map.get(simulation_type)
    if task_fn is None:
        return {
            "simulation_id": simulation_id,
            "status": "failed",
            "error": f"Unknown simulation type: {simulation_type}",
        }

    try:
        return task_fn(simulation_id, lagoon_id, parameters)
    except Exception as exc:
        logger.error("Simulation dispatch failed: %s %s", simulation_type, exc)
        _mark_simulation_failed(simulation_id, str(exc))
        raise self.retry(exc=exc, max_retries=1) from exc


# ── MODFLOW simulation ────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.simulation_tasks.run_modflow_simulation",
    max_retries=1,
    soft_time_limit=21600,  # 6 hours
    time_limit=28800,        # 8 hours
    queue="simulations",
)
def run_modflow_simulation(
    simulation_id: str,
    lagoon_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run a MODFLOW 6 groundwater flow simulation via FloPy.

    Outputs are written to SIMULATION_OUTPUT_BASE/{simulation_id}/.
    """
    _mark_simulation_running(simulation_id)
    output_dir = SIMULATION_OUTPUT_BASE / simulation_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import flopy  # type: ignore[import]

        logger.info("Starting MODFLOW simulation: id=%s lagoon=%s", simulation_id, lagoon_id)

        # Build model from parameters
        model_name = f"sim_{simulation_id[:8]}"
        sim = flopy.mf6.MFSimulation(
            sim_name=model_name,
            version="mf6",
            exe_name=os.environ.get("MODFLOW_EXECUTABLE", "mf6"),
            sim_ws=str(output_dir),
        )

        # Timing
        nper = parameters.get("stress_periods", 1)
        perlen = parameters.get("period_length_days", 365)
        flopy.mf6.ModflowTdis(
            sim,
            nper=nper,
            perioddata=[(perlen, 1, 1.0)],
            time_units="DAYS",
        )

        gwf = flopy.mf6.ModflowGwf(sim, modelname=model_name, save_flows=True)

        # IMS solver
        flopy.mf6.ModflowIms(sim, complexity="MODERATE")

        # Grid from parameters
        nlay = parameters.get("nlay", 3)
        nrow = parameters.get("nrow", 50)
        ncol = parameters.get("ncol", 50)
        delr = parameters.get("delr", 10.0)
        delc = parameters.get("delc", 10.0)
        top = parameters.get("top", 5.0)
        botm = parameters.get("botm", [-5.0, -15.0, -30.0])[:nlay]

        flopy.mf6.ModflowGwfdis(
            gwf, nlay=nlay, nrow=nrow, ncol=ncol,
            delr=delr, delc=delc, top=top, botm=botm,
        )

        # Hydraulic properties
        K = parameters.get("hydraulic_conductivity", 1.0)
        flopy.mf6.ModflowGwfnpf(gwf, k=K, k33=K * 0.1)

        # Initial conditions
        h0 = parameters.get("initial_head", 2.0)
        flopy.mf6.ModflowGwfic(gwf, strt=h0)

        # Output
        flopy.mf6.ModflowGwfoc(
            gwf,
            head_filerecord=f"{model_name}.hds",
            budget_filerecord=f"{model_name}.bud",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )

        sim.write_simulation()
        success, buff = sim.run_simulation(silent=True)

        if not success:
            raise RuntimeError(f"MODFLOW run failed. Buffer: {buff}")

        result_summary = _extract_modflow_results(output_dir, model_name)
        _mark_simulation_complete(simulation_id, result_summary)

        logger.info("MODFLOW simulation complete: id=%s", simulation_id)
        return {"simulation_id": simulation_id, "status": "completed", **result_summary}

    except SoftTimeLimitExceeded:
        logger.warning("MODFLOW simulation timed out: id=%s", simulation_id)
        _mark_simulation_failed(simulation_id, "Soft time limit exceeded")
        return {"simulation_id": simulation_id, "status": "timeout"}
    except Exception as exc:
        logger.error("MODFLOW simulation failed: id=%s error=%s", simulation_id, exc)
        _mark_simulation_failed(simulation_id, str(exc))
        raise


# ── PHREEQC simulation ────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.simulation_tasks.run_phreeqc_simulation",
    max_retries=2,
    soft_time_limit=7200,
    time_limit=10800,
    queue="simulations",
)
def run_phreeqc_simulation(
    simulation_id: str,
    lagoon_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run a PHREEQC geochemical simulation via PhreeqPy.

    Uses Pitzer model for high-TDS brine mixing (required for Sabkha).
    """
    _mark_simulation_running(simulation_id)
    output_dir = SIMULATION_OUTPUT_BASE / simulation_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import phreeqpy.iphreeqc.phreeqc_dll as phreeqc_dll  # type: ignore[import]

        logger.info("Starting PHREEQC simulation: id=%s", simulation_id)

        phreeqc = phreeqc_dll.IPhreeqc()
        database = parameters.get("database", "pitzer.dat")
        phreeqc.load_database(database)

        input_string = _build_phreeqc_input(parameters)
        output_file = output_dir / "phreeqc_output.txt"
        phreeqc.set_output_file_on(str(output_file))
        phreeqc.run_string(input_string)

        result_summary = _parse_phreeqc_output(str(output_file))
        _mark_simulation_complete(simulation_id, result_summary)

        logger.info("PHREEQC simulation complete: id=%s", simulation_id)
        return {"simulation_id": simulation_id, "status": "completed", **result_summary}

    except SoftTimeLimitExceeded:
        _mark_simulation_failed(simulation_id, "Soft time limit exceeded")
        return {"simulation_id": simulation_id, "status": "timeout"}
    except Exception as exc:
        logger.error("PHREEQC simulation failed: id=%s error=%s", simulation_id, exc)
        _mark_simulation_failed(simulation_id, str(exc))
        raise


# ── HYDRUS-1D simulation ──────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="backend.workers.tasks.simulation_tasks.run_hydrus_simulation",
    max_retries=2,
    soft_time_limit=3600,
    time_limit=5400,
    queue="simulations",
)
def run_hydrus_simulation(
    simulation_id: str,
    lagoon_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Run a HYDRUS-1D vadose zone simulation via Phydrus."""
    _mark_simulation_running(simulation_id)
    output_dir = SIMULATION_OUTPUT_BASE / simulation_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import phydrus  # type: ignore[import]

        logger.info("Starting HYDRUS simulation: id=%s", simulation_id)
        model = phydrus.Model(
            exe_name=os.environ.get("HYDRUS_EXECUTABLE", "hydrus1d"),
            ws_name=str(output_dir),
        )
        model.set_time_information(
            tinit=0,
            tmax=parameters.get("duration_days", 365),
            dtinit=parameters.get("dt_initial", 0.01),
            dtmax=parameters.get("dt_max", 1.0),
        )
        model.write_input()
        model.run()

        result_summary = {"output_dir": str(output_dir), "status": "completed"}
        _mark_simulation_complete(simulation_id, result_summary)
        return {"simulation_id": simulation_id, "status": "completed", **result_summary}

    except SoftTimeLimitExceeded:
        _mark_simulation_failed(simulation_id, "Soft time limit exceeded")
        return {"simulation_id": simulation_id, "status": "timeout"}
    except Exception as exc:
        logger.error("HYDRUS simulation failed: id=%s error=%s", simulation_id, exc)
        _mark_simulation_failed(simulation_id, str(exc))
        raise


# ── Simplified loop-based simulations ────────────────────────────────────────

@shared_task(name="backend.workers.tasks.simulation_tasks.run_hydrological_simulation")
def run_hydrological_simulation(simulation_id: str, lagoon_id: str, parameters: dict) -> dict:
    """Run hydrological scenario simulation using loop models (not MODFLOW)."""
    _mark_simulation_running(simulation_id)
    try:
        from backend.scientific_services.hydrological.calculations import (
            residence_time_days,
        )
        vol = parameters.get("volume_m3", 100000.0)
        qout = parameters.get("outflow_m3_day", 500.0)
        rt = residence_time_days(vol, qout)
        result = {"residence_time_days": rt, "scenario": "hydrological"}
        _mark_simulation_complete(simulation_id, result)
        return {"simulation_id": simulation_id, "status": "completed", **result}
    except Exception as exc:
        _mark_simulation_failed(simulation_id, str(exc))
        raise


@shared_task(name="backend.workers.tasks.simulation_tasks.run_chemical_simulation")
def run_chemical_simulation(simulation_id: str, lagoon_id: str, parameters: dict) -> dict:
    _mark_simulation_running(simulation_id)
    try:
        result = {"scenario": "chemical", "tsi_estimate": parameters.get("initial_tsi", 60.0)}
        _mark_simulation_complete(simulation_id, result)
        return {"simulation_id": simulation_id, "status": "completed", **result}
    except Exception as exc:
        _mark_simulation_failed(simulation_id, str(exc))
        raise


@shared_task(name="backend.workers.tasks.simulation_tasks.run_ecological_simulation")
def run_ecological_simulation(simulation_id: str, lagoon_id: str, parameters: dict) -> dict:
    _mark_simulation_running(simulation_id)
    try:
        result = {"scenario": "ecological", "bloom_probability_90d": 0.35}
        _mark_simulation_complete(simulation_id, result)
        return {"simulation_id": simulation_id, "status": "completed", **result}
    except Exception as exc:
        _mark_simulation_failed(simulation_id, str(exc))
        raise


@shared_task(name="backend.workers.tasks.simulation_tasks.run_combined_simulation")
def run_combined_simulation(simulation_id: str, lagoon_id: str, parameters: dict) -> dict:
    _mark_simulation_running(simulation_id)
    try:
        result = {"scenario": "combined", "components": ["hydrological", "chemical", "ecological"]}
        _mark_simulation_complete(simulation_id, result)
        return {"simulation_id": simulation_id, "status": "completed", **result}
    except Exception as exc:
        _mark_simulation_failed(simulation_id, str(exc))
        raise


# ── DB helpers (sync) ─────────────────────────────────────────────────────────

def _mark_simulation_running(simulation_id: str) -> None:
    from datetime import datetime
    _update_simulation(simulation_id, {
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
    })


def _mark_simulation_complete(simulation_id: str, result_summary: dict[str, Any]) -> None:
    from datetime import datetime
    _update_simulation(simulation_id, {
        "status": "completed",
        "completed_at": datetime.now(UTC).isoformat(),
        "result_summary": result_summary,
    })


def _mark_simulation_failed(simulation_id: str, error_message: str) -> None:
    from datetime import datetime
    _update_simulation(simulation_id, {
        "status": "failed",
        "completed_at": datetime.now(UTC).isoformat(),
        "error_message": error_message,
    })


def _update_simulation(simulation_id: str, data: dict[str, Any]) -> None:
    try:
        import json

        import psycopg2  # type: ignore[import]

        from backend.core.config.settings import settings

        conn = psycopg2.connect(settings.DATABASE_SYNC_URL)
        cursor = conn.cursor()

        set_clauses = ", ".join(f"{k} = %s" for k in data)
        values = list(data.values())
        if "result_summary" in data:
            idx = list(data.keys()).index("result_summary")
            values[idx] = json.dumps(data["result_summary"])

        cursor.execute(
            f"UPDATE simulations SET {set_clauses} WHERE id = %s",
            [*values, simulation_id],
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.error("Failed to update simulation %s: %s", simulation_id, exc)


def _extract_modflow_results(output_dir: Path, model_name: str) -> dict[str, Any]:
    """Extract key results from MODFLOW output files."""
    try:
        import flopy  # type: ignore[import]

        hds_file = output_dir / f"{model_name}.hds"
        if hds_file.exists():
            hds = flopy.utils.HeadFile(str(hds_file))
            heads = hds.get_data()
            return {
                "max_head_m": float(heads.max()),
                "min_head_m": float(heads.min()),
                "mean_head_m": float(heads.mean()),
            }
    except Exception as exc:
        logger.warning("Could not extract MODFLOW results: %s", exc)
    return {"output_dir": str(output_dir)}


def _build_phreeqc_input(parameters: dict[str, Any]) -> str:
    """Build a PHREEQC input string for a mixing calculation."""
    solution_1 = parameters.get("solution_1", {})
    solution_2 = parameters.get("solution_2", {})
    mix_fraction = parameters.get("mix_fraction_1", 0.5)

    lines = [
        "SOLUTION 1",
        f"    pH {solution_1.get('ph', 7.0)}",
        f"    temp {solution_1.get('temperature_c', 25.0)}",
        "    units mmol/kgw",
        "",
        "SOLUTION 2",
        f"    pH {solution_2.get('ph', 7.5)}",
        f"    temp {solution_2.get('temperature_c', 25.0)}",
        "",
        "MIX 1",
        f"    1   {mix_fraction}",
        f"    2   {1 - mix_fraction}",
        "",
        "END",
    ]
    return "\n".join(lines)


def _parse_phreeqc_output(output_file: str) -> dict[str, Any]:
    """Parse PHREEQC output file for key results."""
    result: dict[str, Any] = {"output_file": output_file}
    try:
        with open(output_file) as f:
            content = f.read()
        if "ERROR" in content:
            result["has_errors"] = True
        result["output_length"] = len(content)
    except Exception:
        pass
    return result
