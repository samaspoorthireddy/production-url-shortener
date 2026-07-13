import pytest
from app.dependencies import API_KEYS
from models import Team, UserTeam, CommentThread, Comment, Notification, TeamInvitation

# Add specific API keys to registry for the permission matrix tests
API_KEYS["API_KEY_OWNER"] = "user_owner"
API_KEYS["API_KEY_ADMIN"] = "user_admin"
API_KEYS["API_KEY_MEMBER"] = "user_member"
API_KEYS["API_KEY_VIEWER"] = "user_viewer"
API_KEYS["API_KEY_OUTSIDER"] = "user_outsider"

HEADERS_OWNER = {"X-API-Key": "API_KEY_OWNER"}
HEADERS_ADMIN = {"X-API-Key": "API_KEY_ADMIN"}
HEADERS_MEMBER = {"X-API-Key": "API_KEY_MEMBER"}
HEADERS_VIEWER = {"X-API-Key": "API_KEY_VIEWER"}
HEADERS_OUTSIDER = {"X-API-Key": "API_KEY_OUTSIDER"}


@pytest.fixture
def setup_permissions_team(client, db_session):
    """
    Sets up a team and populates the members with various roles.
    Returns the team_id.
    """
    # 1. Create team as Owner (user_owner)
    res = client.post("/teams/", json={"name": "Permissions Team", "description": "For testing permissions matrix"}, headers=HEADERS_OWNER)
    assert res.status_code == 201
    team_data = res.json()
    team_id = team_data["id"]

    # 2. Add Admin (user_admin)
    res_admin = client.post(f"/teams/{team_id}/members", json={"user_id": "user_admin", "role": "admin"}, headers=HEADERS_OWNER)
    assert res_admin.status_code == 201

    # 3. Add Member (user_member)
    res_member = client.post(f"/teams/{team_id}/members", json={"user_id": "user_member", "role": "member"}, headers=HEADERS_OWNER)
    assert res_member.status_code == 201

    # 4. Add Viewer (user_viewer)
    res_viewer = client.post(f"/teams/{team_id}/members", json={"user_id": "user_viewer", "role": "viewer"}, headers=HEADERS_OWNER)
    assert res_viewer.status_code == 201

    return team_id


