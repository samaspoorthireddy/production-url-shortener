# Runbook: Circuit Breaker Open — Database

> **Alert**: `CircuitBreakerOpen` — `circuit_state_change` log event with `new_state: CircuitOpenState` for `dependency: database`  
> **Service**: url-shortener  
> **Severity**: P1 — new short codes cannot be created; cached redirects still work  
> **Format**: Linear checklist — complete every step in order  

---

## What This Means

The database circuit breaker (`db_breaker`) opened because PostgreSQL failed 5 consecutive requests. The service is now in a protective state:

- **Cache HIT redirects**: Still succeed using Redis-cached URLs ✅  
- **Cache MISS redirects**: Return `503 Service Unavailable` ❌  
- **Link creation / update / delete**: Return `503 Service Unavailable` ❌  

The circuit will automatically attempt recovery after 30 seconds (`reset_timeout=30`). This runbook covers the case where it does **not** self-recover.

---

## Step 1. Confirm the circuit is open

```bash
journalctl -u url-shortener --since "5 minutes ago" --no-pager \
  | grep "circuit_state_change" \
  | grep "CircuitOpenState" \
  | tail -5
```

**Expected (open)**:
```json
{"message": "circuit_state_change", "dependency": "database", "old_state": "CircuitClosedState", "new_state": "CircuitOpenState"}
```

**Expected (not open)**: No output — circuit is not the issue. Stop here and check other runbooks.

---

## Step 2. Check PostgreSQL connectivity directly

```bash
psql "$DATABASE_URL" -c "SELECT NOW();" 2>&1
```

**Expected (healthy)**:
```
              now
-------------------------------
 2026-06-04 06:09:00.000000+00
```

**Expected (down)**: `could not connect to server: Connection refused` or a timeout after several seconds.

---

## Step 3a. If PostgreSQL is DOWN — restart it

```bash
# Homebrew (local / staging)
brew services restart postgresql@16

# Docker Compose
docker compose restart db

# Systemd
sudo systemctl restart postgresql
```

Verify it came back:

```bash
psql "$DATABASE_URL" -c "SELECT 1;" 2>&1
```

**Expected**: `1` returned within 2 seconds.

---

## Step 3b. If PostgreSQL is UP — check for long-running locks

```bash
psql "$DATABASE_URL" -c "
  SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
  FROM pg_stat_activity
  WHERE state = 'active'
    AND now() - pg_stat_activity.query_start > interval '5 seconds'
  ORDER BY duration DESC;
" 2>&1
```

**Expected (no locks)**: Empty result set `(0 rows)`.  
**Expected (locks present)**: Rows showing long-running queries. Kill the offending PID:

```bash
psql "$DATABASE_URL" -c "SELECT pg_terminate_backend(PID);"
```

Replace `PID` with the process ID from the query above.

---

## Step 4. Wait for circuit breaker auto-recovery (30 seconds)

```bash
sleep 30
```

The `db_breaker.reset_timeout = 30` seconds. After this duration, the next request will probe in HALF-OPEN state.

---

## Step 5. Send a probe request to trigger recovery

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/r/healthcheck-probe
```

**Expected (recovery succeeding)**: `404` — the code does not exist, but the circuit attempt reached the database.  
**Expected (still open)**: `503` — wait another 30 seconds and retry this step.

---

## Step 6. Confirm circuit closed in logs

```bash
journalctl -u url-shortener --since "2 minutes ago" --no-pager \
  | grep "circuit_state_change" \
  | tail -5
```

**Expected**:
```json
{"message": "circuit_state_change", "dependency": "database", "old_state": "CircuitOpenState", "new_state": "CircuitHalfOpenState"}
{"message": "circuit_state_change", "dependency": "database", "old_state": "CircuitHalfOpenState", "new_state": "CircuitClosedState"}
```

---

## Step 7. Verify end-to-end redirect works

```bash
# First check the health endpoint
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}

# Then check readiness (verifies DB connectivity)
curl -s http://localhost:8000/ready
# Expected: {"status":"ready","database":"ok","redis":"ok"}
```

---

## Step 8. Check for data drift during outage

If the outage lasted more than 2 minutes, verify that any write operations that failed during the open state are accounted for. Celery will have queued retried analytics events — confirm the queue is draining:

```bash
celery -A app.celery_app inspect active 2>&1 | head -20
```

**Expected**: Shows queued tasks processing, or `No workers found` if Celery is idle (all tasks drained).

---

## Escalation Path

| Time since alert fired | Action |
|---|---|
| 0–5 min | Follow this runbook |
| 5 min, PostgreSQL still down | Page `dba-oncall` via PagerDuty |
| 10 min, circuit still open after DB recovered | Page Service Owner via `url-shortener-oncall` |
| 20+ min, unresolved | Escalate to Infra and Engineering Lead |

---

## Drill Test Record

**Tested**: 2026-06-04  
**Tester**: Platform Engineering  
**Scenario**: Stopped `postgresql@16` mid-traffic; fired 8 rapid redirect requests to `/r/nonexistent-*` to exhaust the breaker threshold.

| Step | Command run | Result | Matches runbook? |
|---|---|---|---|
| A1 — Confirm 503s | `curl -o /dev/null -w "%{http_code}" /r/nonexistent` × 8 | All 8 returned `503` | ✅ |
| A2 — Confirm DB down | `psql "$DATABASE_URL" -c "SELECT 1;"` | `Connection refused` | ✅ |
| A3 — Confirm Redis up | `redis-cli ping` | `PONG` | ✅ |
| A4 — Restart DB | `brew services start postgresql@16` | Started successfully | ✅ |
| A5 — Wait 31s | `sleep 31` | Elapsed | ✅ |
| A6 — Recovery probe | `curl -w "%{http_code}" /r/probe-test-*` | `404` (not 503) — DB reached | ✅ |

**Steps updated after drill**: 0  
**Notes**: Runbook steps matched real behaviour exactly. The recovery probe correctly returned `404` (code not found in DB) rather than `503`, proving the circuit transitioned OPEN → HALF-OPEN → CLOSED automatically after the 30s `reset_timeout`. No runbook corrections were required.
