# Getting Started — LOS Developer Guide

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Node.js | 20+ |
| Docker | 24+ |
| Docker Compose | 2.20+ |

## Local Development Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd LOS
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials. Required secrets:
- `SECRET_KEY` — 32+ character random string
- `JWT_SECRET_KEY` — 32+ character random string
- `DATABASE_URL` — PostgreSQL connection string
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
- `NEO4J_PASSWORD`

### 3. Start infrastructure services

```bash
docker compose up -d postgres redis neo4j
```

### 4. Backend setup

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# or: .venv\Scripts\activate   # Windows

pip install -e ".[dev]"
```

### 5. Initialise database

```bash
make init-db
# or: ./deployment/scripts/init_db.sh
```

### 6. Seed the Scientific Relationship Graph

```bash
python deployment/scripts/seed_srg.py
```

### 7. Run the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

API documentation: http://localhost:8000/api/docs

### 8. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (no external services required)
pytest tests/unit/ -v

# Scientific validation scenarios
pytest tests/scientific_validation/ -v

# With coverage
pytest tests/ --cov=backend --cov-report=html
open htmlcov/index.html
```

## Code Standards

- **Type hints** required on all public functions
- **Ruff** for linting: `ruff check backend/`
- **MyPy** for type checking: `mypy backend/`
- **No hardcoded paths** — use `pathlib.Path`
- **No print statements** — use `logging` module
- **Config via YAML/ENV** — never hardcoded parameters

## Adding a New Scientific Service

1. Create directory: `backend/scientific_services/<name>/`
2. Implement `__init__.py`, `calculations.py`, `models.py`, `service.py`
3. Service must inherit `ScientificService` base class
4. Expose: `start()`, `stop()`, `compute_state()`, `publish_state()`, `process_event()`
5. Register in `backend/main.py` lifespan if it runs continuously
6. Add tests in `tests/unit/scientific_services/test_<name>_calculations.py`

## Module Interface Contract

Every scientific service module must implement:

```python
class MyService(ScientificService):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def compute_state(self, lagoon_id: UUID) -> dict[str, Any]: ...
    async def publish_state(self, lagoon_id: UUID) -> None: ...
    async def process_event(self, event: dict[str, Any]) -> None: ...
```

## Useful Make Commands

```bash
make up          # Start all Docker services
make down        # Stop all services
make test        # Run full test suite
make lint        # Run ruff + mypy
make logs        # Follow service logs
make seed        # Seed SRG with baseline relationships
make neo4j-seed  # Seed Neo4j only
```
