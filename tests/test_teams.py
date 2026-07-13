import pytest
from models import Team, UserTeam
from app.dependencies import API_KEYS

# Register extra mock keys for tests
API_KEYS["API_KEY_C"] = "user_c"
API_KEYS["API_KEY_D"] = "user_d"

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}
HEADERS_C = {"X-API-Key": "API_KEY_C"}
HEADERS_D = {"X-API-Key": "API_KEY_D"}


class TestTeamsRouter:
    """Integration tests for Teams and Team Memberships API endpoints."""

    def test_create_team_happy_path(self, client):
        """User creates a new team successfully, and is set as owner and admin member."""
        payload = {"name": "Engineers", "description": "Backend Team"}
        res = client.post("/teams/", json=payload, headers=HEADERS_A)
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Engineers"
        assert data["description"] == "Backend Team"
        assert data["owner_id"] == "user_a"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Check membership list
        memberships = data.get("memberships", [])
        assert len(memberships) == 1
        assert memberships[0]["user_id"] == "user_a"
        assert memberships[0]["role"] == "admin"

    def test_create_team_invalid_name(self, client):
        """Creating a team with an empty or whitespace name fails validation."""
        # Empty string
        payload = {"name": "", "description": "Empty name"}
        res = client.post("/teams/", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

        # Whitespace-only string
        payload = {"name": "   ", "description": "Spaces name"}
        res = client.post("/teams/", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

    def test_get_team_happy_path(self, client):
        """Member of the team can view team details."""
        # 1. Create team as User A
        create_res = client.post("/teams/", json={"name": "Frontend"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Retrieve team as User A
        get_res = client.get(f"/teams/{team_id}", headers=HEADERS_A)
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "Frontend"

    def test_get_team_not_member_forbidden(self, client):
        """Non-member of the team cannot view team details (403 Forbidden)."""
        # 1. Create team as User A
        create_res = client.post("/teams/", json={"name": "DevOps"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Try to retrieve team as User B (not a member)
        get_res = client.get(f"/teams/{team_id}", headers=HEADERS_B)
        assert get_res.status_code == 403
        assert "not a member" in get_res.json()["error"]["message"]

    def test_get_team_not_found(self, client):
        """Retrieving a non-existent team returns 404 Not Found."""
        get_res = client.get("/teams/99999", headers=HEADERS_A)
        assert get_res.status_code == 404

    def test_add_member_as_admin_owner(self, client):
        """Team owner/admin can add a new member."""
        # 1. Create team as User A (owner and admin)
        create_res = client.post("/teams/", json={"name": "QA"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Owner User A adds User B as member
        add_res = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_b", "role": "member"},
            headers=HEADERS_A
        )
        assert add_res.status_code == 201
        data = add_res.json()
        assert data["user_id"] == "user_b"
        assert data["role"] == "member"
        assert data["team_id"] == team_id

        # 3. Verify User B now has access to the team
        get_res = client.get(f"/teams/{team_id}", headers=HEADERS_B)
        assert get_res.status_code == 200

    def test_add_member_unauthorized_forbidden(self, client):
        """Non-admin / non-owner member cannot add new members (403 Forbidden)."""
        # 1. Create team as User A (owner)
        create_res = client.post("/teams/", json={"name": "Security"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Owner adds User B as viewer
        client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_b", "role": "viewer"},
            headers=HEADERS_A
        )

        # 3. User B (viewer, not admin/owner) tries to add a third user
        add_res = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_c", "role": "member"},
            headers=HEADERS_B
        )
        assert add_res.status_code == 403
        assert "Only team owners or administrators" in add_res.json()["error"]["message"]

    def test_add_duplicate_member_bad_request(self, client):
        """Adding a user who is already a member of the team returns 400 Bad Request."""
        # 1. Create team as User A
        create_res = client.post("/teams/", json={"name": "Marketing"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Add User B
        client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_b", "role": "member"},
            headers=HEADERS_A
        )

        # 3. Add User B again
        add_res = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_b", "role": "member"},
            headers=HEADERS_A
        )
        assert add_res.status_code == 400
        assert "already a member" in add_res.json()["error"]["message"]

    def test_add_member_invalid_role(self, client):
        """Adding a member with an invalid role returns 422 Unprocessable Entity."""
        # 1. Create team as User A
        create_res = client.post("/teams/", json={"name": "Sales"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Try to add User B with role 'superuser'
        add_res = client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user_b", "role": "superuser"},
            headers=HEADERS_A
        )
        assert add_res.status_code == 422

    def test_role_update_security_matrix(self, client):
        """Verify the 13 secure constraint behaviors of PUT /teams/:id/members/:uid"""
        # 1. Create team as User A (becomes Owner)
        create_res = client.post("/teams/", json={"name": "SecOps"}, headers=HEADERS_A)
        assert create_res.status_code == 201
        team_id = create_res.json()["id"]

        # 2. Add members with different roles via Owner A
        # User B: viewer
        res = client.post(f"/teams/{team_id}/members", json={"user_id": "user_b", "role": "viewer"}, headers=HEADERS_A)
        assert res.status_code == 201
        # User C: member
        res = client.post(f"/teams/{team_id}/members", json={"user_id": "user_c", "role": "member"}, headers=HEADERS_A)
        assert res.status_code == 201
        # User D: admin
        res = client.post(f"/teams/{team_id}/members", json={"user_id": "user_d", "role": "admin"}, headers=HEADERS_A)
        assert res.status_code == 201

        # CONSTRAINT 1: Viewer tries to update own role to admin -> 403
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "admin"}, headers=HEADERS_B)
        assert res.status_code == 403

        # CONSTRAINT 2: Viewer tries to update another member's role -> 403
        res = client.put(f"/teams/{team_id}/members/user_c", json={"role": "admin"}, headers=HEADERS_B)
        assert res.status_code == 403

        # CONSTRAINT 3: Member tries to update own role to admin -> 403
        res = client.put(f"/teams/{team_id}/members/user_c", json={"role": "admin"}, headers=HEADERS_C)
        assert res.status_code == 403

        # CONSTRAINT 4: Member tries to update another member's role -> 403
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "admin"}, headers=HEADERS_C)
        assert res.status_code == 403

        # CONSTRAINT 5: Admin updates a viewer to member -> 200
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "member"}, headers=HEADERS_D)
        assert res.status_code == 200
        assert res.json()["role"] == "member"

        # CONSTRAINT 6: Admin updates a member to viewer -> 200
        res = client.put(f"/teams/{team_id}/members/user_c", json={"role": "viewer"}, headers=HEADERS_D)
        assert res.status_code == 200
        assert res.json()["role"] == "viewer"

        # CONSTRAINT 7: Admin tries to promote member to owner -> 403
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "owner"}, headers=HEADERS_D)
        assert res.status_code == 403

        # CONSTRAINT 8: Admin tries to update own role -> 403
        res = client.put(f"/teams/{team_id}/members/user_d", json={"role": "viewer"}, headers=HEADERS_D)
        assert res.status_code == 403

        # CONSTRAINT 9: Owner updates a member to admin -> 200
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "admin"}, headers=HEADERS_A)
        assert res.status_code == 200
        assert res.json()["role"] == "admin"

        # CONSTRAINT 10: Owner promotes a member to owner -> 200
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "owner"}, headers=HEADERS_A)
        assert res.status_code == 200
        assert res.json()["role"] == "owner"

        # CONSTRAINT 11: Owner tries to update own role -> 403
        # Note: Since User B is the new owner now, User B tries to update own role
        res = client.put(f"/teams/{team_id}/members/user_b", json={"role": "admin"}, headers=HEADERS_B)
        assert res.status_code == 403

        # CONSTRAINT 12: Any user sends role value "superadmin" -> 400
        res = client.put(f"/teams/{team_id}/members/user_c", json={"role": "superadmin"}, headers=HEADERS_A)
        assert res.status_code == 400

        # CONSTRAINT 13: Any user sends role value "" -> 400
        res = client.put(f"/teams/{team_id}/members/user_c", json={"role": ""}, headers=HEADERS_A)
        assert res.status_code == 400

