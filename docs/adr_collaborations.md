# Architectural Decision Record (ADR): Real-Time Team Collaboration & Feeds

## Context and Problem Statement
The team collaboration feature requires a real-time updates mechanism for team activity feeds and comments. Users should immediately see new events, comments, and mentions without manually refreshing their client interface. Furthermore, access to these updates must respect strict security and team boundaries.

## Decision Drivers
1. **Low Latency**: Event distribution should occur in sub-second times to maintain a highly collaborative feel.
2. **Reduced Server Load**: Prevent continuous HTTP polling requests from clients.
3. **Robust Security Gating**: Enforce authentication and authorization checks at connection startup.
4. **Consistency**: Use existing dependency contexts (SQLAlchemy, API Keys registry, FastAPI) without introducing heavy message brokers (like Kafka or RabbitMQ) in the MVP/initial launch.

## Considered Alternatives

### Alternative 1: HTTP Polling (Short/Long Polling)
- **Pros**: Easy to implement; works completely over standard stateless HTTP request lifecycles.
- **Cons**: High network and CPU overhead due to repeating requests every few seconds; lacks instantaneous real-time delivery.

### Alternative 2: Server-Sent Events (SSE)
- **Pros**: Unidirectional streaming is easy to implement; uses standard HTTP connections.
- **Cons**: Harder to establish bidirectional communication (e.g. sending back heartbeats or status in-place); browser connection limits per domain (6 connections) without HTTP/2.

### Alternative 3: FastAPI WebSockets with Memory Connection Manager
- **Pros**: Bidirectional persistent connection; low latency; native FastAPI support; client-specific message delivery.
- **Cons**: Stateful connection management; state is local to the server process instance.

---

## Decision Outcome

**Chosen Option: Alternative 3 - WebSockets with Memory Connection Manager**

We selected FastAPI WebSockets coupled with a centralized memory Connection Manager (`app.services.activity_feed.activity_feed_manager`) to manage active client connections mapped by `team_id` and `user_id`.

### Implementation Details:
1. **Token Authentication**: Since browser WebSocket clients do not easily allow setting custom request headers, authentication is done by accepting the API Key via a `token` query parameter.
2. **Access Authorization**: A database query verifies the user is a member of the specific `team_id` before accepting the connection. Unauthorized requests are closed with code `1008 Policy Violation`.
3. **Centralized Broadcasts**: Event producers (e.g., the comment creation router) trigger an asynchronous broadcast to all WebSocket instances associated with the target team.
4. **State Cleanup**: Disconnections are caught cleanly, ensuring stale WebSocket handles are evicted from the active mappings dictionary to prevent memory leaks.

---

## Authorization & Role-Based Access Control (RBAC) Model

We established a strict 4-tier Role-Based Access Control (RBAC) matrix for team collaboration, implemented inside router dependencies:

| Role | Actions Permitted |
| :--- | :--- |
| **Owner** | All operations (Manage memberships, Roles updates including ownership transfer, Delete team, Invitations, Comments CRUD, Read Activity Feed) |
| **Admin** | Manage memberships, Roles updates (cannot promote anyone to Owner or modify Owner), Delete team, Invitations, Comments CRUD, Read Activity Feed |
| **Member** | Comments CRUD, Read Activity Feed (cannot invite, change roles, or delete team) |
| **Viewer** | Read-only details, Read comments, Read Activity Feed (cannot comment or edit/modify anything) |

### Key Security Decisions:
- **Viewer Protection**: Endpoints checking writes verify membership roles. Viewers are blocked from posting comments (`POST /threads/{id}/comments` raises `403 Forbidden`).
- **IDOR Protection**: The system checks resource ownership (e.g. only comment authors can update/delete comments, and only users matching the recipient_id of a notification can update it).
- **Transactional Consistency**: All database writes are wrapped in try-except statements with `db.rollback()` on exceptions to keep the database in a clean state.
