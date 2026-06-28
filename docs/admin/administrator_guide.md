# Lagoons Operating System — Administrator Guide

Version: 1.0 | Audience: System Administrators and DevOps Engineers

---

## Overview

This guide covers installation, configuration, user management, monitoring, backup, and troubleshooting for the Lagoons Operating System (LOS).

For deployment architecture and Docker Compose setup, refer to `docs/deployment/production.md`.  
For API reference, refer to `docs/api/reference.md`.

---

## 1. System Requirements

### Minimum Infrastructure

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 16 GB | 32 GB |
| Storage | 100 GB SSD | 500 GB NVMe |
| Network | 100 Mbps | 1 Gbps |

### Required External Services

| Service | Version | Purpose |
|---------|---------|---------|
| PostgreSQL | 16+ (via Supabase) | Primary database + PostGIS |
| Redis | 7.2+ | Event bus, shared memory, Celery broker |
| Neo4j | 5.23+ | Scientific Relationship Graph |

### Optional External Services

| Service | Purpose |
|---------|---------|
| Sentry | Error tracking |
| Prometheus + Grafana | Metrics and dashboards |
| S3 / Supabase Storage | Model file and report storage |

---

## 2. Installation

### Step 1: Clone and Configure

```bash
git clone <repository-url> /opt/los
cd /opt/los
cp .env.example .env
```

Edit `.env` and populate all required values. See Section 3 for configuration reference.

### Step 2: Build and Start

```bash
docker compose build
docker compose up -d
```

### Step 3: Apply Database Migrations

```bash
docker compose exec api alembic upgrade head
```

### Step 4: Verify Startup

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Both should return HTTP 200. The `/ready` endpoint checks PostgreSQL, Redis, and Neo4j connectivity.

---

## 3. Configuration Reference

All configuration is via environment variables. See `.env.example` for the full list with descriptions.

### Required Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Application signing key (≥32 chars, random hex) |
| `DATABASE_URL` | PostgreSQL connection: `postgresql+asyncpg://user:pass@host:5432/db` |
| `JWT_SECRET_KEY` | JWT signing key (≥32 chars, different from SECRET_KEY) |
| `NEO4J_PASSWORD` | Neo4j database password |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (keep secret) |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (from project settings) |
| `ANTHROPIC_API_KEY` | Claude API key for AI narrative generation |

### Key Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LOG_FORMAT` | `json` | `json` for structured logging, `console` for development |
| `SENTRY_DSN` | (empty) | Sentry error tracking DSN |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins |
| `ENVIRONMENT` | `production` | `development`, `staging`, or `production` |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_WEBSOCKETS` | `true` | Real-time dashboard updates |
| `ENABLE_AUTO_APPROVE_RECOMMENDATIONS` | `false` | NEVER enable in production |
| `ENABLE_VADOSE_SIMULATION` | `true` | HYDRUS-1D vadose zone modelling |
| `ENABLE_FLOW_SIMULATION` | `true` | MODFLOW groundwater flow modelling |
| `ENABLE_GEOCHEM_SIMULATION` | `true` | PHREEQC geochemical modelling |

---

## 4. User Management

### User Roles

| Role | Capabilities |
|------|-------------|
| `admin` | Full system access, user management, configuration |
| `manager` | All operator capabilities plus report generation and multi-lagoon view |
| `operator` | View dashboards, add observations, approve/decline recommendations, generate reports |
| `viewer` | Read-only access to dashboards and reports |

### Creating a User

User accounts are managed through Supabase authentication. To create a new user:

1. Log into the Supabase dashboard for your project
2. Navigate to **Authentication → Users**
3. Click **Invite User** and enter the email address
4. Once the user accepts the invitation, assign their role via the LOS admin panel

Alternatively, use the LOS admin API:

```bash
curl -X POST https://your-los-domain/api/v1/admin/users \
  -H "Authorization: Bearer <admin-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "operator@example.com", "role": "operator", "lagoon_ids": ["<lagoon-uuid>"]}'
