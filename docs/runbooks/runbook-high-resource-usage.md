# Runbook: Service Restart / High Memory or CPU

> **Alert**: `HighMemoryUsage` — container memory > 85% for 5+ minutes, OR `HighCPUUsage` — CPU > 90% for 5+ minutes  
> **Service**: url-shortener  
> **Severity**: P2 — service is degraded but still serving; may crash soon  
> **Format**: Linear checklist — complete every step in order  

---

## What This Means

High memory can indicate a memory leak (likely from an unbounded in-memory cache or log accumulation). High CPU can indicate a hot code path (e.g., a ReDoS-vulnerable regex on URL validation, or a stampeding retry loop). Neither will self-resolve without intervention.

---

## Step 1. Confirm current resource usage

```bash
docker stats url-shortener-prod --no-stream
```

**Expected output columns**: `CONTAINER ID`, `NAME`, `CPU %`, `MEM USAGE / LIMIT`, `MEM %`  
**Healthy baseline**: CPU < 20%, MEM < 60%  
**Action threshold**: CPU > 90% OR MEM > 85%

---

## Step 2. Check for runaway retry loops in logs

```bash
journalctl -u url-shortener --since "10 minutes ago" --no-pager \
  | grep '"message":"retry_attempt"' \
  | wc -l
```

**Expected (normal)**: < 10 retry events in 10 minutes.  
**Expected (retry storm)**: Hundreds of retry events — indicates a circuit breaker is not open but retries are looping.

If a retry storm is confirmed, check if the relevant circuit breaker has opened:

```bash
journalctl -u url-shortener --since "10 minutes ago" --no-pager \
  | grep "circuit_state_change"
```

If the breaker has NOT opened despite hundreds of retries, the breaker configuration may have drifted. Proceed to Step 3 and escalate after.

---

## Step 3. Check for slow or blocked requests

```bash
curl -s http://localhost:8000/metrics \
  | grep 'http_request_duration_seconds_bucket' \
  | grep 'le="5.0"'
```

**Expected (healthy)**: Most requests in the `le="0.5"` bucket.  
**Expected (saturated)**: Many requests only appearing in `le="5.0"` or `le="+Inf"` — confirms slow response times.

---

## Step 4. Take a thread / memory snapshot before restart

Check the process-level memory metric via the Prometheus endpoint:

```bash
curl -s http://localhost:8000/metrics | grep process_memory_bytes
```

Or query the container system stats:

```bash
docker exec url-shortener-prod ps aux --sort=-%mem | head -20
```

**Expected**: Shows Python process(es) — note the memory usage bytes (metric) or `RSS` column (ps aux) for the record.

---

## Step 5. Gracefully restart the service

```bash
docker restart url-shortener-prod
```

> ⚠️ Use `docker restart`, NOT `docker rm`. Removing the container loses the volume mapping and requires a full redeploy.

**Expected**: Container restarts. Check it came back up:

```bash
docker ps | grep url-shortener-prod
```

**Expected**: Status shows `Up X seconds` — not `Exited`.

---

## Step 6. Verify liveness and readiness after restart

```bash
curl -s http://localhost:8000/live
# Expected: {"ok":true}

curl -s http://localhost:8000/ready
# Expected: {"ok":true,"checks":{"database":"connected","cache":"connected","uptime_seconds":1}}
```

---

## Step 7. Monitor resource usage for 5 minutes post-restart

```bash
docker stats url-shortener-prod
```

**Expected**: Memory stabilises below 60% and CPU drops below 20%. If memory climbs again within 5 minutes, there is a memory leak — escalate.

---

## Step 8. Check error rate returned to baseline

```bash
curl -s http://localhost:8000/metrics \
  | grep 'http_requests_total.*5[0-9][0-9]'
```

**Expected**: Error counter is stable (not increasing rapidly).

---

## Escalation Path

| Time since alert fired | Action |
|---|---|
| 0–5 min | Follow this runbook |
| After restart, memory climbs again within 5 min | Post snapshot from Step 4 in `#platform-eng` + page Service Owner |
| CPU still > 90% after restart | Page Service Owner via PagerDuty `url-shortener-oncall` |
| 20+ min, unresolved | Engineering Lead + Infra escalation |
