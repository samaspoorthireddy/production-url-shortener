import pytest
import asyncio
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from app.services.activity_feed import activity_feed_manager

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}

class TestWebSocketFeed:
    """Integration tests for the real-time team activity feed WebSockets."""

    def test_websocket_missing_token_rejected(self, client: TestClient):
        """Rejects WebSocket connection when the auth token query parameter is missing."""
        team_payload = {"name": "Dev Team", "description": "Development"}
        res = client.post("/teams/", json=team_payload, headers=HEADERS_A)
        assert res.status_code == 201
        team_id = res.json()["id"]

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/teams/{team_id}/feed"):
                pass
        assert excinfo.value.code == 1008

    def test_websocket_invalid_token_rejected(self, client: TestClient):
        """Rejects WebSocket connection when an invalid token is provided."""
        team_payload = {"name": "Dev Team", "description": "Development"}
        res = client.post("/teams/", json=team_payload, headers=HEADERS_A)
        assert res.status_code == 201
        team_id = res.json()["id"]

        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/teams/{team_id}/feed?token=INVALID_KEY"):
                pass
        assert excinfo.value.code == 1008

    def test_websocket_not_member_rejected(self, client: TestClient):
        """Rejects WebSocket connection when the authenticated user is not a member of the team."""
        # User A creates a team (so User A is a member/owner, but User B is not)
        team_payload = {"name": "Secret DevOps", "description": "Private DevOps team"}
        res = client.post("/teams/", json=team_payload, headers=HEADERS_A)
        assert res.status_code == 201
        team_id = res.json()["id"]

        # Try connecting with User B's token (not a member)
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"/teams/{team_id}/feed?token=API_KEY_B"):
                pass
        assert excinfo.value.code == 1008

    def test_websocket_non_existent_team_rejected(self, client: TestClient):
        """Rejects WebSocket connection for a non-existent team."""
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/teams/99999/feed?token=API_KEY_A"):
                pass
        assert excinfo.value.code == 1008

    def test_websocket_successful_connection_and_broadcast(self, client: TestClient):
        """Verifies successful connection and broadcast delivery to all active members of the team."""
        # 1. User A creates the team
        team_payload = {"name": "Product Team", "description": "Product updates"}
        res = client.post("/teams/", json=team_payload, headers=HEADERS_A)
        assert res.status_code == 201
        team_id = res.json()["id"]

        # 2. User A adds User B to the team
        member_payload = {"user_id": "user_b", "role": "member"}
        res = client.post(f"/teams/{team_id}/members", json=member_payload, headers=HEADERS_A)
        assert res.status_code == 201

        # 3. Open WebSocket connections for both User A and User B
        with client.websocket_connect(f"/teams/{team_id}/feed?token=API_KEY_A") as ws_a:
            with client.websocket_connect(f"/teams/{team_id}/feed?token=API_KEY_B") as ws_b:
                # 4. Broadcast an activity feed event to the team
                event = {
                    "event": "link_created",
                    "user_id": "user_a",
                    "team_id": team_id,
                    "timestamp": "2026-06-06T22:00:00Z",
                    "details": "User A created short link 'xyz'"
                }
                
                # Execute the async broadcast using the TestClient's portal or fallback
                if hasattr(client, "portal") and client.portal is not None:
                    client.portal.call(activity_feed_manager.broadcast, team_id, event)
                else:
                    asyncio.run(activity_feed_manager.broadcast(team_id, event))

                # 5. Verify both connected clients receive the broadcasted event
                data_a = ws_a.receive_json()
                data_b = ws_b.receive_json()

                assert data_a == event
                assert data_b == event
