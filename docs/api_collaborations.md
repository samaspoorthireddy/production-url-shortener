# Team Collaboration Features API Specification

This document provides the complete API specifications for the Team Collaboration features, including Team Management, Invitations, Comments, Notifications, and the real-time WebSocket Activity Feed.

---

## 1. Authentication
All HTTP requests require authentication via the custom header:
- Header Name: `X-API-Key`
- Description: Valid static API key registered in the system (e.g. `API_KEY_A` -> `user_a`).
- Failure response: `401 Unauthorized` with error structure:
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid API Key provided.",
    "request_id": "req-uuid"
  }
}
```

---

## 2. Teams Endpoint (`/teams`)

### Create a Team
- **Method**: `POST`
- **Path**: `/teams/`
- **Request Body Schema**:
  - `name`: string (1-100 characters, required, stripped)
  - `description`: string (optional)
- **Response**: `201 Created`
```json
{
  "id": 1,
  "name": "DevOps Team",
  "description": "Infrastructure and Pipelines",
  "owner_id": "user_a",
  "created_at": "2026-06-08T12:00:00Z",
  "updated_at": "2026-06-08T12:00:00Z"
}
```

### Delete a Team
- **Method**: `DELETE`
- **Path**: `/teams/{team_id}`
- **Permissions**: Requester must be the Team Owner or a Team Administrator.
- **Response**: `200 OK`
```json
{
  "status": "deleted"
}
```

### Add a Member Directly
- **Method**: `POST`
- **Path**: `/teams/{team_id}/members`
- **Permissions**: Requester must be Owner or Admin.
- **Request Body Schema**:
  - `user_id`: string (required)
  - `role`: string (one of `admin`, `member`, `viewer`, required)
- **Response**: `201 Created`
```json
{
  "id": 5,
  "user_id": "user_b",
  "team_id": 1,
  "role": "member",
  "joined_at": "2026-06-08T12:05:00Z"
}
```

### Update Member Role
- **Method**: `PUT`
- **Path**: `/teams/{team_id}/members/{user_id}`
- **Permissions**: 
  - Owner can update any role (including promoting to Owner).
  - Admin can update members/viewers to other roles but NOT promote anyone to Owner.
  - A member cannot modify their own role.
- **Request Body Schema**:
  - `role`: string (one of `owner`, `admin`, `member`, `viewer`, required)
- **Response**: `200 OK`
```json
{
  "id": 5,
  "user_id": "user_b",
  "team_id": 1,
  "role": "admin",
  "joined_at": "2026-06-08T12:05:00Z"
}
```

### Remove Member / Leave Team
- **Method**: `DELETE`
- **Path**: `/teams/{team_id}/members/{user_id}`
- **Permissions**:
  - Owner or Admin can remove members.
  - Any member can delete their own membership to leave the team (except owners, who must transfer ownership first).
- **Response**: `200 OK`
```json
{
  "status": "removed"
}
```

---

## 3. Team Invitations (`/teams/{team_id}/invitations`)

### Invite to Team
- **Method**: `POST`
- **Path**: `/teams/{team_id}/invitations`
- **Permissions**: Requester must be Owner or Admin.
- **Request Body Schema**:
  - `email`: string (valid email format, required)
  - `role`: string (one of `admin`, `member`, `viewer`, required)
- **Response**: `201 Created` (returns generated 24-hour token)
```json
{
  "id": 3,
  "team_id": 1,
  "email": "user_b@example.com",
  "role": "member",
  "token": "4a7b8c...",
  "status": "pending",
  "created_at": "2026-06-08T12:10:00Z",
  "expires_at": "2026-06-09T12:10:00Z"
}
```

### Accept Invitation
- **Method**: `POST`
- **Path**: `/teams/invitations/accept`
- **Request Body Schema**:
  - `token`: string (required)
- **Response**: `200 OK`
```json
{
  "id": 8,
  "user_id": "user_b",
  "team_id": 1,
  "role": "member",
  "joined_at": "2026-06-08T12:15:00Z"
}
```

---

## 4. Comments & Threads

### Create or Retrieve Comment Thread
- **Method**: `POST`
- **Path**: `/threads`
- **Request Body Schema**:
  - `target_type`: string (either `team` or `link`, required)
  - `target_id`: integer (required)
- **Response**: `200 OK` (if already exists) or `201 Created` (if new)
```json
{
  "id": 10,
  "target_type": "team",
  "target_id": 1,
  "created_at": "2026-06-08T12:20:00Z"
}
```

### Add Comment to Thread
- **Method**: `POST`
- **Path**: `/threads/{thread_id}/comments`
- **Permissions**: Viewer role cannot add comments.
- **Request Body Schema**:
  - `content`: string (1-5000 chars, required, stripped)
- **Response**: `201 Created`
```json
{
  "id": 42,
  "thread_id": 10,
  "user_id": "user_b",
  "content": "Hey @user_a! Let's check the pipeline logs.",
  "created_at": "2026-06-08T12:21:00Z",
  "updated_at": "2026-06-08T12:21:00Z"
}
```

### Fetch Comments
- **Method**: `GET`
- **Path**: `/threads/{thread_id}/comments`
- **Response**: `200 OK`
```json
[
  {
    "id": 42,
    "thread_id": 10,
    "user_id": "user_b",
    "content": "Hey @user_a! Let's check the pipeline logs.",
    "created_at": "2026-06-08T12:21:00Z",
    "updated_at": "2026-06-08T12:21:00Z"
  }
]
```

### Edit Comment
- **Method**: `PATCH`
- **Path**: `/comments/{comment_id}`
- **Permissions**: Only the original comment author can edit.
- **Request Body Schema**:
  - `content`: string (1-5000 chars, required, stripped)
- **Response**: `200 OK`
```json
{
  "id": 42,
  "thread_id": 10,
  "user_id": "user_b",
  "content": "Hey @user_a! Log updates completed.",
  "created_at": "2026-06-08T12:21:00Z",
  "updated_at": "2026-06-08T12:25:00Z"
}
```

---

## 5. Notifications

### Fetch Unread Notifications
- **Method**: `GET`
- **Path**: `/notifications`
- **Response**: `200 OK`
```json
[
  {
    "id": 15,
    "recipient_id": "user_a",
    "comment_id": 42,
    "is_read": false,
    "created_at": "2026-06-08T12:21:00Z"
  }
]
```

### Mark Notification as Read
- **Method**: `PATCH`
- **Path**: `/notifications/{notification_id}/read`
- **Permissions**: Users can only mark their own notifications as read.
- **Response**: `200 OK`
```json
{
  "id": 15,
  "recipient_id": "user_a",
  "comment_id": 42,
  "is_read": true,
  "created_at": "2026-06-08T12:21:00Z"
}
```

---

## 6. Real-time WebSocket Activity Feed

- **URL Protocol/Scheme**: `ws://` or `wss://`
- **WebSocket Route**: `/teams/{team_id}/feed`
- **Query Parameters**:
  - `token`: Valid X-API-Key token (required, used to authenticate the WS connection)

### Connection Rules:
- Rejects connection with `1008 Policy Violation` if `token` query param is missing or invalid.
- Rejects connection with `1008 Policy Violation` if the authenticated user is not a member of the team.

### Feed Broadcast Payload format (JSON):
When collaborative events occur in the team (like posting comments), all active subscribers receive a JSON broadcast event:
```json
{
  "event": "comment_created",
  "user_id": "user_b",
  "team_id": 1,
  "timestamp": "2026-06-08T12:21:00.012345+00:00",
  "details": "New comment added by user_b in thread 10"
}
```