```

### Assigning Lagoon Access

Users can only access lagoons they are explicitly assigned to. Assign lagoons via:
- LOS admin panel: **Admin → Users → Edit User → Lagoon Access**
- LOS admin API: `PUT /api/v1/admin/users/{user_id}/lagoons`

### Deactivating a User

1. In the LOS admin panel, navigate to **Admin → Users**
2. Select the user and click **Deactivate**
3. Deactivated users cannot log in but their audit history is preserved

---

## 5. Lagoon Configuration

### Creating a New Lagoon

```bash
curl -X POST https://your-los-domain/api/v1/lagoons \
  -H "Authorization: Bearer <admin-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Marina West Lagoon",
    "slug": "marina-west",
    "location": {"lat": 25.076, "lng": 55.134, "country": "UAE", "city": "Dubai"},
    "volume_m3": 125000,
    "surface_area_m2": 62500,
    "max_depth_m": 3.2
  }'
```

### Configuring Sensors

Sensors are registered per lagoon and linked to specific parameters. Contact the integration team to configure sensor ingestion pipelines.

### Setting Permit Thresholds

Compliance thresholds (DO, TP, TN, etc.) are configured per lagoon in the admin panel under **Admin → Lagoons → {Lagoon Name} → Compliance Thresholds**.

---

## 6. Monitoring

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe — API process alive |
| `GET /ready` | Readiness probe — all dependencies connected |
| `GET /metrics` | Prometheus metrics |

### Prometheus Metrics

Key metrics to monitor:

| Metric | Description |
|--------|-------------|
| `los_decision_cycles_total` | Decision Engine cycles run |
| `los_recommendations_generated_total` | Recommendations produced |
| `los_event_bus_published_total` | Events published to bus |
| `los_shared_memory_operations_total` | Shared memory read/write ops |
| `http_request_duration_seconds` | API latency histogram |

### Grafana Dashboard

Import the LOS Grafana dashboard from `docs/monitoring/grafana_dashboard.json`.

Key panels to configure:
- API P95 latency (target: < 200ms)
- Decision Engine cycle duration (target: < 500ms)
- Active alert count per lagoon
- Event bus publish rate
- Redis memory usage

### Alerting Rules

Configure Prometheus alerts for:
- `los_api_error_rate > 0.01` — more than 1% API errors
- `los_decision_engine_lag > 3600` — Decision Engine has not run in 1 hour
- `los_redis_connected == 0` — Redis connection lost
- `los_neo4j_connected == 0` — Neo4j connection lost

---

## 7. Backup and Recovery

### Database Backup

PostgreSQL (Supabase):
- Supabase performs automated daily backups (Pro plan and above)
- Point-in-time recovery is available on Pro plan
- Download a manual backup: Supabase dashboard → **Database → Backups**

For self-hosted PostgreSQL:
```bash
pg_dump -h localhost -U postgres los_db > los_backup_$(date +%Y%m%d).sql
```

### Redis Backup

Redis data is ephemeral by design — event streams have a configurable replay window. Configure Redis persistence if you require event replay beyond the TTL:

```
# redis.conf
appendonly yes
appendfsync everysec
```

### Neo4j Backup

```bash
docker compose exec neo4j neo4j-admin database dump --to-path=/backups neo4j
```

### Model File Backup

If using local storage for simulation model files:
```bash
tar -czf los_models_$(date +%Y%m%d).tar.gz /data/los/storage/
```

### Disaster Recovery

To restore from backup:

1. Restore PostgreSQL: `psql -h localhost -U postgres los_db < los_backup_YYYYMMDD.sql`
2. Apply any missing migrations: `docker compose exec api alembic upgrade head`
3. Restore Neo4j: `docker compose exec neo4j neo4j-admin database load --from-path=/backups neo4j`
4. Restart all services: `docker compose restart`
5. Verify: `curl /ready`

---

## 8. Scaling

### Horizontal API Scaling

The API is stateless. Add additional API containers:
```yaml
# docker-compose.override.yml
services:
  api:
    deploy:
      replicas: 3
