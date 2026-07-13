# Codebase Architecture Summary

This document summarizes the core components, layout, and request flows of the URL Shortener codebase.

## 1. Folder Structure & Layout
*   **Root Directory (`/`)**: Entry points, setup files, database engine config, and dependencies.
    *   `main.py`: Entry point for FastAPI. Registers routes, middleware, and startup table creation.
    *   `models.py`: Database schema definitions using SQLAlchemy declarative base.
    *   `database.py`: SQLAlchemy connection engine and local session generator (`SessionLocal`).
    *   `requirements.txt`: Package dependency definitions.
*   **`app/`**: Core application logic.
    *   `app/config.py`: Settings module loading config from environment.
    *   `app/dependencies.py`: Authentication route dependencies (`get_current_user`) and RateLimiter.
    *   `app/metrics.py`: Instrumentation setting up Prometheus and custom memory gauges.
    *   `app/celery_app.py`: Celery instance configuration using Redis.
    *   `app/tasks.py`: Asynchronous Celery background tasks.
    *   `app/routers/`: Router packages grouping URL endpoints by resource:
        *   `links.py`: Endpoint handlers for link CRUD.
        *   `links_v2.py`: Support for link tags.
        *   `redirect.py`: Redirect route using cache-aside lookups.
        *   `webhooks.py`: Webhook subscription endpoints.
    *   `app/services/`: Business services for cache management, validation, metadata scraping, and resilience.
*   **`tests/`**: Test suite directory.

## 2. Key Data Models (Defined in `models.py`)
1.  **`Link` (table: `links`)**: Stores short code mappings, target URLs, expiration details, click caps, and metadata tags.
2.  **`ClickEvent` (table: `click_events`)**: Stores details of individual redirects (time, user agent, referrer, IP hash) with an idempotency request ID.
3.  **`WebhookSubscription` (table: `webhook_subscriptions`)**: Stores registration callback URLs.

## 3. Database & Connection Configuration
*   Uses PostgreSQL with SQLAlchemy.
*   Connection pool configuration:
    *   `pool_size=10`: Retains 10 persistent connections.
    *   `max_overflow=5`: Temporary burst of 5 additional connections.
    *   `pool_timeout=10`: Raises timeout if waiting >10s to acquire connection.
    *   `pool_pre_ping=True`: Verifies connection health before lending.

## 4. Authentication Flow
*   Header-based validation using `X-API-Key`.
*   Enforced via FastAPI dependency injection `get_current_user`.
*   Mapped statically: `API_KEY_A` -> `user_a`, `API_KEY_B` -> `user_b`.

## 5. Background Jobs (Celery)
*   **Broker**: Redis (`redis://localhost:6379/0`).
*   **Tasks**:
    *   `log_click_task`: Asynchronously records redirection click events and initiates webhook dispatches.
    *   `dispatch_webhook_task`: Delivers HTTP POST callbacks to subscribers.
    *   `purge_clicks_task`: Prunes expired click data.
