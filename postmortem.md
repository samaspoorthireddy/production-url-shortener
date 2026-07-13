# Incident Postmortem: Silent Order Drops in OrderProcessor Service

## Summary
On Wednesday afternoon, a two-hour incident impacted the `OrderProcessor` service between 14:00 and 16:02 UTC. A deployment removing a deprecated configuration parameter triggered a silent failure in the order creation flow. This resulted in approximately 1,400 customer orders being charged but dropped without creation or confirmation, affecting an estimated $186,000 in revenue. The service was restored by executing a manual rollback, and all dropped orders were successfully reprocessed from payment gateway logs.

---

## Timeline (all times UTC)
- **14:00** -- Deployment of `OrderProcessor v2.14` goes live in production. This release includes a configuration change removing the deprecated `warehouse_routing` parameter.
- **14:00 - 14:22** -- System metrics appear normal. The deployment dashboard reports green status, service health checks pass, and HTTP response codes return 200 OK.
- **14:22** -- Customers begin posting on social media regarding missing order confirmation emails. Support tickets start arriving in the customer support queue.
- **14:23** -- A customer support agent flags the customer complaints in the `#cs-escalations` Slack channel.
- **14:38** -- A second wave of support tickets arrives. The on-call engineer begins an investigation, having previously assumed the issue was a generic email delivery delay.
- **14:42** -- The on-call engineer inspects the monitoring dashboard. Latency, resource utilization (CPU and memory), and HTTP response codes are all normal (returning 200 OK).
- **14:55** -- The on-call engineer queries the production database directly and discovers no new orders have been written since 14:00 UTC.
- **15:02** -- The on-call engineer identifies the v2.14 deployment as the likely trigger and attempts an automated rollback.
- **15:08** -- The automated rollback fails. The rollback script references outdated deployment artifact paths due to an untested infrastructure migration completed four months prior.
- **15:15** -- The on-call engineer escalates the issue to the platform team to execute a manual rollback.
- **15:34** -- The platform team completes a manual rollback to `OrderProcessor v2.13`. Database queries verify that new orders have begun processing successfully.
- **15:45** -- The engineering team begins manually reprocessing the 1,400 dropped orders from the payment processor logs.
- **16:02** -- All dropped orders are successfully reprocessed, confirmation emails are sent, and the incident is declared fully resolved.

---

## Five-Whys Analysis
1. **Symptom:** Customers were charged for checkout transactions, but orders were silently dropped.
   - *Why?* The `OrderProcessor` service failed to write orders to the database while still returning `200 OK` and a success screen to clients.
2. **Why?** A missing configuration field (`warehouse_routing`) caused order creation database writes to fail, and this database error was caught in a broad `try/except` block that swallowed the exception, logged a DEBUG warning, and returned a success code to the user.
   - *Why?* The `warehouse_routing` field was completely removed from the configuration in `v2.14`, but the database write logic in `v2.13` still required it.
3. **Why?** The staging and production configuration schemas were out of sync; staging had never configured the `warehouse_routing` field, so the code change passed all pre-release staging tests without error.
   - *Why?* There was no automated mechanism to validate config schema compatibility between code changes and the target environment before deployment.

---

## Root Causes
1. **Broad Exception Swallowing:** The `OrderProcessor` logic caught critical order persistence database failures in a generic `try/except` block. It logged the failure as a low-priority DEBUG message rather than raising a critical exception. This caused the system to return a misleading `200 OK` success response to clients despite the transaction failing.
2. **Configuration Environment Mismatch:** The staging and production configuration schemas were completely out of sync. Staging had never populated the `warehouse_routing` field, masking the dependency error during pre-release testing.
3. **Lack of Business Metric Monitoring:** The monitoring and alerting systems only checked infrastructure health indicators (HTTP status codes, latency, resource utilization). They did not track core business metrics, such as the volume of orders successfully created per minute.

---

## Contributing Factors
1. **Escalation and Response Delay:** The initial support escalation was dismissed by the on-call engineer as a known email delivery delay, which delayed the investigation by 15 minutes.
2. **Untested Rollback Automation:** The automated rollback scripts referenced outdated path structures because the automation was not tested or updated after the infrastructure migration four months ago. This added 26 minutes of downtime.
3. **Incomplete Deprecation Verification:** The configuration parameter was removed from the deployment environment without verifying that all active code references to that parameter had been removed.

---

## Action Items
1. **Refactor Error Handling in Order Pipeline**
   - **Description:** Remove the broad catch-all exception block in `OrderProcessor` order creation. Ensure database write failures abort the transaction, throw a `500 Internal Server Error` to the client, and log a CRITICAL alert.
   - **Owner:** Backend Engineering Lead
   - **Deadline:** June 25, 2026
   - **Definition of Done:** Unit tests verify that a database write failure throws a 500 error code and fails the checkout flow.

2. **Add CI/CD Backwards-Compatibility Check**
   - **Description:** Add a backwards-compatibility check to the CI pipeline that fails the build if a configuration field is removed while any running service version still references it.
   - **Owner:** Platform Team Lead
   - **Deadline:** July 10, 2026
   - **Definition of Done:** CI pipeline successfully flags and blocks a PR that attempts to delete a config field still referenced in any active release.

3. **Pre-Deploy Checklist Integration**
   - **Description:** Add a required pre-deploy checklist in the deployment tool that blocks deployment until config compatibility is confirmed.
   - **Owner:** Deployment Tooling Owner
   - **Deadline:** July 15, 2026
   - **Definition of Done:** The deploy tool prevents clicking 'Deploy' until compatibility checklists are completed.

4. **Transaction Monitoring and Alerting**
   - **Description:** Add an orders-per-minute metric with an alert that fires to `#ops-alerts` when the rate drops below the trailing-7-day average by more than 50% for 5 minutes.
   - **Owner:** On-Call Rotation Owner
   - **Deadline:** June 20, 2026
   - **Definition of Done:** Alert fires successfully during a simulated low-traffic test run in staging, sending a slack notification to `#ops-alerts`.

5. **Rollback Verification and Dry-Runs**
   - **Description:** Platform team will audit and test all rollback scripts monthly; add a rollback dry-run step to the deploy pipeline.
   - **Owner:** Platform Team Lead
   - **Deadline:** July 5, 2026
   - **Definition of Done:** Rollback dry-run step completes successfully in the deployment pipeline, and the platform team logs the first monthly script verification test.

6. **Automated Configuration Diff Analysis**
   - **Description:** Require automated config-diff analysis in the PR pipeline that flags removed or renamed fields.
   - **Owner:** Platform Team Lead
   - **Deadline:** June 30, 2026
   - **Definition of Done:** PR checks show a config diff report block indicating any modified configuration parameters.

---

## Lessons Learned
- **What surprised the team:** We were surprised that the service could report 100% green health checks and low latencies while failing to perform its primary business logic.
- **What worked well:** The platform team manually rolled back the release rapidly once escalated, and the team reprocessed all 1,400 orders from logs with no permanent data or financial loss.
- **What we would do differently next time:** If a silent drop is suspected, we will immediately query the database to verify active order counts rather than relying on HTTP metrics. We will also perform sanity checks of the rollback scripts before deploying changes with high blast radius.
