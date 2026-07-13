# Module 02 - Decomposed Task Tree: Team Collaboration Feature

This document presents the complete task tree for the Team Collaboration features, focusing on comments, threads, and @mentions, designed under **Option B (Progressive Decomposition)** with a **Medium-Grained** granularity (no task exceeding 150 lines of code).

---

## Part 1: The Task Tree (9 Atomic Tasks)

```
             ┌────────────────────────────────────────────────────────┐
             │  Task 1: Team & User Database Models and Migrations    │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 2: Team CRUD & Membership API Endpoints          │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 3: Comment & Thread Database Models and Migr.    │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 4: Comment API Endpoints (Add, Edit, Fetch)      │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 5: @Mention Regex Extraction Utility             │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 6: @Mention Processor & Notification Handler     │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 7: Notification Database Model & Migration       │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 8: Notification API Endpoints (List & Mark Read)  │
             └───────────────────────────┬────────────────────────────┘
                                         │
                                         ▼
             ┌────────────────────────────────────────────────────────┐
             │  Task 9: Audit Logging for Collaborative Events        │
             └────────────────────────────────────────────────────────┘
```

### Task 1: Create Database Models and Migrations for Team & UserTeam
- **Task Description**: Define the SQLAlchemy database models for `Team` and the `UserTeam` association table to handle team ownership and role-based memberships (Admin, Member, Viewer).
- **Input Context**: [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py), [database.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/database.py)
- **Expected Output**: Updated `models.py` containing `Team` and `UserTeam` models, and migration statements added to startup table generation if necessary.
- **Acceptance Criteria**:
  - PostgreSQL schema contains `teams` and `user_teams` tables.
  - Foreign key constraint is set from `user_teams.team_id` to `teams.id` with `ondelete="CASCADE"`.
  - Roles column in `user_teams` is restricted to "admin", "member", or "viewer".
- **Dependencies**: None (Foundational Task).

### Task 2: Implement Team CRUD and Membership API Endpoints
- **Task Description**: Add routes to manage teams (Create, Read, Update, Delete) and team memberships (Add/Remove members, Update member roles).
- **Input Context**: [main.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/main.py), [app/dependencies.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/dependencies.py), Task 1 outputs.
- **Expected Output**: A new router file `app/routers/teams.py` registered in `main.py`.
- **Acceptance Criteria**:
  - `POST /teams` creates a team and automatically assigns the creator as "owner" and "admin".
  - `GET /teams/{team_id}` returns team details for authorized members.
  - `POST /teams/{team_id}/members` adds a member (restricted to Admin/Owner).
  - Validation: API returns `403 Forbidden` if a member tries to add others without admin role.
- **Dependencies**: Task 1.

### Task 3: Create Comment & Thread Database Models and Migrations
- **Task Description**: Define the SQLAlchemy models for discussion threads and individual comments. Threads are linked to a target object (e.g., a Task, Post, or the existing `Link` entity).
- **Input Context**: [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py), Task 1 outputs.
- **Expected Output**: Updated `models.py` with `CommentThread` and `Comment` models.
- **Acceptance Criteria**:
  - `CommentThread` table has: `id` (Integer PK), `target_type` (String, e.g. "link"), `target_id` (Integer), `created_at` (DateTime).
  - `Comment` table has: `id` (Integer PK), `thread_id` (ForeignKey to `comment_threads.id` on cascade delete), `user_id` (String representing user_id), `content` (Text, required), `created_at` and `updated_at`.
- **Dependencies**: Task 2.

### Task 4: Implement Comment API Endpoints (Add, Edit, Fetch)
- **Task Description**: Implement endpoint routes to add a comment to a thread, edit a comment's content, and fetch all comments in a thread in chronological order.
- **Input Context**: `app/routers/comments.py`, Task 3 outputs, [app/dependencies.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/dependencies.py).
- **Expected Output**: A new router file `app/routers/comments.py` registered in `main.py`.
- **Acceptance Criteria**:
  - `POST /threads/{thread_id}/comments` adds a new comment to the thread and returns status 201.
  - `PATCH /comments/{comment_id}` edits comment text. Returns `403 Forbidden` if another user attempts to edit it.
  - `GET /threads/{thread_id}/comments` retrieves all comments sorted by `created_at` ASC.
- **Dependencies**: Task 3.

### Task 5: Implement @Mention Regex Extraction Utility
- **Task Description**: Write a pure, tested utility function to parse a comment string and extract all unique @usernames.
- **Input Context**: None (independent utility).
- **Expected Output**: A new utility file `app/services/mention_service.py` containing the regex extraction function.
- **Acceptance Criteria**:
  - Correctly extracts "@user_a" from `"Hello @user_a and @user_b!"` -> `["user_a", "user_b"]`.
  - Ignores invalid formats (e.g., email addresses `test@domain.com` or double-@ `@@user`).
  - Unit tests verifying typical text, punctuation boundaries, empty strings, and duplicate mentions.
- **Dependencies**: Task 4.

