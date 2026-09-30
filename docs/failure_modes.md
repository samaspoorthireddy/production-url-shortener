# Failure Mode Analysis (FMA)

This document contains the Dependency Inventory, Failure Mode Analysis Matrix, and Simulated Outages Log for the Python/FastAPI URL Shortener service.

---

## 1. Dependency Inventory

The URL Shortener service relies on several internal and external systems to perform its functions. The inventory below documents each dependency, how it is connected, timeout limits, and retry patterns.

| Dependency | Connection Method | Configured Timeout | Retry Behavior |
| :--- | :--- | :--- | :--- |
| **PostgreSQL** | TCP via SQLAlchemy Pool (`psycopg2-binary`) | Connect: `5.0s`<br>Pool Wait: `10.0s` | `pool_pre_ping=True` (automatic reconnect for stale sockets). No application-level query retries. |
| **Redis (Cache & Celery Broker)** | TCP via `redis.asyncio` connection pool | Default socket timeout (unlimited) | None configured in code; cache operations fail-open (fail-safe fallback to DB). |
| **External API (Scraper)** | HTTPS via `httpx.Client` (sync stream) | Strict: `3.0s` | None (graceful degradation: returns empty metadata on failure). |
| **File System** | Local OS filesystem calls | N/A (blocking write) | None (raises OS exception). |
| **DNS** | OS resolver (`getaddrinfo`) | OS Default (~30.0s) | OS resolver default retries. |
| **Celery Tasks** | Redis Client (Broker/Backend connection) | Soft Limit: `30.0s`<br>Hard Limit: `60.0s` | `autoretry_for=(Exception,)`, up to 5 times, exponential backoff (default delay 10s, capped at 120s). |

---

## 2. Failure Mode Analysis Matrix

Below is a detailed analysis of the 12 failure modes identified for the service.

| Dependency | Failure Mode | Probability | User Impact | Current Handling | Desired Handling |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Database** | Connection refused (PostgreSQL stopped) | Medium | Complete outage for writes & cache misses. API `/ready` fails. | `/ready` returns `503 Service Unavailable`. Database queries raise `OperationalError` which is caught by FastAPI exception handler and returns `503 Service Unavailable`. | Expose readiness to load balancer to drain traffic. Return standard 503 with a `Retry-After` header. |
| **Database** | Slow queries (high database latency) | High | Requests hang, threads exhaust, cascading timeouts. | Waits indefinitely (or up to pool timeout of 10s if waiting for a connection). | Set statement timeout (`statement_timeout=3000ms`) via connection args, raise 504 on timeout. |
| **Cache (Redis)** | Down / Unreachable | Medium | Cache misses, DB query load increases significantly. | Service degrades gracefully; catches Redis exceptions and query database directly. | Circuit breaker to stop spamming Redis during outage. Alert on persistent cache errors. |
| **Cache (Redis)** | Stale data / invalidation failure | High | User redirected to old/expired destination URLs. | Cache evicted on deletes/updates. If eviction fails, stale redirect is served until 300s TTL expires. | Version stamps on cache entries, or shorter cache TTLs for dynamic/highly-active links. |
| **External API** | Scraper API is down | Medium | Link created successfully, but metadata details remain empty. | Exception caught in `scraper.py`, logged as Warning, returns empty metadata. Link created with empty title. | Keep existing fail-open/degrade gracefully design. |
| **External API** | Scraper API is slow | High | Link creation latency spikes up to scraper timeout. | Enforces strict 3.0s timeout in `httpx.Client`. If exceeded, times out, logs warning, returns empty title. | Reduce scraper timeout to 1.5s or offload scraping completely to Celery background task. |
| **Disk** | Disk full | Low-Medium | Logging fails, temp files fail, database may crash. | Standard python logging fails, potential filesystem exception bubbles up or logging fails silently. | Setup Docker log rotation, alert on disk usage > 80%, store temp files in memory-backed mount (`/dev/shm`). |
| **Runtime (Memory)**| Out of Memory (OOM) | Low-Medium | OS terminates process. In-flight requests dropped immediately. | Process dies. Docker/Kubernetes container restarts the worker instance automatically. | Configure container RAM limits, set CPU/Memory thresholds in Prometheus, alert at 80% usage. |
| **Network** | Network partition (DB unreachable, Cache reachable) | Low | Redirects from cache succeed instantly, but new links / cache misses fail. | Cache resolves redirects successfully. Cache misses and POSTs crash on DB queries (500 error). | Serve cache hits successfully, degrade gracefully to return 503 for database-bound requests. |
| **DNS** | DNS resolution failure | Low-Medium | Service cannot find DB, Cache, or Scraper hostnames. | Connection attempts timeout or raise "host not found". Readiness fails. | Cache DNS lookups locally (`nscd` or local dnsmasq), use IP addresses for static cluster nodes. |
| **Connection Pool** | Pool exhaustion (all slots taken) | High | Incoming DB queries block waiting for a slot, then raise timeout. | SQLAlchemy raises `TimeoutError` which is caught by FastAPI exception handler and returns `503 Service Unavailable`. | Alert on pool utilization > 80%. Tune pool size and overflow. Implement query rate-limiting. |
| **Clock Skew** | Host system clock drifts | Low | Incorrect TTL calculations, metrics timestamp misalignment. | Rely on system clock. Expiration times could occur too early or too late. | Run `ntpd`/`chrony` on host nodes, alert on host drift > 1.0s. Use UTC timestamps everywhere. |

