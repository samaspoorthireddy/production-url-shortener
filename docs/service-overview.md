# URL Shortener — Service Overview

> **Audience**: On-call engineers, new team members, and incident responders.  
> **Last updated**: 2026-06-04  
> **Owner**: Platform Engineering

---

## Purpose

The URL Shortener is a FastAPI-based HTTP service that creates short redirect codes for long URLs, tracks click analytics, and enforces per-link lifecycle policies (expiry, click caps, API key access control). It is the primary redirect path for end users and must maintain high availability because every outage directly blocks user navigation.

---

## Dependencies

| Dependency | Role | What happens without it |
|---|---|---|
| **PostgreSQL** | Primary data store — links, analytics, webhooks | Writes fail with 503; cached redirects still work via Redis for up to TTL seconds |
| **Redis** | Read-through redirect cache + job deduplication | Cache misses fall back to PostgreSQL; if both fail, all redirects return 503 |
| **Celery Worker** | Async analytics event processing (click counts, timeseries) | Click analytics stop recording; redirects still succeed |
| **RabbitMQ / Redis broker** | Celery task queue | Same impact as Celery Worker going down |

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe — returns `{"status": "ok"}` |
| `GET` | `/ready` | Readiness probe — checks DB + Redis connectivity |
| `GET` | `/metrics` | Prometheus metrics endpoint |
| `GET` | `/r/{code}` | **Core redirect** — resolve short code to long URL |
| `POST` | `/v1/links/` | Create a new short link |
| `GET` | `/v1/links/` | List all links (paginated) |
| `GET` | `/v1/links/{link_id}` | Get single link details |
| `PATCH` | `/v1/links/{link_id}` | Update a link |
| `DELETE` | `/v1/links/{link_id}` | Delete a link |
| `POST` | `/v1/links/bulk` | Bulk create links |
| `GET` | `/v1/links/{link_id}/analytics` | Click analytics for a link |
| `GET` | `/v1/links/analytics/summary` | Aggregate analytics summary |
| `POST` | `/v1/webhooks/` | Register a webhook |
| `GET` | `/v1/webhooks/` | List webhooks |
| `DELETE` | `/v1/webhooks/` | Delete a webhook |

---

## Configuration Reference

All configuration is injected as environment variables. The service **refuses to start** if required variables are missing.

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | ✅ | — | `development` \| `staging` \| `production` |
| `PORT` | ✅ | — | TCP port the uvicorn server binds to (e.g. `8000`) |
| `DATABASE_URL` | ✅ | — | PostgreSQL DSN — `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | ✅ | — | Redis DSN — `redis://host:6379/0` |
| `JWT_SECRET` | ✅ | — | HMAC secret for API key signing |
| `CORS_ORIGIN` | ✅ | — | Allowed CORS origin (e.g. `https://app.example.com`) |
| `LOG_LEVEL` | ❌ | `info` | Logging verbosity: `debug` \| `info` \| `warning` \| `error` |

---

## Deploy Commands

```bash
# 1. Pull the latest image
docker pull ghcr.io/yourorg/url-shortener:latest

# 2. Run database migrations (always before deploying new containers)
docker run --rm \
  --env-file .env.production \
  ghcr.io/yourorg/url-shortener:latest \
  alembic upgrade head

# 3. Start the service container
docker run -d \
  --name url-shortener-prod \
  --env-file .env.production \
  -p 8000:8000 \
  ghcr.io/yourorg/url-shortener:latest

# 4. Verify liveness
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}

# 5. Verify readiness (DB + Redis)
curl -s http://localhost:8000/ready
# Expected: {"status":"ready","database":"ok","redis":"ok"}
```

---

## Rollback Commands

```bash
# 1. Stop the current container
docker stop url-shortener-prod

# 2. Remove the current container
docker rm url-shortener-prod

# 3. Start the previous known-good image (replace TAG with the last stable tag)
docker run -d \
  --name url-shortener-prod \
  --env-file .env.production \
  -p 8000:8000 \
  ghcr.io/yourorg/url-shortener:TAG

# 4. Verify recovery
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}

# 5. If migration rollback is also needed:
docker run --rm \
  --env-file .env.production \
  ghcr.io/yourorg/url-shortener:TAG \
  alembic downgrade -1
```

---

## Ownership & Escalation

| Role | Name | Contact | When to page |
|---|---|---|---|
| **Primary On-Call** | Rotation (see PagerDuty) | PagerDuty: `url-shortener-oncall` | Any 5xx error rate > 1% for > 2 min |
| **Service Owner** | Platform Engineering Lead | Slack: `#platform-eng` | Sustained outage > 10 min |
| **Database Admin** | DBA Team | PagerDuty: `dba-oncall` | PostgreSQL connection failures not resolving in 5 min |
| **Infra / Redis** | Infrastructure Team | PagerDuty: `infra-oncall` | Redis failures not resolving in 5 min |
