# Postmortem: Service Instability and Security Bypass (Auth Bypass & Connection Starvation)

## Summary
On June 3, 2026, two distinct incidents impacted the URL Shortener service. First, an authentication bypass vulnerability in the admin API allowed unauthorized requests to delete 12 short links over a 10-minute window (14:15–14:25 UTC). Second, a background task retry storm starved the API's PostgreSQL connection pool, causing total service unresponsiveness for approximately 3 minutes (15:00–15:03 UTC). Both issues were resolved by applying strict boundary validation, database pool configuration limits, and background worker backoff policies, with no permanent data loss.

## Timeline (all times UTC)
- **14:15** -- Monitoring alert fires: anomalous admin API access pattern detected (high volume of DELETE requests from unrecognized IP addresses).
- **14:17** -- On-call engineer begins investigation and verifies that short links are being deleted without valid API keys.
- **14:22** -- Initial status update dispatched to VP of Engineering.
- **14:25** -- Root cause identified: an empty or whitespace-only `Authorization` header bypassed the truthy check in the authentication middleware.
- **14:28** -- Fix (rejecting empty/whitespace headers) deployed to staging and successfully verified.
- **14:32** -- Fix deployed to production; unauthorized admin API access attempts are blocked with 401 Unauthorized.
- **14:35** -- Restored the 12 deleted short links from the most recent database backup.
- **15:00** -- Internal API latency spikes; automated monitoring alerts fire for 504 Gateway Timeouts and database connection pool saturation.
- **15:03** -- On-call engineer receives page and initiates database connection state analysis.
- **15:05** -- Root cause identified: background queue worker is in an infinite retry storm on failed tasks, exhausting all available PostgreSQL connections.
- **15:08** -- Temporary mitigation applied: background worker process scaled down to 0, immediately freeing database connections for the API.
- **15:12** -- Permanent fix deployed: set strict connection pool bounds, configured Celery task retry limits, and added exponential backoff.
- **15:15** -- Background worker scaled back up; queue successfully drains and system latency returns to baseline.

## Root Cause
1. **Authentication Bypass**: The authentication middleware implemented a naive falsy check (`if not header` or equivalent). Because empty headers (e.g. `Authorization: ` or whitespace values) evaluate as a present but empty string, they passed this check. The middleware then attempted to validate the key against a storage/database lookup that treated empty keys as valid or matching empty credentials, bypassing authentication.
2. **Database Connection Starvation**: The Celery background tasks had no maximum retry limits or backoff policies. When a task failed (e.g., due to a temporary network blip or lock), it retried immediately and infinitely. Simultaneously, the database configuration lacked a cap on connection pool sizes. This allowed the background worker to spawn unbounded database connections during a retry storm, completely exhausting the PostgreSQL connection pool and starving the API server of connections.

## Contributing Factors
1. **Testing Gap**: The integration test suite lacked negative boundary value test coverage for security-critical middleware, including tests verifying behavior with empty, whitespace-only, and malformed authorization headers.
2. **Missing Lint/Static Analysis Guardrails**: The CI/CD pipeline did not incorporate SAST (Static Application Security Testing) or security-focused linter rules that automatically flag naive falsy checks (`if not header`) on critical security parameters.
3. **Absence of Rate Limiting**: The admin API endpoints lacked rate-limiting policies, allowing the unauthorized attacker to execute 47 destructive delete requests within a 10-minute window without triggering automated request throttling.
4. **Unbounded Connection/Retry Configurations**: The database pool settings did not define maximum limits on connection sizes, and the background task framework (Celery) default settings permitted infinite retries without exponential backoff or jitter.
5. **Inadequate Alerting**: Anomaly detection was not configured for administrative actions (e.g., sudden spike in link deletions), delaying manual intervention until after 12 links had already been deleted.

## Impact
- **Duration**: Auth bypass active exploitation lasted 10 minutes; database pool starvation caused 3 minutes of total API downtime.
- **Users affected**: All active API clients experienced 504 timeouts during the 3-minute database starvation window. A subset of users (owners of the 12 deleted links) experienced broken redirects until the backup was restored.
- **Data affected**: 12 short links were temporarily deleted; all 12 links were successfully recovered from backups with 100% data integrity restored.

## Resolution
1. **Auth Bypass Fix**: Patched the authentication middleware to strip header values and reject any empty, whitespace-only, or malformed authorization headers with an immediate 401 Unauthorized response.
2. **Connection Pool Fix**: Configured strict database connection pool bounds (`max_overflow`, `pool_size`, `connect_timeout=5`) and updated the background task queue settings to enforce a maximum of 5 retries with exponential backoff and jitter.

## Remediation Items
| # | Action | Owner | Deadline | Status |
|---|--------|-------|----------|--------|
| 1 | Add integration tests for authentication middleware covering empty string, null, undefined, and malformed header values. | Backend Team | End of Sprint 12 | Open |
| 2 | Integrate security-focused SAST tools (e.g., Bandit, Semgrep) into the GitHub Actions CI pipeline to flag naive falsy validation checks. | Platform Team | End of Sprint 13 | Open |
| 3 | Implement rate-limiting middleware on all admin API endpoints to restrict requests to a maximum of 10 requests per minute per IP address. | Backend Team | End of Sprint 12 | Open |
| 4 | Configure strict PostgreSQL connection pool limits and Celery queue task retry limits with exponential backoff across all microservices. | SRE Team | End of Sprint 12 | Open |
| 5 | Establish anomaly detection alerts in Prometheus/Grafana to trigger PagerDuty alerts if admin API write operations exceed 5 actions per minute. | SRE Team | End of Sprint 13 | Open |

## Lessons Learned
- **What went well?**: 
  - Automated monitoring alerts correctly caught anomalous traffic and database saturation early.
  - The database backup restore procedure was documented and functioning, permitting complete recovery of deleted links within 17 minutes.
- **What went poorly?**:
  - The lack of defense-in-depth (missing rate limits, SAST checks, and database pool controls) allowed simple mistakes to escalate into security breaches and service outages.
  - The background worker's infinite loop behavior was not caught in the local development or staging environment due to different connection limits.
- **Where did we get lucky?**:
  - The unauthorized attacker only deleted 12 links instead of performing a bulk deletion of all links in the database.
  - The database backup was highly recent, preventing any data/progress loss for the affected link owners.
