# ============================================================
# Lagoons Operating System — Developer Makefile
# Usage: make <target>
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# --- Project settings ---
APP_NAME        := los
BACKEND_DIR     := backend
DOCKER_COMPOSE  := docker compose
PYTHON          := python3
PIP             := pip3
ALEMBIC         := alembic
PYTEST          := pytest
BLACK           := black
RUFF            := ruff
MYPY            := mypy

# Colours
CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

.PHONY: help up down restart test test-fast lint format type-check \
        migrate migrate-down migrate-history seed logs shell \
        build clean install dev-install neo4j-seed srg-seed \
        generate-migration check-env

## ─── Docker ──────────────────────────────────────────────────────────────────

up:  ## Start all services (PostgreSQL, Redis, Neo4j, API)
	@echo -e "$(CYAN)Starting LOS services...$(RESET)"
	$(DOCKER_COMPOSE) up -d
	@echo -e "$(GREEN)Services up. API → http://localhost:8000/api/docs$(RESET)"

down:  ## Stop and remove all containers
	@echo -e "$(CYAN)Stopping LOS services...$(RESET)"
	$(DOCKER_COMPOSE) down

restart:  ## Restart all containers
	$(DOCKER_COMPOSE) restart

build:  ## Build Docker images (no cache)
	$(DOCKER_COMPOSE) build --no-cache

logs:  ## Tail logs for all services (Ctrl+C to exit)
	$(DOCKER_COMPOSE) logs -f

logs-api:  ## Tail API logs only
	$(DOCKER_COMPOSE) logs -f api

## ─── Development setup ───────────────────────────────────────────────────────

install:  ## Install production dependencies
	$(PIP) install -e .

dev-install:  ## Install all dev dependencies (including test, lint tools)
	$(PIP) install -e ".[dev]"
	pre-commit install

check-env:  ## Verify required environment variables are set
	@$(PYTHON) -c "from backend.core.config.settings import settings; print('Settings loaded OK')"

## ─── Testing ─────────────────────────────────────────────────────────────────

test:  ## Run the full test suite with coverage
	@echo -e "$(CYAN)Running test suite...$(RESET)"
	$(PYTEST) tests/ -v --cov=$(BACKEND_DIR) --cov-report=term-missing --cov-report=html

test-fast:  ## Run tests without coverage (faster feedback)
	$(PYTEST) tests/ -v --no-cov -x

test-unit:  ## Run only unit tests
	$(PYTEST) tests/unit/ -v --no-cov

test-integration:  ## Run only integration tests (requires running services)
	$(PYTEST) tests/integration/ -v --no-cov

test-file:  ## Run a specific test file: make test-file FILE=tests/test_foo.py
	$(PYTEST) $(FILE) -v --no-cov

## ─── Code quality ────────────────────────────────────────────────────────────

lint:  ## Run ruff linter (auto-fix safe issues)
	@echo -e "$(CYAN)Running ruff...$(RESET)"
	$(RUFF) check $(BACKEND_DIR) --fix
	@echo -e "$(GREEN)Lint complete.$(RESET)"

format:  ## Format code with black
	@echo -e "$(CYAN)Formatting with black...$(RESET)"
	$(BLACK) $(BACKEND_DIR) tests/
	$(RUFF) check $(BACKEND_DIR) --fix --select I
	@echo -e "$(GREEN)Formatting complete.$(RESET)"

type-check:  ## Run mypy static type checking
	@echo -e "$(CYAN)Running mypy...$(RESET)"
	$(MYPY) $(BACKEND_DIR)/
	@echo -e "$(GREEN)Type checking complete.$(RESET)"

## ─── Database ────────────────────────────────────────────────────────────────

migrate:  ## Apply all pending Alembic migrations
	@echo -e "$(CYAN)Running migrations...$(RESET)"
	$(ALEMBIC) upgrade head
	@echo -e "$(GREEN)Migrations complete.$(RESET)"

migrate-down:  ## Roll back the last migration
	$(ALEMBIC) downgrade -1

migrate-history:  ## Show migration history
	$(ALEMBIC) history --verbose

generate-migration:  ## Auto-generate a migration from model changes: make generate-migration MSG="add foo"
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

## ─── Data seeding ────────────────────────────────────────────────────────────

seed:  ## Seed all databases (PostgreSQL + Neo4j SRG)
	@echo -e "$(CYAN)Seeding databases...$(RESET)"
	$(PYTHON) -m backend.database.seed
	$(PYTHON) -m backend.scientific_relationship_graph.seed_data
	@echo -e "$(GREEN)Seeding complete.$(RESET)"

neo4j-seed:  ## Seed Neo4j Scientific Relationship Graph only
	$(PYTHON) -m backend.scientific_relationship_graph.seed_data

## ─── Interactive shell ───────────────────────────────────────────────────────

shell:  ## Open IPython REPL with LOS context pre-loaded
	$(PYTHON) -c "\
import asyncio; \
from backend.core.config.settings import settings; \
from backend.database.connection import AsyncSessionLocal; \
print('LOS shell ready. Use: asyncio.run(coroutine)'); \
import IPython; IPython.start_ipython()"

shell-db:  ## Open psql connected to the LOS database
	$(DOCKER_COMPOSE) exec postgres psql -U postgres -d los_db

shell-redis:  ## Open redis-cli
	$(DOCKER_COMPOSE) exec redis redis-cli

shell-neo4j:  ## Open Cypher shell for Neo4j
	$(DOCKER_COMPOSE) exec neo4j cypher-shell -u neo4j

## ─── Utilities ───────────────────────────────────────────────────────────────

clean:  ## Remove compiled Python files and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	@echo -e "$(GREEN)Clean complete.$(RESET)"

## ─── Help ────────────────────────────────────────────────────────────────────

help:  ## Show this help message
	@echo ""
	@echo "  Lagoons Operating System — Developer Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-22s$(RESET) %s\n", $$1, $$2}'
	@echo ""
