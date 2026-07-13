# Rollback & Recovery Plan: Team Collaboration Feature

In the event of a critical regression, authorization bypass, or resource exhaustion issue discovered in production after deploying the Team Collaboration features, the following procedures must be followed.

---

## 1. Quick Revert (Rollback) Strategy

### Scenario A: Reverting the Deployment
Since our deployment strategy packages the application inside a Docker container:
- **Action**: Redeploy the previous stable Docker image tag (e.g., the commit SHA tag prior to this merge).
- **Process**: Trigger the deployment pipeline pointing to the previous image SHA, or manually update the container runner / Kubernetes manifest to refer to the last known good image.
- **Estimated Time**: < 3 minutes.
- **Data Backwards Compatibility**: The new tables (`comment_threads`, `comments`, `notifications`, `team_invitations`) are purely additive. Reverting the application code to a version that does not reference these tables will immediately stop reads/writes to them without breaking any existing legacy features (like core link shortening).

---

## 2. Database Schema Rollback / Migration

Because our system uses SQLAlchemy's `Base.metadata.create_all()` at startup:
- **Migration Engine**: We do not currently use Alembic for versioned migrations; tables are created dynamically if they do not exist.
- **Reverting Schema Changes**:
  - Dropping the additive tables is **not** required for a rollback, as the older code version simply ignores them.
  - **WARNING**: Do NOT drop any database tables unless specifically instructed by a DBA, to preserve any user comments or invitation tokens created during the brief window the new code was live.
- **Forward-Fix Strategy**:
  - If a schema defect is identified, a hotfix patch must be built, tested, and rolled out.
  - If a hard rollback of the schema is absolutely required, the rollback must be performed via a manual migration script executing `DROP TABLE` statements in dependency order:
    ```sql
    DROP TABLE IF EXISTS notifications;
    DROP TABLE IF EXISTS comments;
    DROP TABLE IF EXISTS comment_threads;
    DROP TABLE IF EXISTS team_invitations;
    ```

---

## 3. Communication & Escalation Path

If a rollback is executed:
1. **Notify Tech Lead**: immediately notify the Tech Lead / Engineering Manager of the rollback decision.
2. **Channel Notification**: Post a summary in the `#ops-alerts` Slack/Teams channel:
   ```text
   [ALERT] Rollback executed for url-shortener service to version <PREVIOUS_SHA>.
   Reason: <Brief description of regression, e.g., memory leak on WebSockets / Auth bypass>.
   Impact: Team Collaboration features temporarily disabled. Core link shortening remains unaffected.
   ```
3. **Post-Mortem**: File an incident report detailing the root cause and the test gap that allowed the bug to bypass CI.
