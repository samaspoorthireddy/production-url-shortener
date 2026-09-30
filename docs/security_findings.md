# Prioritized Security & Architecture Findings

## 1. Summary of Findings

| Severity | Category | Description | Status |
|---|---|---|---|
| Critical | Security | PUT `/teams/:id/members/:uid` role escalation vulnerability | Fixed |
| Critical | Security | PUT `/teams/:id/members/:uid` missing input validation on `role` | Fixed |
| High | Security / IDOR | Missing admin check or author verification on comments mutation | Documented |
| Medium | Architecture | Error response format drift in AI-generated routes vs core | Documented |
| Medium | Test Coverage | Missing validation and permission test coverage mapping | Fixed (Tests Added) |
| Low | Architecture | Inconsistent naming conventions in generated websocket files | Documented |

---

## 2. Detailed Findings

### FINDING 1: Team Member Role Escalation Privilege Bypass
*   **Severity**: Critical
*   **Category**: Security
*   **Description**: The endpoint `PUT /teams/{team_id}/members/{user_id}` was not implemented with appropriate authorization checks. A member of a team could theoretically escalate roles of other members or modify membership details without admin or owner verification.
*   **Impact**: Any regular member of a team could escalate their own privilege or change other members' roles, leading to unauthorized team ownership/administration.
*   **Fix Plan**: Implement the route `PUT /teams/{team_id}/members/{user_id}` and add checks that the requester (`current_user`) is either the owner of the team or has an `"admin"` role in the team, throwing `403 Forbidden` if not.
*   **Status**: Fixed. Added verification logic and 4 test cases covering authorization behavior.

### FINDING 2: Missing Input Validation on Member Update Role
*   **Severity**: Critical
*   **Category**: Security / Data Integrity
*   **Description**: In updating member roles, the API was lacking a Pydantic input validation model check on the role string. Without this, arbitrary strings could be sent as a role parameter.
*   **Impact**: Users could potentially input arbitrary roles, leading to database pollution or bypassing role checks that assume role value is strictly `"admin"`, `"member"`, or `"viewer"`.
*   **Fix Plan**: Define a `TeamMemberUpdate` schema using Pydantic `field_validator` to enforce that the `role` is strictly one of `{"admin", "member", "viewer"}`.
*   **Status**: Fixed. `TeamMemberUpdate` schema is implemented and validated in the router handler.

### FINDING 3: Potential IDOR on Comments Mutations
*   **Severity**: High
*   **Category**: Security / IDOR
*   **Description**: Edit/delete operations on comments need to verify that `comment.authorId == userId` or the requester is an admin/owner of the team/thread to prevent Insecure Direct Object References.
*   **Impact**: Users could edit or delete comments posted by other team members if direct object permissions are not strictly enforced.
*   **Fix Plan**: Ensure comments route (e.g. `PATCH /comments/{id}`) retrieves comment by ID and checks authorship.
*   **Status**: Documented/Review.

### FINDING 4: Error Handling Format Drift
*   **Severity**: Medium
*   **Category**: Architecture
*   **Description**: Some AI-generated error handlers might return JSON response formats that differ from the core `{ "error": { "code": "...", "message": "...", "request_id": "..." } }` standard structure.
*   **Impact**: Consumers parsing response messages from the API will face parser failures or unhandled exceptions when requesting updated endpoints.
*   **Fix Plan**: Enforce `build_error_response` helper usage across all router endpoints.
*   **Status**: Documented.

### FINDING 5: Gaps in Role Management Test Coverage
*   **Severity**: Medium
*   **Category**: Test Coverage
*   **Description**: Gaps existed in testing role permissions and validations around team modifications.
*   **Impact**: Regression bugs in security gates could be introduced without failing unit tests.
*   **Fix Plan**: Add test cases for owner authorization, regular member rejection, and role validators.
*   **Status**: Fixed. Added detailed tests in `tests/test_teams.py`.