### Task 6: Implement @Mention Processor & Notification Handler
- **Task Description**: Create the service layer function that processes extracted @usernames, verifies them against the registered users, and calls the notification recorder.
- **Input Context**: `app/services/mention_service.py`, [app/dependencies.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/dependencies.py), Task 5 outputs.
- **Expected Output**: Updated `app/services/mention_service.py` with the mention handling service method.
- **Acceptance Criteria**:
  - Integration with user registry lookup (matching `API_KEYS.values()` values `"user_a"`, `"user_b"`).
  - **Edge Case (unknown users)**: If a comment mentions `@unknownuser`, the registry lookup fails, and the system **silently ignores** the username. No exception is thrown, no notification is written, and execution proceeds for any valid users in the list.
- **Dependencies**: Task 5.

### Task 7: Create Notification Database Model and Migration
- **Task Description**: Define the database schema for user notifications, linking them to comments, threads, and the recipient user.
- **Input Context**: [models.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/models.py), Task 6 outputs.
- **Expected Output**: Updated `models.py` containing the `Notification` model.
- **Acceptance Criteria**:
  - `notifications` table has columns: `id` (Integer PK), `recipient_id` (String user identifier, nullable=False), `comment_id` (ForeignKey to comments, nullable=False), `is_read` (Boolean, default=False), `created_at` (DateTime).
- **Dependencies**: Task 6.

### Task 8: Implement Notification API Endpoints (List & Mark Read)
- **Task Description**: Create API routes for users to fetch their own notifications and mark them as read.
- **Input Context**: New router `app/routers/notifications.py`, [app/dependencies.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/app/dependencies.py), Task 7 outputs.
- **Expected Output**: New router `app/routers/notifications.py` registered in `main.py`.
- **Acceptance Criteria**:
  - `GET /notifications` returns a JSON list of unread notifications for the currently logged-in user (from `get_current_user`).
  - `PATCH /notifications/{notification_id}/read` marks the notification as read.
  - Users can only mark their own notifications as read (returns `403 Forbidden` otherwise).
- **Dependencies**: Task 7.

