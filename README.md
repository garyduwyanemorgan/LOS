# Lagoons Operating System (LOS)

Enterprise SaaS Environmental Operating System for lagoon management.

LOS converts scientific understanding into operational decisions through a Loop of Loops architecture: five independent scientific loops (Hydrological, Chemical, Ecological, Infrastructure, Operational) that operate continuously, exchange information through a shared event bus and memory system, and produce explainable operational recommendations.

## Architecture

```
Loop of Loops
┌─────────────────────────────────────────────────────────────┐
│  Hydrological ◄──────────────────────────► Chemical         │
│       │                                         │           │
│       ▼                                         ▼           │
│  Infrastructure ◄──────────────────────► Ecological         │
│                          │                                  │
│                    Decision Engine                          │
│                    AI Orchestrator                          │
│                    Shared Memory                            │
│                    Scientific Relationship Graph            │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 / FastAPI / SQLAlchemy async |
| Database | PostgreSQL 16 + PostGIS 3.4 (via Supabase) |
| Event Bus | Redis Streams |
| Knowledge Graph | Neo4j 5.23 |
| AI | Anthropic Claude claude-sonnet-4-6 / LangGraph |
| Scientific Models | FloPy/MODFLOW 6, PhreeqPy/PHREEQC, Phydrus/HYDRUS-1D |
| Frontend | React 18 / TypeScript / Vite / TailwindCSS |
| Background Workers | Celery |
| Monitoring | Prometheus / Grafana / Sentry |
| Deployment | Docker / GitHub Actions / Azure |

## Quick Start

### Prerequisites

- Docker 24+
- Docker Compose 2.20+

### 1. Clone and configure

```bash
git clone <repository-url>
cd LOS
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start services

```bash
docker compose up -d
```

### 3. Initialise database

```bash
./deployment/scripts/init_db.sh
```

### 4. Seed the Scientific Relationship Graph

```bash
docker compose exec backend python deployment/scripts/seed_srg.py
```

### 5. Access

| Service | URL |
|---------|-----|
| LOS Frontend | http://localhost:3000 |
| API Documentation | http://localhost:8000/api/docs |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

## Development

### Backend

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
mypy backend/

# Lint
ruff check backend/
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Project Structure

```
LOS/
├── backend/
│   ├── api/v1/              # REST API routers
│   ├── core/                # Config, logging, security
│   ├── database/            # SQLAlchemy models, repositories, migrations
│   ├── decision_engine/     # Multi-objective decision engine + AI orchestrator
│   ├── event_bus/           # Redis Streams event bus
│   ├── scientific_models/   # MODFLOW, PHREEQC, HYDRUS wrappers + pure-Python models
│   ├── scientific_relationship_graph/  # Neo4j cause-effect reasoning network
│   ├── scientific_services/ # Five scientific loops
│   ├── shared_memory/       # Redis + PostgreSQL two-tier memory
│   └── workers/             # Celery tasks
├── frontend/
│   └── src/
│       ├── components/      # Shared + chart components
│       ├── hooks/           # React Query hooks
│       ├── pages/           # Route-level pages
│       ├── stores/          # Zustand state stores
│       └── lib/             # API client, WebSocket, utilities
├── tests/
│   ├── unit/                # Fast unit tests (no external services)
│   ├── integration/         # Database + Redis integration tests
│   ├── api/                 # HTTP API tests
│   └── scientific_validation/  # End-to-end scenario tests
├── deployment/
│   ├── docker/              # Docker infrastructure configs
│   └── scripts/             # Init and seed scripts
└── .github/workflows/       # CI/CD pipeline
```

## Operating Objectives

LOS optimises against 7 configurable strategic objectives:

1. **Protect the Lagoon** — structural integrity, water balance, infrastructure reliability
2. **Improve Water Quality** — DO, nutrients, pH, ORP, salinity within target bounds
3. **Maintain Ecological Stability** — algal balance, bloom prevention, biodiversity
4. **Reduce Operational Cost** — energy, maintenance, chemical usage optimisation
5. **Regulatory Compliance** — water quality standards, permit conditions, reporting
6. **Improve Scientific Confidence** — prediction accuracy, model performance, learning
7. **Continuous Improvement** — measurable lagoon performance improvement over time

Each recommendation is scored against all 7 objectives using configurable per-lagoon weights.

## Security

- RBAC with 6 roles: SUPERADMIN, ADMIN, ENGINEER, SCIENTIST, OPERATOR, VIEWER
- Row-Level Security on all PostgreSQL tables (multi-tenancy)
- JWT authentication via Supabase Auth
- Full audit log for every recommendation and intervention

## License

Proprietary. All rights reserved.
