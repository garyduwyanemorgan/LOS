# LOS API Reference

Base URL: `/api/v1`

Interactive documentation (development only): `http://localhost:8000/api/docs`

## Authentication

All endpoints require a valid JWT Bearer token in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are issued via the `/api/v1/auth/login` endpoint or Supabase Auth.

## Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Issue JWT access + refresh token |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Invalidate tokens |
| GET | `/auth/me` | Current user profile |

### Lagoons

| Method | Path | Description |
|--------|------|-------------|
| GET | `/lagoons` | List all lagoons (org-scoped) |
| POST | `/lagoons` | Create lagoon |
| GET | `/lagoons/{id}` | Get lagoon details |
| PATCH | `/lagoons/{id}` | Update lagoon |
| DELETE | `/lagoons/{id}` | Archive lagoon |
| GET | `/lagoons/{id}/status` | Current system state (all loops) |
| GET | `/lagoons/{id}/objectives` | Operating objectives |
| PUT | `/lagoons/{id}/objectives` | Update objective weights |

### Observations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/observations` | Query observations with filters |
| POST | `/observations` | Ingest a single observation |
| POST | `/observations/batch` | Ingest batch of observations |
| GET | `/observations/{id}` | Get specific observation |
| GET | `/lagoons/{id}/observations/recent` | Recent observations for a lagoon |
| GET | `/lagoons/{id}/observations/stats` | Statistical summary |

### Recommendations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/recommendations` | List recommendations |
| GET | `/recommendations/{id}` | Get recommendation with full explanation |
| POST | `/recommendations/{id}/approve` | Approve a recommendation |
| POST | `/recommendations/{id}/reject` | Reject a recommendation |
| POST | `/recommendations/trigger` | Manually trigger decision cycle |

### Interventions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/interventions` | List interventions |
| POST | `/interventions` | Record a manual intervention |
| GET | `/interventions/{id}` | Get intervention details |
| PATCH | `/interventions/{id}` | Update intervention status |
| POST | `/interventions/{id}/complete` | Mark intervention complete |
| POST | `/interventions/{id}/outcome` | Record measured outcome |

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events` | Query event history |
| GET | `/lagoons/{id}/events` | Events for a specific lagoon |

### Simulations

| Method | Path | Description |
|--------|------|-------------|
| POST | `/simulations/predict` | Run predictive simulation |
| GET | `/simulations/{id}` | Get simulation results |
| GET | `/simulations/{id}/status` | Check simulation status |

### Reports

| Method | Path | Description |
|--------|------|-------------|
| GET | `/reports` | List reports |
| POST | `/reports/generate` | Generate a new report |
| GET | `/reports/{id}` | Get report |
| GET | `/reports/{id}/download` | Download report file |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | API liveness (no auth) |
| GET | `/ready` | Readiness probe (no auth) |
| GET | `/metrics` | Prometheus metrics (no auth) |
| GET | `/api/v1/health/detailed` | Detailed health status (auth required) |

## WebSocket

| Path | Description |
|------|-------------|
| `/api/v1/ws/lagoon/{lagoon_id}` | Real-time event stream for a lagoon |
| `/api/v1/ws/system` | System-wide events (admin) |

## Response Format

All responses use consistent JSON envelopes:

```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2026-06-26T10:00:00Z",
    "request_id": "uuid"
  }
}
```

Error responses:

```json
{
  "error": "error-code",
  "message": "Human readable message",
  "detail": { ... }
}
```

## Common Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Validation error |
| 401 | Unauthenticated |
| 403 | Forbidden (insufficient role) |
| 404 | Not found |
| 422 | Unprocessable entity |
| 503 | Service unavailable |