class TestPermissionsMatrix:
    """Verifies access control boundaries across Owner, Admin, Member, Viewer, and Outsider roles."""

    def test_invitation_permissions(self, client, setup_permissions_team):
        team_id = setup_permissions_team

        # Owner can invite (201)
        res = client.post(f"/teams/{team_id}/invitations", json={"email": "invitee_owner@example.com", "role": "member"}, headers=HEADERS_OWNER)
        assert res.status_code == 201
        assert res.json()["status"] == "pending"

        # Admin can invite (201)
        res = client.post(f"/teams/{team_id}/invitations", json={"email": "invitee_admin@example.com", "role": "member"}, headers=HEADERS_ADMIN)
        assert res.status_code == 201

        # Member cannot invite (403)
        res = client.post(f"/teams/{team_id}/invitations", json={"email": "invitee_member@example.com", "role": "member"}, headers=HEADERS_MEMBER)
        assert res.status_code == 403

        # Viewer cannot invite (403)
        res = client.post(f"/teams/{team_id}/invitations", json={"email": "invitee_viewer@example.com", "role": "member"}, headers=HEADERS_VIEWER)
        assert res.status_code == 403

        # Outsider cannot invite (403)
        res = client.post(f"/teams/{team_id}/invitations", json={"email": "invitee_out@example.com", "role": "member"}, headers=HEADERS_OUTSIDER)
        assert res.status_code == 403

    def test_member_removal_permissions(self, client, setup_permissions_team):
        team_id = setup_permissions_team

        # Member trying to remove Viewer -> 403
        res = client.delete(f"/teams/{team_id}/members/user_viewer", headers=HEADERS_MEMBER)
        assert res.status_code == 403

        # Viewer trying to remove Member -> 403
        res = client.delete(f"/teams/{team_id}/members/user_member", headers=HEADERS_VIEWER)
        assert res.status_code == 403

        # Outsider trying to remove Member -> 403
        res = client.delete(f"/teams/{team_id}/members/user_member", headers=HEADERS_OUTSIDER)
        assert res.status_code == 403

        # Admin trying to remove Member -> 200
        res = client.delete(f"/teams/{team_id}/members/user_member", headers=HEADERS_ADMIN)
        assert res.status_code == 200

        # Owner trying to remove Viewer -> 200
        res = client.delete(f"/teams/{team_id}/members/user_viewer", headers=HEADERS_OWNER)
        assert res.status_code == 200

    def test_commenting_permissions(self, client, setup_permissions_team):
        team_id = setup_permissions_team

        # 1. Create a comment thread for the team. Anyone in the team can do this.
        res_thread = client.post("/threads", json={"target_type": "team", "target_id": team_id}, headers=HEADERS_MEMBER)
        assert res_thread.status_code in {200, 201}
        thread_id = res_thread.json()["id"]

        # Owner can comment -> 201
        res = client.post(f"/threads/{thread_id}/comments", json={"content": "Hello from Owner"}, headers=HEADERS_OWNER)
        assert res.status_code == 201

        # Admin can comment -> 201
        res = client.post(f"/threads/{thread_id}/comments", json={"content": "Hello from Admin"}, headers=HEADERS_ADMIN)
        assert res.status_code == 201

        # Member can comment -> 201
        res = client.post(f"/threads/{thread_id}/comments", json={"content": "Hello from Member"}, headers=HEADERS_MEMBER)
        assert res.status_code == 201

        # Viewer CANNOT comment -> 403 Forbidden (Viewers cannot add comments)
        res = client.post(f"/threads/{thread_id}/comments", json={"content": "Hello from Viewer"}, headers=HEADERS_VIEWER)
        assert res.status_code == 403
        assert "cannot add comments" in res.json()["error"]["message"].lower()

        # Outsider CANNOT comment -> 403 Forbidden
        res = client.post(f"/threads/{thread_id}/comments", json={"content": "Hello from Outsider"}, headers=HEADERS_OUTSIDER)
        assert res.status_code == 403

    def test_viewing_comments_permissions(self, client, setup_permissions_team):
        team_id = setup_permissions_team

        # Create thread
        res_thread = client.post("/threads", json={"target_type": "team", "target_id": team_id}, headers=HEADERS_OWNER)
        thread_id = res_thread.json()["id"]

        # Add a comment
        client.post(f"/threads/{thread_id}/comments", json={"content": "Important discussion"}, headers=HEADERS_OWNER)

        # Owner can retrieve comments -> 200
        res = client.get(f"/threads/{thread_id}/comments", headers=HEADERS_OWNER)
        assert res.status_code == 200
        assert len(res.json()) >= 1

        # Admin can retrieve comments -> 200
        res = client.get(f"/threads/{thread_id}/comments", headers=HEADERS_ADMIN)
        assert res.status_code == 200

        # Member can retrieve comments -> 200
        res = client.get(f"/threads/{thread_id}/comments", headers=HEADERS_MEMBER)
        assert res.status_code == 200

        # Viewer can retrieve comments -> 200
        res = client.get(f"/threads/{thread_id}/comments", headers=HEADERS_VIEWER)
        assert res.status_code == 200

        # Outsider CANNOT retrieve comments -> 403
        res = client.get(f"/threads/{thread_id}/comments", headers=HEADERS_OUTSIDER)
        assert res.status_code == 403

    def test_notification_isolation_permissions(self, client, setup_permissions_team, db_session):
        team_id = setup_permissions_team

        # Create thread
        res_thread = client.post("/threads", json={"target_type": "team", "target_id": team_id}, headers=HEADERS_OWNER)
        thread_id = res_thread.json()["id"]

        # Add comment mentioning user_member and user_viewer
        # Mentions are processed and notifications are generated
        res_comment = client.post(
            f"/threads/{thread_id}/comments",
            json={"content": "Let's ask @user_member and @user_viewer for input"},
            headers=HEADERS_OWNER
        )
        assert res_comment.status_code == 201
        comment_id = res_comment.json()["id"]

        # Verify that notifications exist for user_member and user_viewer in the database
        notif_member = db_session.query(Notification).filter(
            Notification.recipient_id == "user_member",
            Notification.comment_id == comment_id
        ).first()
        notif_viewer = db_session.query(Notification).filter(
            Notification.recipient_id == "user_viewer",
            Notification.comment_id == comment_id
        ).first()

        assert notif_member is not None
        assert notif_viewer is not None

        # Member can view their own notifications -> 200
        res = client.get("/notifications", headers=HEADERS_MEMBER)
        assert res.status_code == 200
        member_notifs = res.json()
        assert any(n["id"] == notif_member.id for n in member_notifs)
        assert not any(n["id"] == notif_viewer.id for n in member_notifs)  # Member should not see Viewer's notifications

        # Viewer can view their own notifications -> 200
        res = client.get("/notifications", headers=HEADERS_VIEWER)
        assert res.status_code == 200
        viewer_notifs = res.json()
        assert any(n["id"] == notif_viewer.id for n in viewer_notifs)
        assert not any(n["id"] == notif_member.id for n in viewer_notifs)

        # Member cannot mark Viewer's notification as read -> 403
        res = client.patch(f"/notifications/{notif_viewer.id}/read", headers=HEADERS_MEMBER)
        assert res.status_code == 403

        # Viewer can mark own notification as read -> 200
        res = client.patch(f"/notifications/{notif_viewer.id}/read", headers=HEADERS_VIEWER)
        assert res.status_code == 200
        assert res.json()["is_read"] is True

    def test_team_deletion_permissions(self, client, setup_permissions_team):
        team_id = setup_permissions_team

        # Member cannot delete team -> 403
        res = client.delete(f"/teams/{team_id}", headers=HEADERS_MEMBER)
        assert res.status_code == 403

        # Viewer cannot delete team -> 403
        res = client.delete(f"/teams/{team_id}", headers=HEADERS_VIEWER)
        assert res.status_code == 403

        # Admin can delete team -> 200
        # Wait, the code in app/routers/teams.py allows Admin OR Owner to delete the team:
        # "Only team owners or administrators can delete the team"
        res = client.delete(f"/teams/{team_id}", headers=HEADERS_ADMIN)
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
