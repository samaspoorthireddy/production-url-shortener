# Production-Grade URL Shortener & Collaborative Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15.0-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0-DC382D.svg)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-224%20Passing-brightgreen.svg)]()

An enterprise-ready **URL Shortener and Analytics Engine** designed for high-concurrency redirection with sub-millisecond latency, asynchronous click telemetry processing, real-time WebSocket activity feeds, and granular Role-Based Access Control (RBAC).

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    Client[Client / User Agent] -->|1. Request /r/{code}| API[FastAPI Application Gateway]
    API -->|2. Check Cache| Redis[(Redis Cache)]
    Redis -- Cache Hit -->|3a. Sub-ms Redirect| Client
    Redis -- Cache Miss -->|3b. Query DB| PG[(PostgreSQL Database)]
    PG -->|4. Populate Cache| Redis
    API -->|5. Dispatch Telemetry Event| Queue[(Redis Celery Broker)]
    Queue -->|6. Async Process Click| Worker[Celery Analytics Worker]
    Worker -->|7. Persist Analytics| PG
    
    subgraph Real-Time & Collaboration
        ClientWS[Client Browser] <-->|WebSocket Stream /teams/{id}/feed| WSManager[Activity Feed Connection Manager]
        WSManager <-->|Broadcast Events| PG
    end
```

---

## ✨ Key Features

- **⚡ Sub-Millisecond Redirections**: Read-through Redis caching pattern bypasses database lookups on hot URL paths.
- **🔄 Asynchronous Telemetry Pipeline**: Celery worker integration offloads analytics processing (IP lookup, user-agent parsing, click metrics) from the critical redirect path.
- **🛡️ Distributed Rate Limiting**: Redis-backed sliding window rate limiter protects endpoints against DDoS and API abuse (`HTTP 429`).
- **👥 Multi-Tenant Team Collaboration**: Granular Role-Based Access Control (RBAC: `Owner`, `Admin`, `Member`, `Viewer`) supporting target-generic `CommentThread` discussions and tokenized team invitations.
- **📡 Real-Time WebSockets Feed**: Stateful connection manager delivering real-time activity updates to team channels (`/teams/{team_id}/feed`).
- **🔐 Enterprise Security & IDOR Protection**: Centralized middleware preventing Insecure Direct Object References (IDOR), SQL injection, and parameter tampering.
- **📊 Observability & Health Probes**: Prometheus `/metrics` endpoint, coupled with Kubernetes `/health` (liveness) and `/ready` (readiness) probes verifying DB and Redis connectivity.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Framework** | FastAPI (ASGI), Uvicorn |
| **Language** | Python 3.10+ |
| **Database & ORM** | PostgreSQL 15, SQLAlchemy 2.0, Alembic |
| **Caching & Rate Limiting** | Redis 7 |
| **Task Queue** | Celery + Redis Broker |
| **Real-Time Communications** | WebSockets |
| **Validation & Settings** | Pydantic v2, Pydantic-Settings |
| **Testing & Mocking** | Pytest, TestClient, Pytest-Cov (224 Tests) |
| **Containerization & CI/CD** | Docker, Docker Compose, Kubernetes, Helm, GitHub Actions |
| **Monitoring** | Prometheus Client, Custom JSON Loggers |

---

## 📂 Project Structure

```text
.
├── app/
│   ├── config.py             # Pydantic environment configuration
│   ├── dependencies.py       # Auth dependencies (get_current_user) & Rate Limiter
│   ├── metrics.py            # Prometheus metrics & memory gauges
│   ├── celery_app.py         # Celery broker configuration
│   ├── tasks.py              # Asynchronous analytics task worker definitions
│   ├── routers/              # Modular API Routers
│   │   ├── activity.py       # WebSocket real-time activity feed router
│   │   ├── comments.py       # Discussion threads & comments API
│   │   ├── links.py          # Short link CRUD management (v1)
│   │   ├── links_v2.py       # Enhanced link management supporting tags (v2)
│   │   ├── notifications.py  # User mention & unread notification endpoints
│   │   ├── redirect.py       # Core fast-path URL redirection router
│   │   ├── teams.py          # Team CRUD, invitations & membership RBAC
│   │   └── webhooks.py       # Event webhook registration & triggers
│   ├── schemas/              # Pydantic validation schemas
│   └── services/             # Core business logic services
│       ├── activity_feed.py  # WebSocket connection manager
│       ├── cache_service.py  # Redis read-through cache service
│       ├── mention_service.py# Mention extractor & notification service
│       └── resilience.py     # Circuit breaker & retry handlers
├── docs/                     # Architectural decision records & runbooks
├── tests/                    # Unit, integration, and capstone end-to-end tests
├── main.py                   # FastAPI entrypoint, middleware & exception handlers
├── models.py                 # SQLAlchemy declarative base data models
├── database.py               # Database engine & session dependency (SessionLocal)
├── Dockerfile                # Multi-stage production container build
├── docker-compose.yml        # Multi-service stack composition
└── requirements.txt          # Production dependencies
```

---

## 🌐 API Endpoints Reference

### Core Redirect & Public Routes
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness probe (returns `200 OK`) |
| `GET` | `/ready` | Readiness probe (checks PostgreSQL & Redis connection health) |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint |
| `GET` | `/r/{code}` | **Core Fast-Path Redirect** (Resolves short code to destination URL) |

### Link Management (`/v1/links` & `/v2/links`)
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/v1/links/` | Create a new short URL link |
| `GET` | `/v1/links/` | List all links (Paginated) |
| `GET` | `/v1/links/{link_id}` | Fetch link details by ID |
| `PATCH` | `/v1/links/{link_id}` | Update destination URL or metadata |
| `DELETE` | `/v1/links/{link_id}` | Delete a short link (invalidates cache) |
| `POST` | `/v1/links/bulk` | Bulk create short URLs |
| `GET` | `/v1/links/{link_id}/analytics` | Fetch click analytics and timeseries data |

