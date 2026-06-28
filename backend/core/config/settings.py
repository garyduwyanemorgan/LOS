"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised, validated application configuration.

    All values are read from environment variables.  Defaults are provided
    only where a sensible non-secret default exists.  Required secrets have
    no default and will raise a validation error at startup if missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "Lagoons Operating System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = Field(default="production", pattern="^(development|staging|production)$")
    SECRET_KEY: str = Field(min_length=32)

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host:port/db
    DATABASE_SYNC_URL: str | None = None  # postgresql://... for sync ops
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=5)
    DATABASE_POOL_RECYCLE: int = Field(default=3600, ge=300)

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = Field(default=10, ge=1, le=100)

    # ── Neo4j (Scientific Relationship Graph) ────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = Field(default=50, ge=5)
    NEO4J_CONNECTION_TIMEOUT: float = Field(default=30.0, ge=5.0)

    # ── Supabase ─────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # ── JWT (LOS-internal) ───────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)

    # ── AI / LLM ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    AI_MODEL: str = "claude-sonnet-4-6"
    AI_MAX_TOKENS: int = Field(default=8192, ge=256, le=200000)
    AI_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)

    # ── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_ALWAYS_EAGER: bool = False  # set True in tests
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # ── Observability ────────────────────────────────────────────────────────
    SENTRY_DSN: str | None = None
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    LOG_FORMAT: str = Field(default="json", pattern="^(json|console)$")
    METRICS_PORT: int = Field(default=9090, ge=1024, le=65535)

    # ── Scientific Loop Intervals ─────────────────────────────────────────────
    SCIENTIFIC_LOOP_INTERVAL_MINUTES: int = Field(default=15, ge=1, le=1440)
    DECISION_ENGINE_INTERVAL_MINUTES: int = Field(default=60, ge=5, le=1440)
    LEARNING_CYCLE_INTERVAL_HOURS: int = Field(default=6, ge=1, le=168)

    # ── Feature Flags ────────────────────────────────────────────────────────
    ENABLE_WEBSOCKETS: bool = True
    ENABLE_AUTO_APPROVE_RECOMMENDATIONS: bool = False
    ENABLE_VADOSE_SIMULATION: bool = True
    ENABLE_FLOW_SIMULATION: bool = True
    ENABLE_GEOCHEM_SIMULATION: bool = True

    # ── Simulation Engine Executables ────────────────────────────────────────
    MODFLOW_EXECUTABLE: str = "mf6"
    HYDRUS_EXECUTABLE: str = "hydrus1d"
    PHREEQC_EXECUTABLE: str = "phreeqc"
    PEST_EXECUTABLE: str = "pestpp-ies"

    # ── Storage ───────────────────────────────────────────────────────────────
    STORAGE_BACKEND: str = Field(default="local", pattern="^(local|s3|supabase-storage)$")
    STORAGE_LOCAL_PATH: str = "/data/los/storage"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_S3_BUCKET: str | None = None
    AWS_S3_REGION: str = "us-east-1"

    # ── Computed properties ──────────────────────────────────────────────────
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def api_prefix(self) -> str:
        return "/api/v1"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql+asyncpg://", "postgresql://", "sqlite")):
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg:// driver for async operation"
            )
        return v

    @model_validator(mode="after")
    def validate_ai_keys(self) -> Settings:
        if not self.ANTHROPIC_API_KEY and not self.OPENAI_API_KEY:
            raise ValueError(
                "At least one AI API key must be set: ANTHROPIC_API_KEY or OPENAI_API_KEY"
            )
        return self

    @model_validator(mode="after")
    def set_sync_url_from_async(self) -> Settings:
        """Derive sync DATABASE_SYNC_URL from DATABASE_URL if not explicitly set."""
        if self.DATABASE_SYNC_URL is None:
            self.DATABASE_SYNC_URL = self.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
        return self


# Singleton instance — import this everywhere.
settings = Settings()
