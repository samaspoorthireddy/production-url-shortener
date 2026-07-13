import pytest
from app.dependencies import API_KEYS

# Register keys for testing
API_KEYS["API_KEY_A"] = "user_a"
API_KEYS["API_KEY_B"] = "user_b"

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}


def test_capstone_collaboration_flow(client, caplog):
    """
    Capstone Integration Test:
    1. User A creates a team.
    2. User A invites User B to the team as a member.
    3. User B accepts the invitation.
    4. User A connects to the real-time team WebSocket feed.
    5. User B posts a comment on the team thread, @mentioning User A.
    6. User A receives the comment event via the WebSocket feed.
    7. Admin checks the logs to verify audit trail prints for team creation,
       invitation sent, invitation accepted, and comment creation.
    """
    import logging
    # Set caplog to capture INFO logs
    caplog.set_level(logging.INFO)

    # --- Step 1: User A creates a team ---
    team_payload = {"name": "Capstone DevOps Team", "description": "E2E Capstone Test"}
    res = client.post("/teams/", json=team_payload, headers=HEADERS_A)
    assert res.status_code == 201
    team_data = res.json()
    team_id = team_data["id"]
    assert team_data["name"] == "Capstone DevOps Team"
    assert team_data["owner_id"] == "user_a"

    # --- Step 2: User A invites User B as a member ---
    invite_payload = {"email": "user_b@example.com", "role": "member"}
    res = client.post(f"/teams/{team_id}/invitations", json=invite_payload, headers=HEADERS_A)
    assert res.status_code == 201
    invite_data = res.json()
    assert invite_data["status"] == "pending"
    assert invite_data["role"] == "member"
    token = invite_data["token"]
    assert token is not None

    # --- Step 3: User B accepts the invitation ---
    accept_payload = {"token": token}
    res = client.post("/teams/invitations/accept", json=accept_payload, headers=HEADERS_B)
    assert res.status_code == 200
    member_data = res.json()
    assert member_data["user_id"] == "user_b"
    assert member_data["role"] == "member"
    assert member_data["team_id"] == team_id

    # --- Step 4 & 5 & 6: WebSocket flow and commenting ---
    # User A connects to WebSocket feed
    with client.websocket_connect(f"/teams/{team_id}/feed?token=API_KEY_A") as ws_a:
        # User B creates/retrieves comments thread for the team
        thread_payload = {"target_type": "team", "target_id": team_id}
        res = client.post("/threads", json=thread_payload, headers=HEADERS_B)
        assert res.status_code in {200, 201}
        thread_id = res.json()["id"]

        # User B posts a comment @mentioning User A
        comment_payload = {"content": "Hey @user_a! Let's check the build logs."}
        res = client.post(f"/threads/{thread_id}/comments", json=comment_payload, headers=HEADERS_B)
        assert res.status_code == 201
        comment_data = res.json()
        assert comment_data["content"] == "Hey @user_a! Let's check the build logs."
        assert comment_data["user_id"] == "user_b"

        # User A receives comment event via WebSocket broadcast
        ws_event = ws_a.receive_json()
        assert ws_event["event"] == "comment_created"
        assert ws_event["user_id"] == "user_b"
        assert ws_event["team_id"] == team_id
        assert f"thread {thread_id}" in ws_event["details"]

    # --- Step 7: Verify audit log records in log capture ---
    log_text = caplog.text

    assert "Audit Log - Team Created" in log_text
    assert f"team_id={team_id}" in log_text
    assert "owner_id=user_a" in log_text

    assert "Audit Log - Invitation Sent" in log_text
    assert f"team_id={team_id}" in log_text
    assert "email=user_b@example.com" in log_text

    assert "Audit Log - Invitation Accepted" in log_text
    assert f"team_id={team_id}" in log_text
    assert "user_id=user_b" in log_text

    assert "Audit Log - Comment Created" in log_text
    assert f"thread_id={thread_id}" in log_text
    assert f"comment_id={comment_data['id']}" in log_text
    assert "user_id=user_b" in log_text
