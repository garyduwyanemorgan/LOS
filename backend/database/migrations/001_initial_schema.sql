-- =============================================================================
-- LOS Initial Schema Migration — 001
-- =============================================================================
-- Requires: PostgreSQL 15+, PostGIS 3.4+
-- Run with:  psql $DATABASE_URL -f 001_initial_schema.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- trigram indexes for text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";     -- GIN indexes for composite queries


-- ---------------------------------------------------------------------------
-- Organisations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS organisations (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             VARCHAR(255) NOT NULL,
    slug             VARCHAR(100) NOT NULL,
    subscription_tier VARCHAR(50) NOT NULL DEFAULT 'starter'
        CHECK (subscription_tier IN ('free','starter','professional','enterprise')),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    metadata         JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_organisations_slug UNIQUE (slug)
);

CREATE INDEX IF NOT EXISTS ix_organisations_slug ON organisations (slug);
CREATE INDEX IF NOT EXISTS ix_organisations_is_active ON organisations (is_active) WHERE is_active = TRUE;


-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id      UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    email       VARCHAR(320) NOT NULL,
    full_name   VARCHAR(255) NOT NULL,
    role        VARCHAR(50) NOT NULL DEFAULT 'VIEWER'
        CHECK (role IN ('SUPERADMIN','ADMIN','ENGINEER','SCIENTIST','OPERATOR','VIEWER')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMPTZ,
    preferences JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS ix_users_org_id ON users (org_id);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);


-- ---------------------------------------------------------------------------
-- Lagoons
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lagoons (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id               UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name                 VARCHAR(255) NOT NULL,
    slug                 VARCHAR(100) NOT NULL,
    location             JSONB NOT NULL DEFAULT '{}',
    geometry             geometry(POLYGON, 4326),
    volume_m3            DOUBLE PRECISION,
    surface_area_m2      DOUBLE PRECISION,
    max_depth_m          DOUBLE PRECISION,
    design_info          JSONB NOT NULL DEFAULT '{}',
    infrastructure_config JSONB NOT NULL DEFAULT '{}',
    operating_parameters JSONB NOT NULL DEFAULT '{}',
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_lagoons_org_slug UNIQUE (org_id, slug)
);

CREATE INDEX IF NOT EXISTS ix_lagoons_org_id ON lagoons (org_id);
CREATE INDEX IF NOT EXISTS ix_lagoons_geometry ON lagoons USING GIST (geometry);
CREATE INDEX IF NOT EXISTS ix_lagoons_is_active ON lagoons (is_active) WHERE is_active = TRUE;


