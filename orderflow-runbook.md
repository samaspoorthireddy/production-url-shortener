# OrderFlow On-Call Runbook

This runbook is designed for 3 AM on-call triage and recovery of the `OrderFlow` service.

---

## 1. Prerequisites & Required Tools
Before executing any troubleshooting commands, verify that the following CLI tools are installed on your machine:

1. **kubectl** (Kubernetes command-line tool)
   - *Verify installation*: `kubectl version --client`
   - *Install if missing*: `brew install kubernetes-cli`
2. **helm** (Kubernetes package manager)
   - *Verify installation*: `helm version`
   - *Install if missing*: `brew install helm`
3. **curl** (HTTP request client)
   - *Verify installation*: `curl --version`
   - *Install if missing*: `brew install curl`

---

## 2. Active Environment Constants
To prevent manual substitutions, copy and run this entire block in your active terminal to set up the context:

```bash
export SERVICE_PORT=8080
export DB_PORT=5432
export REDIS_PORT=6379
export CELERY_PORT=6379
export K8S_NAMESPACE="production"
export HELM_RELEASE="orderflow"
export APP_LABEL="orderflow-api"
export CELERY_LABEL="orderflow-worker"
```

---

## 3. Health Triage Flow
Follow these steps sequentially to diagnose the current status:

