"""Initial schema — all LOS tables.

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ── organisations ────────────────────────────────────────────────────────
    op.create_table(
        "organisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("subscription_tier", sa.String(50), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("slug", name="uq_organisations_slug"),
        sa.CheckConstraint(
            "subscription_tier IN ('free','starter','professional','enterprise')",
            name="ck_organisations_subscription_tier",
        ),
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="VIEWER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ('SUPERADMIN','ADMIN','ENGINEER','SCIENTIST','OPERATOR','VIEWER')",
            name="ck_users_role",
        ),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])

    # ── lagoons ──────────────────────────────────────────────────────────────
    op.create_table(
        "lagoons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("location", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("geometry", sa.Text(), nullable=True),  # PostGIS POLYGON stored as WKT
        sa.Column("volume_m3", sa.Float(), nullable=True),
        sa.Column("surface_area_m2", sa.Float(), nullable=True),
        sa.Column("max_depth_m", sa.Float(), nullable=True),
        sa.Column("design_info", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("infrastructure_config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("operating_parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "slug", name="uq_lagoons_org_slug"),
    )
    op.create_index("ix_lagoons_org_id", "lagoons", ["org_id"])
    # PostGIS geometry index created separately
    op.execute(
        "ALTER TABLE lagoons ALTER COLUMN geometry TYPE geometry(POLYGON,4326) "
        "USING ST_GeomFromText(geometry, 4326)"
    )
    op.execute(
        "CREATE INDEX ix_lagoons_geometry ON lagoons USING GIST (geometry)"
    )

    # ── sensors ──────────────────────────────────────────────────────────────
    op.create_table(
        "sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sensor_type", sa.String(100), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),  # PostGIS POINT as WKT
        sa.Column("depth_m", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("calibration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_factor", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("calibration_offset", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("model_number", sa.String(255), nullable=True),
        sa.Column("serial_number", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('active','inactive','faulty','calibrating','decommissioned')",
            name="ck_sensors_status",
        ),
    )
    op.create_index("ix_sensors_lagoon_id", "sensors", ["lagoon_id"])
    op.execute(
        "ALTER TABLE sensors ALTER COLUMN location TYPE geometry(POINT,4326) "
        "USING ST_GeomFromText(location, 4326)"
    )
    op.execute("CREATE INDEX ix_sensors_location ON sensors USING GIST (location)")

    # ── observations ─────────────────────────────────────────────────────────
    op.create_table(
        "observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parameter", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("depth_m", sa.Float(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="sensor"),
        sa.Column("quality_flag", sa.String(20), nullable=False, server_default="good"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "quality_flag IN ('good','suspect','bad','corrected','missing')",
            name="ck_observations_quality_flag",
        ),
        sa.CheckConstraint(
            "source IN ('sensor','manual','laboratory','model','estimated')",
            name="ck_observations_source",
        ),
        sa.CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_observations_confidence"),
    )
    op.create_index("ix_observations_lagoon_ts", "observations", ["lagoon_id", "timestamp"])
    op.create_index("ix_observations_sensor_ts", "observations", ["sensor_id", "timestamp"])
    op.create_index("ix_observations_parameter", "observations",
                    ["lagoon_id", "parameter", "timestamp"])

    # ── laboratory_results ───────────────────────────────────────────────────
    op.create_table(
        "laboratory_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sample_id", sa.String(100), nullable=False),
        sa.Column("sample_type", sa.String(50), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("quality_control", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("lab_reference", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "sample_type IN ('water','sediment','soil','biota')",
            name="ck_lab_results_sample_type",
        ),
    )
    op.create_index("ix_lab_results_lagoon_collected", "laboratory_results",
                    ["lagoon_id", "collected_at"])

    # ── infrastructure_assets ────────────────────────────────────────────────
    op.create_table(
        "infrastructure_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("specifications", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("commissioned_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="operational"),
        sa.Column("last_maintenance", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maintenance_interval_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "asset_type IN ('aerator','pump','inlet','outlet','weir','sensor_array',"
            "'diffuser','screen','valve','pipeline')",
            name="ck_infrastructure_asset_type",
        ),
        sa.CheckConstraint(
            "status IN ('operational','degraded','faulty','offline','maintenance')",
            name="ck_infrastructure_status",
        ),
    )
    op.create_index("ix_infrastructure_lagoon", "infrastructure_assets", ["lagoon_id"])

    # ── los_events ───────────────────────────────────────────────────────────
    op.create_table(
        "los_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("loop", sa.String(50), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "loop IN ('hydrological','chemical','ecological','infrastructure','decision','system')",
            name="ck_los_events_loop",
        ),
        sa.CheckConstraint(
            "priority IN ('critical','high','normal','low')",
            name="ck_los_events_priority",
        ),
    )
    op.create_index("ix_los_events_lagoon_created", "los_events", ["lagoon_id", "created_at"])
    op.create_index("ix_los_events_correlation", "los_events", ["correlation_id"])
    op.create_index("ix_los_events_loop", "los_events", ["loop"])
    op.create_index("ix_los_events_event_type", "los_events", ["event_type"])

    # ── operating_objectives ─────────────────────────────────────────────────
    op.create_table(
        "operating_objectives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objective_type", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint("weight BETWEEN 0.0 AND 1.0", name="ck_objectives_weight"),
        sa.CheckConstraint("priority BETWEEN 1 AND 10", name="ck_objectives_priority"),
    )
    op.create_index("ix_operating_objectives_lagoon", "operating_objectives", ["lagoon_id"])

    # ── recommendations ──────────────────────────────────────────────────────
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(500), nullable=False),
        sa.Column("action_category", sa.String(100), nullable=False),
        sa.Column("scientific_reason", sa.Text(), nullable=False),
        sa.Column("contributing_loops", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("expected_timeframe_days", sa.Integer(), nullable=True),
        sa.Column("alternative_options", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("operating_objective_ids", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_by_system", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','implemented','cancelled','superseded')",
            name="ck_recommendations_status",
        ),
        sa.CheckConstraint(
            "action_category IN ('aeration','chemical_dosing','water_management','maintenance',"
            "'investigation','monitoring','dredging','other')",
            name="ck_recommendations_category",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0.0 AND 1.0", name="ck_recommendations_confidence"
        ),
        sa.CheckConstraint(
            "priority IN ('critical','high','normal','low')", name="ck_recommendations_priority"
        ),
    )
    op.create_index("ix_recommendations_lagoon_status", "recommendations",
                    ["lagoon_id", "status"])
    op.create_index("ix_recommendations_created_at", "recommendations", ["created_at"])

    # ── interventions ────────────────────────────────────────────────────────
    op.create_table(
        "interventions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(500), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("implemented_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_outcome", sa.Text(), nullable=True),
        sa.Column("outcome_confidence", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('planned','in_progress','completed','failed','cancelled')",
            name="ck_interventions_status",
        ),
        sa.CheckConstraint(
            "outcome_confidence BETWEEN 0.0 AND 1.0",
            name="ck_interventions_outcome_confidence",
        ),
    )
    op.create_index("ix_interventions_lagoon", "interventions", ["lagoon_id"])
    op.create_index("ix_interventions_recommendation", "interventions", ["recommendation_id"])

    # ── scientific_model_runs ────────────────────────────────────────────────
    op.create_table(
        "scientific_model_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False, server_default="1.0.0"),
        sa.Column("input_parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_results", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("limitations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("execution_time_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_model_runs_status",
        ),
        sa.CheckConstraint("confidence BETWEEN 0.0 AND 1.0", name="ck_model_runs_confidence"),
    )
    op.create_index("ix_model_runs_lagoon_created", "scientific_model_runs",
                    ["lagoon_id", "created_at"])
    op.create_index("ix_model_runs_model_name", "scientific_model_runs", ["model_name"])

    # ── shared_memory_entries ────────────────────────────────────────────────
    op.create_table(
        "shared_memory_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lagoon_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lagoons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("loop", sa.String(50), nullable=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("lagoon_id", "memory_type", "loop", "key",
                            name="uq_shared_memory_key"),
    )
    op.create_index("ix_shared_memory_lagoon_type", "shared_memory_entries",
                    ["lagoon_id", "memory_type"])
    op.create_index("ix_shared_memory_expires_at", "shared_memory_entries", ["expires_at"])

    # ── audit_log ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changes", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_audit_log_user_timestamp", "audit_log", ["user_id", "timestamp"])
    op.create_index("ix_audit_log_resource", "audit_log", ["resource_type", "resource_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("shared_memory_entries")
    op.drop_table("scientific_model_runs")
    op.drop_table("interventions")
    op.drop_table("recommendations")
    op.drop_table("operating_objectives")
    op.drop_table("los_events")
    op.drop_table("infrastructure_assets")
    op.drop_table("laboratory_results")
    op.drop_table("observations")
    op.drop_table("sensors")
    op.drop_table("lagoons")
    op.drop_table("users")
    op.drop_table("organisations")
