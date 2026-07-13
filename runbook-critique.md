# OrderFlow Runbook Critique: Failure Identification

This critique evaluates the operational flaws in the provided `OrderFlow Service -- Incident Runbook` under pressure at 3 AM.

---

## 1. Stale Environment Variable Reference
* **Location**: Step 3 (Database Connection Failure), lines containing:
  - `python -c "import psycopg2; psycopg2.connect('$DB_CONNECTION_STRING')"`
  - `kubectl exec -n production deployment/orderflow-api -- printenv DB_CONNECTION_STRING`
* **Operational Impact**: An engineer testing database connectivity will get a failure because `$DB_CONNECTION_STRING` is empty. Running `printenv` will return nothing. The engineer will waste critical time trying to diagnose a deployment configuration error when the database credentials are valid but named differently (`DATABASE_URL`).
* **Correct Fix**: Update the connection test and environment print commands to target `DATABASE_URL`:
  ```bash
  kubectl exec -n production deployment/orderflow-api -- \
    python -c "import os, psycopg2; psycopg2.connect(os.getenv('DATABASE_URL'))"
  ```
  And:
  ```bash
  kubectl exec -n production deployment/orderflow-api -- printenv DATABASE_URL
  ```

---

## 2. Rolling Forward Instead of Rolling Back
* **Location**: Step 6 (Application Bug), line 2:
  - `helm upgrade orderflow deploy/charts/orderflow --namespace production --set image.tag=latest`
* **Operational Impact**: The command executes a new Helm upgrade with `image.tag=latest`. Since the CI/CD pipeline pushes the broken build as `latest`, this command simply redeploys the broken deployment. The outage continues, increasing MTTR (Mean Time to Resolution) under stress.
* **Correct Fix**: Use Helm's native revision rollback mechanism to revert to the previous stable release version:
  ```bash
  helm rollback orderflow --namespace production
  ```

---

## 3. Omission of Redis & Celery Worker Checks
* **Location**: Missing entire validation paths between Step 2 and Step 5.
* **Operational Impact**: The runbook never instructs the engineer to check Redis (port 6379) or the Celery worker deployment (`orderflow-worker`), despite Redis hosting the refund queue and caching layer. If Celery stops or Redis experiences an outage, refunds will silently backlog or API latency will spike, but the engineer following this runbook will check PostgreSQL or Auth, missing the root cause.
* **Correct Fix**: Insert a dedicated Redis and Worker health verification section:
  ```bash
  # Check if Redis is healthy (port 6379)
  kubectl get pods -n production -l app=redis
  
  # Check Celery worker log stack
  kubectl logs -n production deployment/orderflow-worker --tail=100
  ```
