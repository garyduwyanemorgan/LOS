# LOS Production Deployment

## Infrastructure Requirements

### Minimum (Single-Site)

| Component | Specification |
|-----------|--------------|
| Application server | 4 vCPU, 16 GB RAM |
| PostgreSQL (Supabase) | Supabase Pro or dedicated PostgreSQL 16 + PostGIS |
| Redis | Redis 7.2, 2 GB RAM minimum |
| Neo4j | Neo4j Community 5.23, 4 GB RAM |
| Reverse proxy | nginx |

### Recommended (Production)

| Component | Specification |
|-----------|--------------|
| API server | 8 vCPU, 32 GB RAM, 2+ instances behind load balancer |
| Celery workers | Separate 4 vCPU instances per queue |
| PostgreSQL | Supabase Pro (managed) |
| Redis | Azure Cache for Redis Standard |
| Neo4j | Neo4j Enterprise or AuraDB |

## Docker Compose Deployment

### 1. Prepare environment

```bash
cp .env.example .env
# Configure all required secrets — see .env.example for documentation
```

### 2. Start all services

```bash
docker compose up -d
```

### 3. Initialise database

```bash
docker compose exec backend ./deployment/scripts/init_db.sh
```

### 4. Seed Scientific Relationship Graph

```bash
docker compose exec backend python deployment/scripts/seed_srg.py
```

### 5. Verify health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Environment Variables

See `.env.example` for complete documentation of all required variables.

Critical variables:
- `SECRET_KEY` — must be 32+ characters, cryptographically random
- `JWT_SECRET_KEY` — must be 32+ characters, cryptographically random
- `DATABASE_URL` — PostgreSQL 16 with PostGIS
- `SUPABASE_*` — Supabase project credentials
- `ANTHROPIC_API_KEY` — required for AI narrative generation
- `NEO4J_PASSWORD` — Neo4j authentication

## Monitoring

### Grafana

Access: `http://localhost:3001`
Default credentials: `admin/admin` (change immediately)

Prometheus metrics endpoint: `http://backend:8000/metrics`

### Sentry

Configure `SENTRY_DSN` in `.env` for error tracking.

### Log aggregation

All services produce structured JSON logs. Ship to your preferred log aggregator.

## Scaling

### Horizontal scaling (API)

The FastAPI backend is stateless. Scale by increasing replica count:

```yaml
# docker-compose.override.yml
services:
  backend:
    deploy:
      replicas: 3
```

### Celery workers

Scale individual queues independently:

```bash
docker compose up -d --scale celery-worker=4 --scale celery-simulations=2
```

## Backup

### PostgreSQL

```bash
pg_dump -Fc $DATABASE_SYNC_URL > los_backup_$(date +%Y%m%d).dump
```

### Neo4j

```bash
docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/backups
```

### Redis

Redis Streams are not critical for disaster recovery — they are ephemeral.
Ensure `shared_memory_entries` table is included in PostgreSQL backup.