### Teams & Real-Time Collaboration
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/teams/` | Create a new enterprise team |
| `POST` | `/teams/{team_id}/members` | Add user to team with specified role |
| `WS` | `/teams/{team_id}/feed` | Real-time WebSocket activity feed stream |
| `POST` | `/threads/` | Create a comment thread linked to a resource |
| `POST` | `/threads/{thread_id}/comments` | Add comment to thread (with user mentions `@user`) |
| `GET` | `/notifications/` | List unread user notifications |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (Optional for containerized run)

### Local Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/samaspoorthireddy/url-shortener.git
   cd url-shortener
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```

5. **Start the FastAPI server:**
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   Access interactive API docs at `http://localhost:8000/docs`.

---

## 🐳 Running with Docker

Start the complete infrastructure stack (FastAPI, PostgreSQL, Redis, Celery worker) with a single command:

```bash
docker-compose up --build
```

---

## 🧪 Testing & Verification

The project includes an extensive automated test suite covering unit logic, integration pathways, authorization boundaries, and WebSockets.

Run the test suite with coverage report:

```bash
pytest --cov=app --cov=models
```

---

## 📈 Monitoring & Incident Runbooks

Operational runbooks and failure mode strategies are documented in the [`docs/`](./docs/) directory:
- [`docs/runbooks/runbook-high-error-rate.md`](./docs/runbooks/runbook-high-error-rate.md): Triage instructions for HTTP 5xx spikes.
- [`docs/runbooks/runbook-circuit-breaker-open.md`](./docs/runbooks/runbook-circuit-breaker-open.md): Resolution steps for external service circuit breakers.
- [`docs/rollback_plan.md`](./docs/rollback_plan.md): Linear release rollback procedures.

---

## 👤 Author

**Spoorthi Reddy Sama**  
- **GitHub:** [@samaspoorthireddy](https://github.com/samaspoorthireddy)
- **Role Target:** Special Engineer Trainee (Software Development / Manual Testing)

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