---

## 3. Simulated Outages Log

To validate the service resilience under actual failure conditions, we executed four simulated outage drills.

### Simulation 1: Stopped Database
* **Execution**: Ran `brew services stop postgresql@16` to terminate the PostgreSQL server.
* **Observed Behavior**:
  - `/health` endpoint: Returned `200 OK` with body `{"status":"healthy"}` instantly (latency < 5ms). This validates that the liveness check is independent of dependencies.
  - `/ready` endpoint: Returned `503 Service Unavailable` with body `{"status":"unready","reason":"Database connection failed"}` in < 20ms. The error log was correctly captured as:
    ```
    Readiness check failed: Database is unreachable. Error: (psycopg2.OperationalError) connection to server at "localhost" (127.0.0.1), port 5432 failed: Connection refused
    ```
* **Gap Identified**: None. The service behaved exactly as intended: liveness checks remain green to prevent container restart loops, while readiness checks turn red to halt traffic routing.

### Simulation 2: Impossibly Low Timeout (1ms) on Metadata Scraper
* **Execution**: Modified `app/services/scraper.py` to use `timeout=0.001` in the `httpx.Client` context manager, then restarted the server.
* **Observed Behavior**:
  - Request: POST `http://localhost:3000/v1/links/` for `https://wikipedia.org`
  - Response: Returned `201 Created` with the JSON response containing `"title": null` in `115ms`.
  - Log Output:
    ```
    Metadata scraping failed for URL 'https://wikipedia.org', degrading gracefully. Error: timed out
    ```
* **Gap Identified**: None. The scraper caught the timeout exception, logged a warning, and degraded gracefully. Link creation was completed successfully without cascading to a `500 Internal Server Error`.

### Simulation 3: Connection Pool Timeout
* **Execution**: Mocked link creation to raise `sqlalchemy.exc.TimeoutError` mimicking pool exhaustion.
* **Observed Behavior**:
  - Request: POST `/v1/links/`
  - Response: Returned `503 Service Unavailable` with `"code": "SERVICE_UNAVAILABLE"` and `"message": "Database connection pool exhausted or query timed out. Please retry shortly."`.
  - Log Output:
    ```
    Database connection pool exhausted or query timed out (checkout timeout): ...
    ```

### Simulation 4: Database Connectivity Failure during Request
* **Execution**: Mocked link creation to raise `sqlalchemy.exc.OperationalError` mimicking database crash mid-request.
* **Observed Behavior**:
  - Request: POST `/v1/links/`
  - Response: Returned `503 Service Unavailable` with `"code": "SERVICE_UNAVAILABLE"` and `"message": "Database service is temporarily unavailable. Please retry shortly."`.
  - Log Output:
    ```
    Database connectivity failure: ...
    ```

---
*Note: All services were restored to their healthy running states upon completion of the drills.*