### Task 9: Implement Event/Audit Logging for Collaborative Activities
- **Task Description**: Log critical team collaboration activities to the server-side audit logs for compliance tracking.
- **Input Context**: [main.py](file:///Users/spoorthireddy/.gemini/antigravity/scratch/url-shortener/main.py), across routers.
- **Expected Output**: Structured log messages emitted via Python standard logging to the default log file.
- **Acceptance Criteria**:
  - Creating a team, adding a member, posting comments, and triggering a valid @mention emit a structured log line containing: `timestamp`, `user_id`, `action`, `target_id`, and `metadata`.
- **Dependencies**: Task 8.

---

## Part 2: The First 3 Production-Grade Prompts

### Prompt 1: Create Database Models and Migrations for Team & UserTeam (Task 1)

```text
Please implement the database models for Teams and User-Team memberships in the FastAPI codebase.

1. CONTEXT TO REFERENCE:
- models.py: Follow the SQLAlchemy conventions used for the `Link` and `ClickEvent` models.
- database.py: Use the declared `Base` class for declarative models.

2. TARGETS & CHANGES:
Modify models.py to define the following two models:

A. Class `Team(Base)`:
- __tablename__ = "teams"
- id: Column(Integer, primary_key=True, index=True, autoincrement=True)
- name: Column(String(100), index=True, nullable=False)
- description: Column(Text, nullable=True)
- owner_id: Column(String(255), index=True, nullable=False)
- created_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
- updated_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
- Setup a back_populates relationship to UserTeam named "memberships" with cascade="all, delete-orphan".

B. Class `UserTeam(Base)`:
- __tablename__ = "user_teams"
- id: Column(Integer, primary_key=True, index=True, autoincrement=True)
- user_id: Column(String(255), index=True, nullable=False)
- team_id: Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
- role: Column(String(30), nullable=False, default="member") # Must be restricted via SQLAlchemy validation or validation logic to "admin", "member", or "viewer"
- joined_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
- Setup a back_populates relationship to Team named "team".

Add the new models to models.py. Ensure imports for `datetime` and `timezone` are present. Do not use external database migration tools; the tables will be created automatically via Base.metadata.create_all.

3. CONSTRAINTS:
- Do not install new third-party packages.
- Ensure all datetimes are timezone-aware using timezone.utc.
```

### Prompt 2: Implement Team CRUD and Membership API Endpoints (Task 2)

```text
Please implement a new API router for Teams and Team Memberships.

1. CONTEXT TO REFERENCE:
- app/dependencies.py: Use `get_current_user` to authenticate requests and retrieve the active username string.
- models.py: Query the newly added `Team` and `UserTeam` models.
- database.py: Use the `get_db` session dependency.

2. TARGETS & CHANGES:
Create a new file `app/routers/teams.py` and register it in `main.py` with prefix `/teams` and tags=["teams"].

Implement the following REST API endpoints in the new router:

A. POST /teams/
- Request Body: JSON with `name` (string, required) and `description` (string, optional).
- Action: Create a new Team record in the database. Also, insert an entry in the user_teams table setting the authenticated user (retrieved via `get_current_user`) as owner_id on the team, and with role="admin" on the membership.
- Response: HTTP 201 Created with the created Team JSON object.

B. GET /teams/{team_id}
- Action: Query the team by ID. Verify that the authenticated user is listed in user_teams for this team.
- Response: HTTP 200 OK with Team details. If the user is not a member, return HTTP 403 Forbidden. If the team does not exist, return HTTP 404 Not Found.

C. POST /teams/{team_id}/members
- Request Body: JSON with `user_id` (string, required) and `role` (string, default "member").
- Action: Verify that the current user exists in user_teams with role="admin" (or is the team owner). If true, add the target user_id to user_teams with the specified role.
- Response: HTTP 201 Created. If the requester is not an admin/owner of the team, return HTTP 403 Forbidden.

3. CONSTRAINTS:
- Write explicit input validation schemas using Pydantic.
- Handle database exceptions and ensure sessions are closed cleanly.
```

### Prompt 3: Create Comment & Thread Database Models and Migrations (Task 3)

```text
Please implement the database models for Discussion Threads and Comments in the FastAPI codebase.

1. CONTEXT TO REFERENCE:
- models.py: Reference existing tables and relationships.
- database.py: Use the declarative `Base` class.

2. TARGETS & CHANGES:
Modify models.py to define the following two models:

A. Class `CommentThread(Base)`:
- __tablename__ = "comment_threads"
- id: Column(Integer, primary_key=True, index=True, autoincrement=True)
- target_type: Column(String(50), nullable=False) # e.g. "link" or "task"
- target_id: Column(Integer, nullable=False)
- created_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
- Setup a back_populates relationship to Comment named "comments" with cascade="all, delete-orphan".

B. Class `Comment(Base)`:
- __tablename__ = "comments"
- id: Column(Integer, primary_key=True, index=True, autoincrement=True)
- thread_id: Column(Integer, ForeignKey("comment_threads.id", ondelete="CASCADE"), nullable=False)
- user_id: Column(String(255), index=True, nullable=False)
- content: Column(Text, nullable=False)
- created_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
- updated_at: Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
- Setup a back_populates relationship to CommentThread named "thread".

Ensure all imports are clean and there are no circular dependencies.

3. CONSTRAINTS:
- Do not add any columns beyond those specified.
- Ensure proper cascaded deletion so deleting a thread automatically purges all child comments.
```

---

## Part 3: Critical Path & Risk Assessment

### 1. Critical Path Analysis
The critical path is defined by the longest sequence of sequential dependencies:
$$\text{Task 1} \longrightarrow \text{Task 2} \longrightarrow \text{Task 3} \longrightarrow \text{Task 4} \longrightarrow \text{Task 5} \longrightarrow \text{Task 6} \longrightarrow \text{Task 7} \longrightarrow \text{Task 8} \longrightarrow \text{Task 9}$$

Because models and relationships must exist in the database before endpoints can read/write to them, database changes are always on the critical path. Similarly, comment retrieval and creation APIs (Task 4) must be implemented before the regex mention parser can trigger against actual user comments (Task 5, 6) to create notifications. 

### 2. The Riskiest Task
**Task 6: @Mention Processor & Notification Handler** is identified as the riskiest task in this feature.
- **Why**: It bridges regex parser outputs with data queries and transactional writes. It contains the business rules defining who should be notified and how invalid mentions are resolved.
- **Mitigation Strategy**: We will isolate the registry lookup from the notification creation logic. We will explicitly test the registry boundary with unit tests feeding valid usernames (`"user_a"`, `"user_b"`) and non-existent usernames (`"@unknownuser"`, `"@doesnotexist"`) to verify that invalid users are filtered out and that the database transaction completes cleanly without raising any integrity errors or server faults.

---

## Part 4: Interface Contracts

### Contract: Task 1 (Database Models) to Task 2 (Team API Endpoints)

#### Task 1 (Upstream) Produces:
- `Team` model mapped to table `teams`:
  - Columns: `id` (Integer PK), `name` (String(100)), `description` (Text), `owner_id` (String(255)), `created_at` (DateTime), `updated_at` (DateTime).
  - Relationship `memberships` linking to `UserTeam` with cascade delete.
- `UserTeam` model mapped to table `user_teams`:
  - Columns: `id` (Integer PK), `user_id` (String(255)), `team_id` (Integer FK to `teams.id`), `role` (String(30)), `joined_at` (DateTime).
  - Validation: Role column validation enforcing only values in `{"admin", "member", "viewer"}`.

#### Task 2 (Downstream) Expects:
- `teams` and `user_teams` tables exist and are accessible via SQLAlchemy.
- Creating a team is transaction-guaranteed: inserting the `Team` and adding the creator to `UserTeam` as `"admin"` must be completed inside the same database transaction.
- Role checking is validated both at the Pydantic schema level (`TeamMemberAdd` request body) and enforced at the database layer.

#### Shared Agreement:
- The `role` values and field names match exactly. Any transaction failure (e.g. database connection or integrity violation) triggers a database rollback and returns a clean HTTP 500 error to the client.

