# Runbook: High Error Rate on Redirect Endpoint

> **Alert**: `ErrorRate5xxHigh` — 5xx error rate on `/r/{code}` exceeds 5% for 2+ minutes  
> **Service**: url-shortener  
> **Severity**: P1 — customer-facing redirect path is degraded  
> **Format**: Linear checklist — complete every step in order  

---

## Quick Triage

Before starting, identify which symptom you are seeing:

| Symptom | Go to |
|---|---|
| 503 errors AND PostgreSQL alerts firing | [Section A — Database Outage](#section-a--database-outage) |
| 503 errors AND Redis alerts firing | [Section B — Redis Outage](#section-b--redis-outage) |
| 500 errors, no infra alerts | [Section C — Application Error](#section-c--application-error) |
| Slow responses (>2s), not hard errors | [Section D — Latency / Saturation](#section-d--latency--saturation) |

---

## Section A — Database Outage

### Step A1. Confirm 503s are occurring and the circuit breaker is open

> ⚠️ **RUNBOOK CORRECTION (2026-06-04)**: The previous command referenced `http_requests_total` which does not exist in this service. The metrics middleware tracks `http_request_duration_seconds` (latency only). Use the application log instead.

```bash
# Check structured logs for 503 responses in the last 5 minutes
grep '"status_code":503\|"message":"Database circuit open"' \
  /tmp/url-shortener.log 2>/dev/null | tail -10

# If running in foreground / Docker, check container logs:
docker logs url-shortener-prod --since 5m 2>&1 | grep -E '"status_code":503|circuit open'
```

**Expected (breaker open)**: Lines showing `"message":"Database circuit open on cache miss"`.  
**Expected (breaker closed)**: No such lines — 503s have a different root cause; check Sections C or D.

### Step A2. Confirm PostgreSQL is unreachable

```bash
psql "$DATABASE_URL" -c "SELECT 1;" 2>&1
```

**Expected (down)**: `could not connect to server: Connection refused` or timeout.  
**Expected (up)**: `?column? --------  1`

### Step A3. Confirm Redis cache is still serving redirects

```bash
redis-cli -u "$REDIS_URL" GET "redirect:abc123"
```

**Expected (cache hit)**: Returns the long URL string — redirects are still working for cached codes.  
**Expected (cache miss)**: `(nil)` — those codes will 503.

### Step A4. Restart PostgreSQL if it is down

```bash
# Homebrew (local / staging)
brew services restart postgresql@16

# Docker
docker restart postgres-prod

# Systemd
sudo systemctl restart postgresql
```

**Expected output after restart**: No error text. Service starts without error.

### Step A5. Wait for circuit breaker to recover (30 seconds)

The `db_breaker` has `reset_timeout=30`. After PostgreSQL is healthy, wait 30 seconds for the circuit to transition OPEN → HALF-OPEN → CLOSED automatically.

```bash
sleep 30
```

### Step A6. Verify recovery

```bash
curl -v http://localhost:8000/r/testcode 2>&1 | grep "< HTTP"
```

**Expected**: `< HTTP/1.1 302 Found` or `< HTTP/1.1 404 Not Found` — not a 503.

### Step A7. Verify logs show circuit closed

```bash
journalctl -u url-shortener --since "5 minutes ago" --no-pager | grep "circuit_state_change"
```

**Expected**:
```json
{"message": "circuit_state_change", "dependency": "database", "old_state": "CircuitOpenState", "new_state": "CircuitHalfOpenState"}
{"message": "circuit_state_change", "dependency": "database", "old_state": "CircuitHalfOpenState", "new_state": "CircuitClosedState"}
```

### Step A8. Escalate if not resolved in 10 minutes

If PostgreSQL is still down after 10 minutes: page `dba-oncall` via PagerDuty.

---

## Section B — Redis Outage

### Step B1. Confirm Redis is unreachable

```bash
redis-cli -u "$REDIS_URL" ping
```

**Expected (down)**: `Could not connect to Redis at ...` or timeout.  
**Expected (up)**: `PONG`

### Step B2. Restart Redis

```bash
# Homebrew (local / staging)
brew services restart redis

# Docker
docker restart redis-prod

# Systemd
sudo systemctl restart redis
```

### Step B3. Verify redirects still working (fallback to DB)

```bash
curl -v http://localhost:8000/r/testcode 2>&1 | grep "< HTTP"
```

**Expected**: `< HTTP/1.1 302 Found` — service degrades to DB-direct, not 503.

### Step B4. Escalate if Redis is still down in 5 minutes

Page `infra-oncall` via PagerDuty.

---

## Section C — Application Error

### Step C1. Check recent error logs

```bash
journalctl -u url-shortener --since "10 minutes ago" --no-pager | grep '"level":"error"' | tail -20
```

**Expected (traceback present)**: JSON log line with `"level":"error"` and `"message"` field showing the exception.

### Step C2. Check for a recent deployment

```bash
docker inspect url-shortener-prod --format '{{.Created}}'
```

If the container was started in the last 30 minutes and errors started at the same time: this is a bad deploy. Proceed to rollback.

### Step C3. Rollback to previous image

```bash
docker stop url-shortener-prod
docker rm url-shortener-prod
docker run -d \
  --name url-shortener-prod \
  --env-file .env.production \
  -p 8000:8000 \
  ghcr.io/yourorg/url-shortener:PREVIOUS_TAG
```

Replace `PREVIOUS_TAG` with the last known-good image tag from your container registry.

### Step C4. Verify recovery

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
curl -s http://localhost:8000/r/testcode
# Expected: 302 redirect or 404, not 500
```

### Step C5. Escalate if rollback does not resolve

Ping `#platform-eng` on Slack with the error log snippet from Step C1.

---

## Section D — Latency / Saturation

### Step D1. Check connection pool pressure

```bash
curl -s http://localhost:8000/metrics | grep 'sqlalchemy_pool'
```

**Expected (normal)**: `sqlalchemy_pool_checked_out` close to 0.  
**Expected (saturated)**: `sqlalchemy_pool_checked_out` equals or exceeds pool size.

### Step D2. Check Redis latency

```bash
redis-cli -u "$REDIS_URL" --latency -i 1
```

**Expected (normal)**: < 1ms.  
**Expected (degraded)**: > 50ms — indicates Redis is overloaded.

### Step D3. Restart the service to reset the connection pool

```bash
docker restart url-shortener-prod
```

**Expected**: Service restarts and pool resets. Not `docker rm` — just `restart`.

### Step D4. Verify latency improved

```bash
curl -o /dev/null -s -w "Time: %{time_total}s\n" http://localhost:8000/r/testcode
```

**Expected**: < 0.5 seconds.

---

## Escalation Path

| Time since alert fired | Action |
|---|---|
| 0–5 min | Follow this runbook |
| 5–10 min | Post in `#platform-eng` Slack with symptoms |
| 10+ min | Page Service Owner via PagerDuty `url-shortener-oncall` |
| 20+ min | Page DBA or Infra depending on root cause |