1. **Verify Pod Status**: Check if API and Worker pods are running in the cluster.
   ```bash
   kubectl get pods --namespace $K8S_NAMESPACE -l "app in ($APP_LABEL, $CELERY_LABEL)"
   ```
   - **If** API pods are not `Running` or have high restart counts, go to [Failure Mode A: API Unhealthy / Unreachable](#41-failure-mode-a-api-unhealthy--unreachable).
   - **If** Worker pods are not `Running` or have high restart counts, go to [Failure Mode B: Worker Process Stopped](#42-failure-mode-b-worker-process-stopped).
   - **If** all pods are `Running`, go to step 2.

2. **Verify API Reachability**: Port-forward to the API service and test the health endpoint.
   In Terminal 1:
   ```bash
   kubectl port-forward svc/$HELM_RELEASE $SERVICE_PORT:$SERVICE_PORT --namespace $K8S_NAMESPACE
   ```
   In Terminal 2:
   ```bash
   curl -i http://localhost:$SERVICE_PORT/health
   ```
   - **If** the command returns `HTTP/1.1 200 OK`, the API is healthy. Go to step 3.
   - **If** the command returns `HTTP/1.1 5xx` or connection fails, go to [Failure Mode A: API Unhealthy / Unreachable](#41-failure-mode-a-api-unhealthy--unreachable).

3. **Verify Redis Connectivity**: Test caching and rate-limiting connectivity.
   ```bash
   kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- python -c "import redis; r = redis.Redis(host='localhost', port=$REDIS_PORT); print('Connected' if r.ping() else 'Failed')"
   ```
   - **If** connection prints `Failed` or raises a ConnectionError, go to [Failure Mode C: Redis Cache Down](#43-failure-mode-c-redis-cache-down).
   - **If** connection prints `Connected`, go to step 4.

4. **Verify Database Connectivity**: Test database status from an application pod.
   ```bash
   kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- python -c "import os, psycopg2; conn = psycopg2.connect(os.getenv('DATABASE_URL')); cur = conn.cursor(); cur.execute('SELECT 1;'); print('DB OK' if cur.fetchone() == (1,) else 'DB Error')"
   ```
   - **If** connection fails, go to [Failure Mode A: API Unhealthy / Unreachable (Postgres Database issues)](#41-failure-mode-a-api-unhealthy--unreachable).

---

## 4. Failure Modes & Recovery Procedures

### 4.1. Failure Mode A: API Unhealthy / Unreachable
1. **Fetch Application Logs**: Run this command to inspect the last 150 lines of logs for errors.
   ```bash
   kubectl logs --namespace $K8S_NAMESPACE -l app=$APP_LABEL --tail=150
   ```
2. **Review DB Connection Errors**: If logs contain `psycopg2.OperationalError: connection refused` or `Too many connections`:
   - Inspect active database sessions:
     ```bash
     kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- python -c "import os, psycopg2; conn = psycopg2.connect(os.getenv('DATABASE_URL')); cur = conn.cursor(); cur.execute('SELECT count(*), state FROM pg_stat_activity GROUP BY state;'); print(cur.fetchall())"
     ```
   - If the connection pool is saturated, restart the API pods to clear connections:
     ```bash
     kubectl rollout restart deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE
     ```
3. **Review Migration Status**: If logs show `Relation does not exist` or `alembic migration errors`:
   - Inspect the database schema state:
     ```bash
     kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- alembic current
     ```
   - Run outstanding database migrations:
     ```bash
     kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- alembic upgrade head
     ```
4. **Stripe API Issues**: If logs show `StripeAPIError: invalid stripe key`:
   - Dump Stripe configuration variable (verify key exists and begins with `sk_live`):
     ```bash
     kubectl set env deployment/$HELM_RELEASE --list --namespace $K8S_NAMESPACE | grep STRIPE_API_KEY
     ```
   - If key is invalid or expired, proceed to [5. Escalation Path](#5-escalation-path) to contact Platform Payments.
5. **Rollback Bad Deployment**: If the API became unhealthy immediately after a git merge/release:
   - Identify the current revision number:
     ```bash
     helm history $HELM_RELEASE --namespace $K8S_NAMESPACE
     ```
   - Roll back to the previous deployment revision (substitute `REVISION_NUMBER` with the preceding successful version from helm history):
     ```bash
     helm rollback $HELM_RELEASE --namespace $K8S_NAMESPACE
     ```
   - Verify rollback completed successfully:
     ```bash
     kubectl rollout status deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE
     ```

### 4.2. Failure Mode B: Worker Process Stopped
1. **Inspect Worker Logs**: Run this to search for unhandled exceptions or connection errors in the worker pods.
   ```bash
   kubectl logs --namespace $K8S_NAMESPACE -l app=$CELERY_LABEL --tail=150
   ```
2. **Check Celery Process Status**:
   ```bash
   kubectl exec -it deployment/$CELERY_LABEL --namespace $K8S_NAMESPACE -- celery -A orderflow.worker inspect ping
   ```
   - **If** worker does not respond to ping, restart the worker deployment:
     ```bash
     kubectl rollout restart deployment/$CELERY_LABEL --namespace $K8S_NAMESPACE
     ```
3. **Verify Queue Backlog**: Query Redis to check the length of the refund queue:
   ```bash
   kubectl exec -it deployment/$HELM_RELEASE --namespace $K8S_NAMESPACE -- python -c "import redis; r = redis.Redis(host='localhost', port=$REDIS_PORT); print('Queue Length:', r.llen('celery'))"
   ```

### 4.3. Failure Mode C: Redis Cache Down
1. **Verify Redis Pod Health**: Check if the Redis pod is running on port 6379:
   ```bash
   kubectl get pods --namespace $K8S_NAMESPACE -l app=redis
   ```
2. **Retrieve Redis Logs**: Look for OOM (Out Of Memory) events or snapshot write errors:
   ```bash
   kubectl logs --namespace $K8S_NAMESPACE -l app=redis --tail=100
   ```
3. **Restart Redis**: If Redis is unresponsive:
   ```bash
   kubectl rollout restart deployment/redis --namespace $K8S_NAMESPACE
   ```

---

## 5. Escalation Path
If the service is not restored within **15 minutes** of executing the recovery steps above:

| Escalation Destination | Slack Channel | PagerDuty Policy |
|---|---|---|
| Platform Payments Team (Service Owner) | `#orderflow-oncall` | `OrderFlow Primary` |
| Database Administrators (Postgres) | `#data-eng` | `DBA Primary Escalation` |
| Infrastructure Engineers (K8s / Networking) | `#platform-infra` | `Cloud Infrastructure` |
