"""
Direct database seed — injects sensors, 30 days of hourly observations,
and operating objectives for Al Qudra Lake 1.
Run inside the backend container:
  docker exec los_backend python /app/scripts/seed_observations.py
"""
from __future__ import annotations

import asyncio
import math
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.environ["DATABASE_URL"]
LAGOON_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

# ── Sensor definitions ────────────────────────────────────────────────────────

SENSORS = [
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000001"),
     "name": "DO Probe — Centre Buoy", "sensor_type": "optical_do",
     "unit": "mg/L", "depth_m": 0.5, "manufacturer": "YSI",
     "model_number": "ProDO", "serial_number": "DO-001",
     "meta_param": "dissolved_oxygen"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000002"),
     "name": "pH Sensor — Inlet", "sensor_type": "electrochemical",
     "unit": "pH", "depth_m": 0.3, "manufacturer": "Hach",
     "model_number": "PHC301", "serial_number": "PH-001",
     "meta_param": "ph"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000003"),
     "name": "ORP Sensor — Centre", "sensor_type": "electrochemical",
     "unit": "mV", "depth_m": 0.5, "manufacturer": "Hach",
     "model_number": "MTC101", "serial_number": "ORP-001",
     "meta_param": "orp"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000004"),
     "name": "Temperature — Outlet", "sensor_type": "thermistor",
     "unit": "°C", "depth_m": 0.5, "manufacturer": "Campbell",
     "model_number": "CS547A", "serial_number": "TEMP-001",
     "meta_param": "water_temperature"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000005"),
     "name": "Turbidity — Centre", "sensor_type": "optical_turbidity",
     "unit": "NTU", "depth_m": 0.4, "manufacturer": "YSI",
     "model_number": "TurbPlus", "serial_number": "TURB-001",
     "meta_param": "turbidity"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000006"),
     "name": "Chlorophyll-a Fluorometer", "sensor_type": "fluorometer",
     "unit": "µg/L", "depth_m": 0.3, "manufacturer": "Turner",
     "model_number": "Cyclops-7", "serial_number": "CHL-001",
     "meta_param": "chlorophyll_a"},
    {"id": uuid.UUID("aaaa0000-0000-0000-0000-000000000007"),
     "name": "Conductivity Sensor", "sensor_type": "conductivity",
     "unit": "mS/cm", "depth_m": 0.5, "manufacturer": "YSI",
     "model_number": "ProSal", "serial_number": "COND-001",
     "meta_param": "conductivity"},
]

# ── Realistic signal generators ───────────────────────────────────────────────

def _noise(scale: float) -> float:
    return random.gauss(0, scale)

def gen_do(t: datetime) -> float:
    """DO mg/L — diurnal cycle driven by photosynthesis, summer stress."""
    hour = t.hour + t.minute / 60
    day_frac = (t - datetime(2026, 5, 29, tzinfo=UTC)).total_seconds() / 86400
    diurnal = 2.5 * math.sin(math.pi * (hour - 6) / 12)   # peak 18:00, trough 06:00
    trend = -0.02 * day_frac                                # slight deterioration
    return max(1.5, min(12.0, 7.2 + diurnal + trend + _noise(0.3)))

def gen_ph(t: datetime) -> float:
    """pH — driven by photosynthesis (CO2 uptake during day)."""
    hour = t.hour + t.minute / 60
    diurnal = 0.6 * math.sin(math.pi * (hour - 6) / 12)
    return max(7.0, min(9.5, 7.9 + diurnal + _noise(0.05)))

def gen_orp(t: datetime) -> float:
    """ORP mV — inversely correlated with bloom events."""
    hour = t.hour + t.minute / 60
    diurnal = 60 * math.sin(math.pi * (hour - 8) / 12)
    return max(-150, min(450, 220 + diurnal + _noise(15)))

def gen_temp(t: datetime) -> float:
    """Water temperature °C — slow diurnal, summer baseline high."""
    hour = t.hour + t.minute / 60
    diurnal = 3.0 * math.sin(math.pi * (hour - 4) / 12)   # peak 16:00
    day_frac = (t - datetime(2026, 5, 29, tzinfo=UTC)).total_seconds() / 86400
    seasonal = 0.05 * day_frac                              # warming trend
    return max(22.0, min(38.0, 31.5 + diurnal + seasonal + _noise(0.2)))

def gen_turbidity(t: datetime) -> float:
    """Turbidity NTU — elevated after wind events (random spikes)."""
    base = 8.0 + _noise(2.0)
    spike = 20.0 if random.random() < 0.03 else 0  # 3% chance of wind event
    return max(1.0, min(80.0, base + spike))

def gen_chlorophyll(t: datetime) -> float:
    """Chlorophyll-a µg/L — diurnal + growing bloom over 30 days."""
    hour = t.hour + t.minute / 60
    day_frac = (t - datetime(2026, 5, 29, tzinfo=UTC)).total_seconds() / 86400
    diurnal = 8 * math.sin(math.pi * (hour - 8) / 12)
    bloom_growth = 1.8 * day_frac                           # bloom developing
    return max(2.0, min(120.0, 18.0 + bloom_growth + diurnal + _noise(3.0)))

def gen_conductivity(t: datetime) -> float:
    """Conductivity mS/cm — slowly rising with evaporation."""
    day_frac = (t - datetime(2026, 5, 29, tzinfo=UTC)).total_seconds() / 86400
    trend = 0.04 * day_frac
    return max(3.0, min(18.0, 7.5 + trend + _noise(0.3)))

