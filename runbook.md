# url-shortener Operations Runbook (Production Readiness Module 04)

This runbook provides actionable procedures for resolving active alerts on the `url-shortener` service.

---

## High Error Rate

**Alert**: `HighErrorRate` (Severity: `critical`)  
**Trigger**: HTTP 5xx error rate > 5% over a 5-minute rolling window.

### Troubleshooting Steps
1. **Identify the Scope**:
   Check if the errors are localized to specific endpoints or instances by querying Prometheus metrics:
   ```promql
   sum(rate(http_requests_total{status_code="5xx"}[5m])) by (endpoint, method)
   ```
2. **Review Application Logs**:
   Query your log aggregator (or run `docker logs` on active container instances) filtering for `level="error"` or `level="critical"`.
   Look for:
   - Database connection errors (e.g., connection pool exhaustion, timeout exceptions).
   - Redis cache timeouts or exceptions.
   - External dependencies failures (e.g., SSRF checks / webhooks).
3. **Verify Database Health**:
   Check database connection metrics and active pool usage:
   - Is Postgres reachable? Check database CPU and memory metrics.
   - Run `SELECT * FROM pg_stat_activity;` to locate stuck or slow locking transactions.
4. **Mitigation**:
   - If the error is caused by a recent deployment, perform an immediate rollback.
   - If DB pool is exhausted, increase `PORT` instances or scale up Postgres pool limits.

---

## High Latency

**Alert**: `HighLatency` (Severity: `warning`)  
**Trigger**: 95th percentile request latency exceeds 2 seconds for >3 minutes.

### Troubleshooting Steps
1. **Locate the Slow Endpoint**:
   Query Prometheus to find which route is dragging down latency:
   ```promql
   histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))
   ```
2. **Check Database Performance**:
   - High latency is usually database-related. Check for missing indexes or complex un-indexed queries on `ClickEvent` / `Link` tables.
   - Run `EXPLAIN ANALYZE` on any query that is identified as slow.
3. **Check Cache Hits**:
   Check if the Redis cache hit rate has suddenly dropped, causing all requests to hit the database directly:
   ```promql
   rate(cache_ops_total{result="miss"}[5m]) / rate(cache_ops_total[5m])
   ```
4. **Mitigation**:
   - Add/verify indexes on slow database queries.
   - If Redis is down, verify cache service health and restart the Redis instance.

---

## Service Down

**Alert**: `ServiceDown` (Severity: `critical`)  
**Trigger**: Scraper cannot reach `/metrics` for > 1 minute.

### Troubleshooting Steps
1. **Check Container Status**:
   List active containers to see if the app container has crashed:
   ```bash
   docker ps -a | grep myservice
   ```
2. **Inspect Crash Reason**:
   Read the last 50 lines of logs from the crashed container:
   ```bash
   docker logs <container_id> --tail 50
   ```
   Look for:
   - Out of Memory (OOM) killer terminations.
   - Startup validation failures (missing required environment variables).
   - Database unreachable crashes.
3. **Verify Network Connectivity**:
   - Ping the service port from within the cluster: `curl -I http://localhost:3000/health`.
   - Verify if firewall rules or security groups have been altered recently.
4. **Mitigation**:
   - Restart the app container: `docker start <container_id>`.
   - Scale up container memory limits if terminated due to OOM.
