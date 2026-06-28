"""Seed data for initial LOS deployment.

Creates the demo organisation, admin user, and a representative lagoon with
sensors and operating objectives so the platform is immediately usable.

Usage:
    python -m backend.database.seed_data
    # or via the alembic data migration hook
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import AsyncSessionLocal, init_db

log = logging.getLogger(__name__)

# ── Fixed UUIDs for deterministic seeding ─────────────────────────────────────

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ADMIN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
ENGINEER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
LAGOON_DEMO_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
SENSOR_DO_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
SENSOR_PH_ID = uuid.UUID("00000000-0000-0000-0000-000000000021")
SENSOR_TEMP_ID = uuid.UUID("00000000-0000-0000-0000-000000000022")
SENSOR_COND_ID = uuid.UUID("00000000-0000-0000-0000-000000000023")
SENSOR_ORP_ID = uuid.UUID("00000000-0000-0000-0000-000000000024")
SENSOR_TURBIDITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000025")


async def seed(session: AsyncSession) -> None:
    """Insert all seed records idempotently."""
    from sqlalchemy import select, text

    from backend.database.models import (
        Lagoon,
        OperatingObjective,
        Organisation,
        Sensor,
        User,
    )

    now = datetime.now(tz=UTC)

    # ── Organisation ──────────────────────────────────────────────────────────
    existing_org = await session.get(Organisation, ORG_ID)
    if existing_org is None:
        org = Organisation(
            id=ORG_ID,
            name="LOS Demo Organisation",
            slug="los-demo",
            subscription_tier="professional",
            is_active=True,
            metadata={"seeded": True, "seeded_at": now.isoformat()},
            created_at=now,
            updated_at=now,
        )
        session.add(org)
        log.info("Seeded organisation: %s", org.name)

    # ── Users ─────────────────────────────────────────────────────────────────
    if await session.get(User, ADMIN_USER_ID) is None:
        admin = User(
            id=ADMIN_USER_ID,
            org_id=ORG_ID,
            email="admin@los-demo.com",
            full_name="LOS Administrator",
            role="ADMIN",
            is_active=True,
            preferences={"theme": "dark", "notifications": True},
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        log.info("Seeded admin user: %s", admin.email)

    if await session.get(User, ENGINEER_USER_ID) is None:
        engineer = User(
            id=ENGINEER_USER_ID,
            org_id=ORG_ID,
            email="engineer@los-demo.com",
            full_name="LOS Engineer",
            role="ENGINEER",
            is_active=True,
            preferences={"theme": "dark", "notifications": True},
            created_at=now,
            updated_at=now,
        )
        session.add(engineer)
        log.info("Seeded engineer user: %s", engineer.email)

    # ── Demo Lagoon ───────────────────────────────────────────────────────────
    if await session.get(Lagoon, LAGOON_DEMO_ID) is None:
        lagoon = Lagoon(
            id=LAGOON_DEMO_ID,
            org_id=ORG_ID,
            name="Al Qudra Demo Lagoon",
            slug="al-qudra-demo",
            location={
                "latitude": 24.9868,
                "longitude": 55.1587,
                "city": "Dubai",
                "country": "AE",
                "timezone": "Asia/Dubai",
            },
            volume_m3=850_000.0,
            surface_area_m2=420_000.0,
            max_depth_m=2.8,
            design_info={
                "design_year": 2018,
                "design_body": "Dubai Municipality",
                "primary_purpose": "ecological_reserve",
                "secondary_purpose": "recreational",
                "liner_type": "HDPE",
                "inlet_count": 3,
                "outlet_count": 2,
                "aerator_count": 12,
            },
            infrastructure_config={
                "aeration_capacity_kw": 180,
                "pump_stations": 2,
                "telemetry_enabled": True,
                "scada_system": "Aveva",
            },
            operating_parameters={
                "target_do_mg_l": 7.0,
                "min_do_mg_l": 4.0,
                "critical_do_mg_l": 2.0,
                "target_ph": 7.8,
                "min_ph": 7.2,
                "max_ph": 8.5,
                "max_turbidity_ntu": 20.0,
                "min_water_level_m": 2.0,
                "max_water_level_m": 2.8,
            },
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(lagoon)
        log.info("Seeded lagoon: %s", lagoon.name)

    # ── Sensors ───────────────────────────────────────────────────────────────
    sensors_to_seed = [
        Sensor(
            id=SENSOR_DO_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="DO Sensor — Inlet Zone",
            sensor_type="dissolved_oxygen",
            depth_m=0.5,
            unit="mg/L",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="YSI",
            model_number="ProDSS",
            serial_number="YSI-DO-001",
            status="active",
            is_active=True,
            metadata={"location_note": "inlet_zone", "installation_date": "2022-03-15"},
            created_at=now,
            updated_at=now,
        ),
        Sensor(
            id=SENSOR_PH_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="pH Sensor — Central",
            sensor_type="ph",
            depth_m=0.5,
            unit="pH",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="YSI",
            model_number="ProDSS",
            serial_number="YSI-PH-001",
            status="active",
            is_active=True,
            metadata={"location_note": "central", "installation_date": "2022-03-15"},
            created_at=now,
            updated_at=now,
        ),
        Sensor(
            id=SENSOR_TEMP_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="Temperature Sensor — Central",
            sensor_type="temperature",
            depth_m=0.5,
            unit="°C",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="YSI",
            model_number="ProDSS",
            serial_number="YSI-TEMP-001",
            status="active",
            is_active=True,
            metadata={"location_note": "central", "installation_date": "2022-03-15"},
            created_at=now,
            updated_at=now,
        ),
        Sensor(
            id=SENSOR_COND_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="Conductivity Sensor — Outlet Zone",
            sensor_type="conductivity",
            depth_m=0.5,
            unit="µS/cm",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="YSI",
            model_number="ProDSS",
            serial_number="YSI-COND-001",
            status="active",
            is_active=True,
            metadata={"location_note": "outlet_zone", "installation_date": "2022-03-15"},
            created_at=now,
            updated_at=now,
        ),
        Sensor(
            id=SENSOR_ORP_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="ORP Sensor — Deep Zone",
            sensor_type="orp",
            depth_m=2.0,
            unit="mV",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="Hach",
            model_number="LDO2",
            serial_number="HACH-ORP-001",
            status="active",
            is_active=True,
            metadata={"location_note": "deep_zone", "installation_date": "2023-01-10"},
            created_at=now,
            updated_at=now,
        ),
        Sensor(
            id=SENSOR_TURBIDITY_ID,
            lagoon_id=LAGOON_DEMO_ID,
            name="Turbidity Sensor — Inlet Zone",
            sensor_type="turbidity",
            depth_m=0.3,
            unit="NTU",
            calibration_factor=1.0,
            calibration_offset=0.0,
            manufacturer="Hach",
            model_number="TU5300sc",
            serial_number="HACH-TURB-001",
            status="active",
            is_active=True,
            metadata={"location_note": "inlet_zone", "installation_date": "2023-01-10"},
            created_at=now,
            updated_at=now,
        ),
    ]

    for sensor in sensors_to_seed:
        if await session.get(Sensor, sensor.id) is None:
            session.add(sensor)
            log.info("Seeded sensor: %s", sensor.name)

    # ── Operating Objectives ──────────────────────────────────────────────────
    objectives = [
        OperatingObjective(
            lagoon_id=LAGOON_DEMO_ID,
            objective_type="water_quality",
            name="Maintain Dissolved Oxygen above 4 mg/L",
            description=(
                "Prevent hypoxic conditions that trigger anaerobic decomposition, "
                "H₂S production, and fish kills."
            ),
            target_value=7.0,
            unit="mg/L",
            priority=10,
            weight=0.35,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        OperatingObjective(
            lagoon_id=LAGOON_DEMO_ID,
            objective_type="ecological",
            name="Maintain pH 7.2–8.5",
            description="Support aquatic biodiversity; prevent corrosive or toxic pH excursions.",
            target_value=7.8,
            unit="pH",
            priority=8,
            weight=0.20,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        OperatingObjective(
            lagoon_id=LAGOON_DEMO_ID,
            objective_type="ecological",
            name="Prevent algal bloom events",
            description=(
                "Keep bloom probability below 30% by managing nutrient loading and "
                "stratification."
            ),
            target_value=0.3,
            unit="probability",
            priority=9,
            weight=0.25,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        OperatingObjective(
            lagoon_id=LAGOON_DEMO_ID,
            objective_type="infrastructure",
            name="Maintain aerator availability ≥ 90%",
            description="Ensure aeration capacity is not compromised by unplanned maintenance.",
            target_value=0.90,
            unit="fraction",
            priority=7,
            weight=0.20,
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
    ]

    result = await session.execute(
        select(OperatingObjective).where(OperatingObjective.lagoon_id == LAGOON_DEMO_ID)
    )
    existing_objectives = result.scalars().all()
    if not existing_objectives:
        for obj in objectives:
            session.add(obj)
        log.info("Seeded %d operating objectives", len(objectives))

    await session.commit()
    log.info("Seed data committed successfully")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