GENERATORS = {
    "dissolved_oxygen": gen_do,
    "ph": gen_ph,
    "orp": gen_orp,
    "water_temperature": gen_temp,
    "turbidity": gen_turbidity,
    "chlorophyll_a": gen_chlorophyll,
    "conductivity": gen_conductivity,
}

UNITS = {
    "dissolved_oxygen": "mg/L",
    "ph": "pH",
    "orp": "mV",
    "water_temperature": "°C",
    "turbidity": "NTU",
    "chlorophyll_a": "µg/L",
    "conductivity": "mS/cm",
}

# ── Operating objectives ──────────────────────────────────────────────────────

OBJECTIVES = [
    {"name": "Dissolved Oxygen", "objective_type": "water_quality",
     "target_value": 7.0, "current_value": 6.8, "unit": "mg/L",
     "priority": 10, "weight": 1.0},
    {"name": "pH Range", "objective_type": "water_quality",
     "target_value": 7.8, "current_value": 8.1, "unit": "pH",
     "priority": 9, "weight": 0.9},
    {"name": "Bloom Risk", "objective_type": "ecological",
     "target_value": 20.0, "current_value": 35.0, "unit": "µg/L Chl-a",
     "priority": 8, "weight": 0.85},
    {"name": "Turbidity", "objective_type": "water_quality",
     "target_value": 10.0, "current_value": 8.5, "unit": "NTU",
     "priority": 7, "weight": 0.7},
    {"name": "Water Temperature", "objective_type": "operational",
     "target_value": 30.0, "current_value": 32.3, "unit": "°C",
     "priority": 6, "weight": 0.6},
]


async def main() -> None:
    random.seed(42)
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # ── Upsert sensors ────────────────────────────────────────────────────
        print("Seeding sensors...")
        for s in SENSORS:
            existing = await session.execute(
                text("SELECT id FROM sensors WHERE id = :id"), {"id": s["id"]}
            )
            if existing.scalar_one_or_none():
                print(f"  skip (exists): {s['name']}")
                continue
            await session.execute(text("""
                INSERT INTO sensors (id, lagoon_id, name, sensor_type, unit,
                    depth_m, manufacturer, model_number, serial_number,
                    is_active, status, calibration_factor, calibration_offset,
                    metadata, created_at, updated_at)
                VALUES (:id, :lagoon_id, :name, :sensor_type, :unit,
                    :depth_m, :manufacturer, :model_number, :serial_number,
                    true, 'active', 1.0, 0.0,
                    :metadata, NOW(), NOW())
            """), {
                "id": s["id"], "lagoon_id": LAGOON_ID,
                "name": s["name"], "sensor_type": s["sensor_type"],
                "unit": s["unit"], "depth_m": s.get("depth_m"),
                "manufacturer": s.get("manufacturer"),
                "model_number": s.get("model_number"),
                "serial_number": s.get("serial_number"),
                "metadata": '{"parameter": "' + s["meta_param"] + '", "sampling_interval_s": 3600}',
            })
            print(f"  created: {s['name']}")
        await session.commit()

        # ── Generate observations ─────────────────────────────────────────────
        print("Generating 30 days of hourly observations...")
        end_ts = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start_ts = end_ts - timedelta(days=30)

        sensor_by_param = {s["meta_param"]: s["id"] for s in SENSORS}

        batch: list[dict] = []
        ts = start_ts
        while ts <= end_ts:
            for param, gen_fn in GENERATORS.items():
                sid = sensor_by_param.get(param)
                quality = "good" if random.random() > 0.02 else "suspect"
                batch.append({
                    "id": uuid.uuid4(),
                    "lagoon_id": LAGOON_ID,
                    "sensor_id": sid,
                    "parameter": param,
                    "value": round(gen_fn(ts), 3),
                    "unit": UNITS[param],
                    "timestamp": ts,
                    "quality_flag": quality,
                    "source": "sensor",
                    "confidence": 0.95 if quality == "good" else 0.6,
                    "depth_m": 0.5,
                })
            ts += timedelta(hours=1)

        # Insert in chunks of 1000
        print(f"  Inserting {len(batch)} observations in chunks...")
        for i in range(0, len(batch), 1000):
            chunk = batch[i:i+1000]
            await session.execute(text("""
                INSERT INTO observations
                    (id, lagoon_id, sensor_id, parameter, value, unit,
                     timestamp, quality_flag, source, confidence, depth_m,
                     created_at)
                VALUES
                    (:id, :lagoon_id, :sensor_id, :parameter, :value, :unit,
                     :timestamp, :quality_flag, :source, :confidence, :depth_m,
                     NOW())
                ON CONFLICT DO NOTHING
            """), chunk)
            print(f"  chunk {i//1000 + 1}/{(len(batch)-1)//1000 + 1} done")
        await session.commit()
        print(f"  Done: {len(batch)} observations written")

        # ── Operating objectives ──────────────────────────────────────────────
        print("Setting operating objectives...")
        await session.execute(
            text("DELETE FROM operating_objectives WHERE lagoon_id = :lid"),
            {"lid": LAGOON_ID}
        )
        for obj in OBJECTIVES:
            await session.execute(text("""
                INSERT INTO operating_objectives
                    (id, lagoon_id, name, objective_type, target_value,
                     current_value, unit, priority, weight, is_active,
                     created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :lagoon_id, :name, :objective_type,
                     :target_value, :current_value, :unit, :priority,
                     :weight, true, NOW(), NOW())
            """), {"lagoon_id": LAGOON_ID, **obj})
        await session.commit()
        print(f"  {len(OBJECTIVES)} objectives set")

    await engine.dispose()
    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(main())
