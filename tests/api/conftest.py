"""API test configuration — sets required env vars before settings load."""
from __future__ import annotations

import os

# Must be set before backend modules are imported so Pydantic settings validation passes.
_TEST_ENV = {
    "SECRET_KEY": "test-secret-key-for-api-tests-do-not-use-in-production",
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-api-tests-do-not-use-in-production",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_los",
    "DATABASE_SYNC_URL": "postgresql://test:test@localhost:5432/test_los",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "test-password",
    "NEO4J_DATABASE": "neo4j",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret",
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-api-tests-do-not-use-in-production",
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "SENTRY_DSN": "",
    "LOS_ENVIRONMENT": "test",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