```

Place a load balancer (nginx, Traefik, or AWS ALB) in front of the API instances.

### Celery Worker Scaling

Add more worker containers to increase background task throughput:
```bash
docker compose up -d --scale celery_worker=4
```

### Redis Scaling

For high-throughput event processing, configure Redis Sentinel (high availability) or Redis Cluster (horizontal scaling). Update `REDIS_URL` accordingly.

---

## 9. SSL/TLS Configuration

LOS itself does not terminate TLS — configure TLS at the reverse proxy layer (nginx, Traefik, or a cloud load balancer).

Example nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name los.yourdomain.com;

    ssl_certificate /etc/ssl/certs/los.crt;
    ssl_certificate_key /etc/ssl/private/los.key;

    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 10. Audit Log

LOS logs every state-changing API call (POST, PUT, PATCH, DELETE) to the structured audit log. Audit records include:

- Request ID and correlation ID
- User ID and email
- HTTP method and path
- Response status code
- Request duration
- Client IP address
- Request body preview (first 4KB)

Audit logs are emitted to the `los.audit` structured logger and can be shipped to your SIEM via log aggregation (Fluentd, Vector, or equivalent).

To search audit logs:
```bash
docker compose logs api | jq 'select(.logger == "los.audit")'
```

---

## 11. Rate Limiting

The API enforces per-user/per-IP sliding-window rate limits:

| Endpoint Group | Limit |
|----------------|-------|
| Authentication (`/api/v1/auth/*`) | 20 requests / 60 seconds |
| Report generation (POST `*/reports`) | 10 requests / 60 seconds |
| All other API endpoints | 200 requests / 60 seconds |

Rate limit status is returned in response headers:
- `X-RateLimit-Limit`: The limit for this endpoint group
- `X-RateLimit-Remaining`: Remaining requests in the current window
- `X-RateLimit-Reset`: Unix timestamp when the window resets

When the limit is exceeded, the API returns HTTP 429 with a `Retry-After` header.

Rate limiting is backed by Redis. If Redis is unavailable, rate limiting is disabled and all requests pass through.

---

## 12. Troubleshooting

### API returns 503 on /ready

Check which dependency is unhealthy:
```bash
curl https://your-los-domain/ready | jq '.checks'
```

Common causes:
- PostgreSQL connection failure: Check `DATABASE_URL` and network connectivity
- Redis connection failure: Check `REDIS_URL` and that Redis is running
- Neo4j connection failure: Check `NEO4J_URI`, `NEO4J_PASSWORD`, and that Neo4j is running

### Decision Engine not generating recommendations

1. Check that scientific services are publishing state: `docker compose logs scientific_worker`
2. Check Redis is receiving events: `redis-cli XLEN los:events:medium`
3. Check Decision Engine cycles: `docker compose logs celery_worker | grep decision`

### High API latency

1. Check database query performance: `docker compose logs api | grep duration_ms | jq '. | select(.duration_ms > 1000)'`
2. Check Redis latency: `redis-cli --latency`
3. Scale API replicas if CPU-bound: `docker compose up -d --scale api=3`

### Missing sensor data / low confidence

1. Verify sensor ingestion pipeline is running
2. Check for sensor quality flag issues in observations
3. Review the hydrological or chemical loop confidence scores for each lagoon
4. Add manual observations to supplement missing sensor data

### Neo4j SRG not seeding

```bash
docker compose exec api python -c "
import asyncio
from backend.scientific_relationship_graph.seed_data import seed_srg
from backend.scientific_relationship_graph.service import ScientificRelationshipGraph
# See docs/developer/getting_started.md for full seed procedure
"
```

---

## 13. Log Management

LOS emits structured JSON logs to stdout. Configure your container runtime to ship logs to your centralised logging platform:

- **CloudWatch Logs**: Use the `awslogs` Docker log driver
- **Elasticsearch**: Use Fluentd with the `fluent/fluentd` container
- **Loki**: Use the `grafana/promtail` agent

Set `LOG_LEVEL=DEBUG` temporarily for detailed troubleshooting. Always revert to `LOG_LEVEL=INFO` in production to avoid PII exposure in logs.
