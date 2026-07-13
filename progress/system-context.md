# System-Level Context Document

This document defines the architectural context, coding conventions, and constraints for the Upsk URL Shortener project. All code generation tasks must adhere strictly to these guidelines.

## 1. Architecture Summary

### Framework
* **FastAPI** (version >= 0.110.0) is the web framework.
* **Uvicorn** (version >= 0.28.0) is the ASGI server.

### Project Organization
The project is structured as follows:
* **Root Directory (`/`)**: Entry points, database engine config, database model declarations.
  * [main.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/main.py): Entry point for FastAPI. Configures app, middleware, routes registration, and handles database startup migrations.
  * [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py): Contains all SQLAlchemy declarative base models.
  * [database.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/database.py): Handles database engine, local session generator (`SessionLocal`), and `get_db` dependency.
* **`app/`**: Core application directories:
  * `app/config.py`: Settings module loading config from environment variables using `pydantic-settings`.
  * `app/dependencies.py`: Authentication route dependencies (`get_current_user`) and thread-safe in-memory `RateLimiter`.
  * `app/metrics.py`: Custom Prometheus metrics and memory gauges.
  * `app/celery_app.py` & `app/tasks.py`: Asynchronous task execution using Celery and Redis.
  * `app/routers/`: Router packages grouping endpoints by resource:
    * [app/routers/teams.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/teams.py): Teams CRUD and membership.
    * [app/routers/links.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/links.py): Links management.
    * [app/routers/links_v2.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/links_v2.py): Enhanced links API supporting tags.
    * [app/routers/redirect.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/redirect.py): URL redirection.
    * [app/routers/webhooks.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/routers/webhooks.py): Webhook registration endpoints.
  * `app/schemas/`: Data validation schemas:
    * [app/schemas/teams.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/schemas/teams.py): Pydantic validation for team requests/responses.
    * [app/schemas/link.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/schemas/link.py): Pydantic validation for link requests/responses.
  * `app/services/`: Services containing core business logic (e.g. metadata scraping, cache lookup, resilience).

### Database & ORM
* **SQLAlchemy** (version >= 2.0.0) is the ORM, connecting to a **PostgreSQL** database.
* Connections are pooled with parameters: `pool_size=10`, `max_overflow=5`, `pool_timeout=10`, and `pool_pre_ping=True`.
* Sessions are obtained using the `get_db` dependency which yields a `Session` and automatically closes it after the request lifecycle.

### Route Registration
* Routes are declared inside `app/routers/*.py` using `APIRouter()`.
* They are registered in `main.py` using `app.include_router(router, ...)` with version prefixes where appropriate (e.g., prefix `"/v1"`, `"/v2"` or no prefix for redirect route).
* For example:
  * `app.include_router(links.router, prefix="/v1")`
  * `app.include_router(webhooks.router, prefix="/v1")`
  * `app.include_router(links_v2.router, prefix="/v2")`
  * `app.include_router(teams.router)` (prefix `/teams` is inside the router itself)

### Middleware
* Request lifecycle processing is hooked via `@app.middleware("http")` in `main.py`.
* Active middleware:
  * Request-ID injection, Latency logging, and API-key header masking (`log_and_time_requests`).
  * API version deprecation headers injection (`deprecation_header_middleware`).
  * CORS headers setup (`CORSMiddleware`).

---

## 2. Coding Conventions

### Naming Conventions
* **Variables, Functions, and Files**: Use `snake_case` (e.g., `get_current_user`, `models.py`, `teams.py`).
* **Classes (Pydantic and SQLAlchemy models)**: Use `PascalCase` (e.g., `Team`, `UserTeam`, `TeamCreate`).
* **Table Names**: Plural `snake_case` (e.g., `teams`, `user_teams`, `links`, `click_events`).
* **Foreign Keys**: `singular_table_name.id` (e.g., `teams.id`, `links.id`).

### Error Handling Convention
* All exceptions are intercepted by global exception handlers in `main.py` and returned in a standard envelope format:
  ```json
  {
    "error": {
      "code": "ERROR_CODE",
      "message": "Friendly descriptive string.",
      "request_id": "UUID-string"
    }
  }
  ```
* Standard codes mapped by handlers:
  * **`VALIDATION_ERROR`** (HTTP 422): For input schema errors. Detail lists field names and errors separated by semicolons.
  * **`UNAUTHORIZED`** (HTTP 401): Missing or invalid headers.
  * **`FORBIDDEN`** (HTTP 403): User lacks permission to complete action.
  * **`NOT_FOUND`** (HTTP 404): Resource not found.
  * **`TOO_MANY_REQUESTS`** (HTTP 429): Rate limits breached.
  * **`SERVICE_UNAVAILABLE`** (HTTP 503): Database timeout or operational connection loss.
  * **`INTERNAL_SERVER_ERROR`** (HTTP 500): Unhandled exception. In development/staging, prints the traceback message, otherwise hides details.
* **Rule**: Raise `HTTPException(status_code=..., detail="...")` within router code. Do not construct JSON error objects manually; the global exception handler in `main.py` wraps details in the correct `"error"` envelope.

### Validation
* Input validation is strictly declared via **Pydantic (v2)** schemas in `app/schemas/`.
* Declare requirements using `Field(..., min_length=..., max_length=...)` and custom validation rules via `@field_validator("field_name")` classmethods.

### Authentication & Authorization
* Headers are validated using the `get_current_user` dependency from `app/dependencies.py`.
* Routes that require authentication must declare it: `current_user: str = Depends(get_current_user)`.
* This extracts and matches the header `X-API-Key`. Unauthenticated requests are rejected with a `401 Unauthorized` status.

---

## 3. Constraints

1. **No new packages**: Do not introduce new npm/pip packages to `requirements.txt` unless strictly justified and approved.
2. **Reuse existing dependencies**: Always use `get_db` and `get_current_user` dependencies. Do not construct duplicate auth logic or custom db sessions.
3. **Consistent naming**: Place all database models in `models.py`. Place all routers in `app/routers/`. Place all validation schemas in `app/schemas/`.
4. **Resilient Migrations**: Database changes must be accompanied by startup migrations executed inside the `try/except` block in `main.py` (using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) to prevent startup crashes when tables already exist.
5. **No plain text errors**: Do not return plain text errors or responses that violate the standard `{ "error": { "code": "...", "message": "..." } }` JSON schema.
6. **Database Transaction Safety**: Any database write operation (adds, edits, deletes, commits) inside API router endpoints must be wrapped in a `try/except` block. If an exception occurs, `db.rollback()` must be called to prevent corrupting the session before raising an appropriate `HTTPException`.
7. **Class-Based Service Organization**: Any business logic or helper utility placed in `app/services/` must be wrapped in a service class (e.g., `class MentionService`) with appropriate loggers, typing, and structured methods rather than loose module-level functions.