-- ---------------------------------------------------------------------------
-- Sensors
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensors (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id           UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    name                VARCHAR(255) NOT NULL,
    sensor_type         VARCHAR(100) NOT NULL,
    location            geometry(POINT, 4326),
    depth_m             DOUBLE PRECISION,
    unit                VARCHAR(50) NOT NULL,
    calibration_date    TIMESTAMPTZ,
    calibration_factor  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    calibration_offset  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    manufacturer        VARCHAR(255),
    model_number        VARCHAR(255),
    serial_number       VARCHAR(255),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    status              VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','inactive','faulty','calibrating','decommissioned')),
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_sensors_lagoon_id ON sensors (lagoon_id);
CREATE INDEX IF NOT EXISTS ix_sensors_sensor_type ON sensors (sensor_type);
CREATE INDEX IF NOT EXISTS ix_sensors_location ON sensors USING GIST (location);
CREATE INDEX IF NOT EXISTS ix_sensors_status ON sensors (status);


-- ---------------------------------------------------------------------------
-- Observations (immutable time-series)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observations (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id    UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    sensor_id    UUID REFERENCES sensors(id) ON DELETE SET NULL,
    parameter    VARCHAR(100) NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         VARCHAR(50) NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    depth_m      DOUBLE PRECISION,
    source       VARCHAR(50) NOT NULL DEFAULT 'sensor'
        CHECK (source IN ('sensor','manual','laboratory','model','estimated')),
    quality_flag VARCHAR(20) NOT NULL DEFAULT 'good'
        CHECK (quality_flag IN ('good','suspect','bad','corrected','missing')),
    confidence   DOUBLE PRECISION NOT NULL DEFAULT 1.0
        CHECK (confidence BETWEEN 0.0 AND 1.0),
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- No updated_at: observations are immutable
);

-- Partition-friendly composite indexes for time-series queries
CREATE INDEX IF NOT EXISTS ix_observations_lagoon_ts
    ON observations (lagoon_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_observations_sensor_ts
    ON observations (sensor_id, timestamp DESC)
    WHERE sensor_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_observations_parameter
    ON observations (lagoon_id, parameter, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_observations_quality
    ON observations (lagoon_id, quality_flag, timestamp DESC);


-- ---------------------------------------------------------------------------
-- Laboratory Results
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS laboratory_results (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id     UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    sample_id     VARCHAR(100) NOT NULL,
    sample_type   VARCHAR(50) NOT NULL
        CHECK (sample_type IN ('water','sediment','soil','biota')),
    location      geometry(POINT, 4326),
    collected_at  TIMESTAMPTZ NOT NULL,
    analysed_at   TIMESTAMPTZ,
    parameters    JSONB NOT NULL DEFAULT '{}',
    quality_control JSONB NOT NULL DEFAULT '{}',
    lab_reference VARCHAR(255),
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lab_results_lagoon_collected
    ON laboratory_results (lagoon_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS ix_lab_results_location
    ON laboratory_results USING GIST (location);


-- ---------------------------------------------------------------------------
-- Infrastructure Assets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infrastructure_assets (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id                UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    asset_type               VARCHAR(100) NOT NULL
        CHECK (asset_type IN ('aerator','pump','inlet','outlet','weir','sensor_array','diffuser','screen','valve','pipeline')),
    name                     VARCHAR(255) NOT NULL,
    location                 geometry(POINT, 4326),
    specifications           JSONB NOT NULL DEFAULT '{}',
    commissioned_date        TIMESTAMPTZ,
    status                   VARCHAR(50) NOT NULL DEFAULT 'operational'
        CHECK (status IN ('operational','degraded','faulty','offline','maintenance')),
    last_maintenance         TIMESTAMPTZ,
    maintenance_interval_days INTEGER,
    notes                    TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_infrastructure_lagoon ON infrastructure_assets (lagoon_id);
CREATE INDEX IF NOT EXISTS ix_infrastructure_status ON infrastructure_assets (status);
CREATE INDEX IF NOT EXISTS ix_infrastructure_location
    ON infrastructure_assets USING GIST (location);


-- ---------------------------------------------------------------------------
-- LOS Events (immutable event ledger)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS los_events (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id      UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    event_type     VARCHAR(100) NOT NULL,
    loop           VARCHAR(50) NOT NULL
        CHECK (loop IN ('hydrological','chemical','ecological','infrastructure','decision','system')),
    source         VARCHAR(100) NOT NULL,
    priority       VARCHAR(20) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('critical','high','normal','low')),
    confidence     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    payload        JSONB NOT NULL DEFAULT '{}',
    correlation_id UUID,
    version        INTEGER NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- No updated_at: events are immutable
);

CREATE INDEX IF NOT EXISTS ix_los_events_lagoon_created
    ON los_events (lagoon_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_los_events_correlation
    ON los_events (correlation_id)
    WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_los_events_loop ON los_events (loop, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_los_events_event_type ON los_events (event_type);
CREATE INDEX IF NOT EXISTS ix_los_events_priority
    ON los_events (priority, created_at DESC)
    WHERE priority IN ('critical','high');


-- ---------------------------------------------------------------------------
-- Operating Objectives
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operating_objectives (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id       UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    objective_type  VARCHAR(100) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    target_value    DOUBLE PRECISION,
    current_value   DOUBLE PRECISION,
    unit            VARCHAR(50),
    priority        INTEGER NOT NULL DEFAULT 5
        CHECK (priority BETWEEN 1 AND 10),
    weight          DOUBLE PRECISION NOT NULL DEFAULT 1.0
        CHECK (weight BETWEEN 0.0 AND 1.0),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_operating_objectives_lagoon
    ON operating_objectives (lagoon_id);
CREATE INDEX IF NOT EXISTS ix_operating_objectives_active
    ON operating_objectives (lagoon_id, is_active)
    WHERE is_active = TRUE;


-- ---------------------------------------------------------------------------
-- Recommendations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id              UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    action                 VARCHAR(500) NOT NULL,
    action_category        VARCHAR(100) NOT NULL
        CHECK (action_category IN ('aeration','chemical_dosing','water_management','maintenance','investigation','monitoring','dredging','other')),
    scientific_reason      TEXT NOT NULL,
    contributing_loops     JSONB NOT NULL DEFAULT '[]',
    evidence               JSONB NOT NULL DEFAULT '{}',
    confidence             DOUBLE PRECISION NOT NULL DEFAULT 0.5
        CHECK (confidence BETWEEN 0.0 AND 1.0),
    priority               VARCHAR(20) NOT NULL DEFAULT 'normal'
        CHECK (priority IN ('critical','high','normal','low')),
    expected_outcome       TEXT NOT NULL,
    expected_timeframe_days INTEGER,
    alternative_options    JSONB NOT NULL DEFAULT '[]',
    operating_objective_ids JSONB NOT NULL DEFAULT '[]',
    status                 VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','implemented','cancelled','superseded')),
    created_by_system      BOOLEAN NOT NULL DEFAULT TRUE,
    approved_by            UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at            TIMESTAMPTZ,
    rejection_reason       TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_recommendations_lagoon_status
    ON recommendations (lagoon_id, status);
CREATE INDEX IF NOT EXISTS ix_recommendations_pending
    ON recommendations (lagoon_id, created_at DESC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_recommendations_priority
    ON recommendations (priority, created_at DESC)
    WHERE status = 'pending';


-- ---------------------------------------------------------------------------
-- Interventions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interventions (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id            UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    recommendation_id    UUID REFERENCES recommendations(id) ON DELETE SET NULL,
    action               VARCHAR(500) NOT NULL,
    approved_by          UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approved_at          TIMESTAMPTZ NOT NULL,
    implemented_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    implemented_at       TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    observed_outcome     TEXT,
    outcome_confidence   DOUBLE PRECISION
        CHECK (outcome_confidence IS NULL OR outcome_confidence BETWEEN 0.0 AND 1.0),
    notes                TEXT,
    status               VARCHAR(50) NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','in_progress','completed','failed','cancelled')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_interventions_lagoon ON interventions (lagoon_id);
CREATE INDEX IF NOT EXISTS ix_interventions_recommendation
    ON interventions (recommendation_id)
    WHERE recommendation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_interventions_status ON interventions (status);


-- ---------------------------------------------------------------------------
-- Scientific Model Runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scientific_model_runs (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id               UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    model_name              VARCHAR(100) NOT NULL,
    model_version           VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    input_parameters        JSONB NOT NULL DEFAULT '{}',
    output_results          JSONB NOT NULL DEFAULT '{}',
    confidence              DOUBLE PRECISION NOT NULL DEFAULT 0.5
        CHECK (confidence BETWEEN 0.0 AND 1.0),
    assumptions             JSONB NOT NULL DEFAULT '[]',
    limitations             JSONB NOT NULL DEFAULT '[]',
    execution_time_seconds  DOUBLE PRECISION,
    error_message           TEXT,
    status                  VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','cancelled')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_model_runs_lagoon_created
    ON scientific_model_runs (lagoon_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_model_runs_model_name
    ON scientific_model_runs (model_name, status);


-- ---------------------------------------------------------------------------
-- Shared Memory Entries
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared_memory_entries (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lagoon_id    UUID NOT NULL REFERENCES lagoons(id) ON DELETE CASCADE,
    memory_type  VARCHAR(50) NOT NULL,
    loop         VARCHAR(50),
    key          VARCHAR(255) NOT NULL,
    value        JSONB NOT NULL DEFAULT '{}',
    ttl_seconds  INTEGER,
    expires_at   TIMESTAMPTZ,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_shared_memory_key UNIQUE (lagoon_id, memory_type, loop, key)
);

CREATE INDEX IF NOT EXISTS ix_shared_memory_lagoon_type
    ON shared_memory_entries (lagoon_id, memory_type);
CREATE INDEX IF NOT EXISTS ix_shared_memory_expires_at
    ON shared_memory_entries (expires_at)
    WHERE expires_at IS NOT NULL;


-- ---------------------------------------------------------------------------
-- Audit Log (immutable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID,
    action        VARCHAR(200) NOT NULL,
    resource_type VARCHAR(100),
    resource_id   UUID,
    changes       JSONB NOT NULL DEFAULT '{}',
    ip_address    VARCHAR(50),
    user_agent    VARCHAR(500),
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- No FK on user_id: audit records must persist after user deletion
);

CREATE INDEX IF NOT EXISTS ix_audit_log_user_timestamp
    ON audit_log (user_id, timestamp DESC)
    WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_audit_log_resource
    ON audit_log (resource_type, resource_id)
    WHERE resource_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp ON audit_log (timestamp DESC);


-- ---------------------------------------------------------------------------
-- Row Level Security (RLS) — Multi-tenant isolation
-- ---------------------------------------------------------------------------

-- Enable RLS on all tenant-scoped tables.
ALTER TABLE lagoons ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensors ENABLE ROW LEVEL SECURITY;
ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE laboratory_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE infrastructure_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE los_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE operating_objectives ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE interventions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scientific_model_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_memory_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS (used by backend API).
-- Individual user access is enforced by the application layer using org_id.

-- Lagoons: users can only see lagoons belonging to their organisation.
CREATE POLICY lagoons_org_isolation ON lagoons
    USING (
        org_id = (
            SELECT org_id FROM users
            WHERE id = auth.uid()
        )
    );

-- Users: can see members of their own organisation.
CREATE POLICY users_org_isolation ON users
    USING (
        org_id = (
            SELECT org_id FROM users
            WHERE id = auth.uid()
        )
    );

-- Lagoon-scoped tables: derive isolation from parent lagoon's org_id.
CREATE POLICY sensors_org_isolation ON sensors
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY observations_org_isolation ON observations
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY lab_results_org_isolation ON laboratory_results
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY infrastructure_org_isolation ON infrastructure_assets
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY los_events_org_isolation ON los_events
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY objectives_org_isolation ON operating_objectives
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY recommendations_org_isolation ON recommendations
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY interventions_org_isolation ON interventions
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY model_runs_org_isolation ON scientific_model_runs
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );

CREATE POLICY shared_memory_org_isolation ON shared_memory_entries
    USING (
        lagoon_id IN (
            SELECT id FROM lagoons WHERE org_id = (
                SELECT org_id FROM users WHERE id = auth.uid()
            )
        )
    );


-- ---------------------------------------------------------------------------
-- Updated_at trigger function
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to all tables with updated_at.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'organisations', 'users', 'lagoons', 'sensors',
        'infrastructure_assets', 'operating_objectives',
        'recommendations', 'interventions', 'shared_memory_entries'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()',
            t, t
        );
    END LOOP;
END $$;


-- ---------------------------------------------------------------------------
-- Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE organisations IS 'Top-level tenant entity. All data belongs to an organisation.';
COMMENT ON TABLE lagoons IS 'Physical lagoon body. Core unit of LOS operations.';
COMMENT ON TABLE observations IS 'Immutable time-series sensor/lab observations. Never update or delete rows.';
COMMENT ON TABLE los_events IS 'Immutable event ledger for all scientific loop communications.';
COMMENT ON TABLE audit_log IS 'Immutable record of all user actions for compliance and forensics.';
COMMENT ON TABLE recommendations IS 'System-generated operational recommendations from the Decision Engine.';
COMMENT ON TABLE interventions IS 'Physical actions taken at the lagoon, linked to approved recommendations.';
COMMENT ON TABLE scientific_model_runs IS 'Record of every simulation run (FloPy, HYDRUS, PHREEQC, etc.).';
COMMENT ON TABLE shared_memory_entries IS 'Persistent shared memory for scientific loop state.';


COMMIT;
