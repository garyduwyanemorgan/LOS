#!/bin/bash
# Initialise the LOS PostgreSQL database.
# Run once after first docker-compose up.
# Requires: psql available, DATABASE_URL set in environment.

set -euo pipefail

echo "==> LOS Database Initialisation"
echo "    Target: ${DATABASE_URL:-not set}"

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL environment variable not set."
    exit 1
fi

# Wait for PostgreSQL to be ready
echo "==> Waiting for PostgreSQL..."
until psql "$DATABASE_URL" -c "SELECT 1" >/dev/null 2>&1; do
    echo "    PostgreSQL not ready — retrying in 2s..."
    sleep 2
done
echo "    PostgreSQL is ready."

# Enable PostGIS extension
echo "==> Enabling PostGIS extension..."
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis_topology;"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"

# Run initial schema migration
echo "==> Applying initial schema..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_FILE="$SCRIPT_DIR/../../backend/database/migrations/001_initial_schema.sql"

if [ -f "$MIGRATION_FILE" ]; then
    psql "$DATABASE_URL" -f "$MIGRATION_FILE"
    echo "    Schema migration applied successfully."
else
    echo "    WARNING: Migration file not found at $MIGRATION_FILE"
    echo "    Running Alembic migrations instead..."
    cd /app && alembic upgrade head
fi

echo "==> Database initialisation complete."
