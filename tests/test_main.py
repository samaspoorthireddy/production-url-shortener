import pytest
from datetime import datetime

# Auth Headers matching the static users defined in dependencies.py
HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}
HEADERS_INVALID = {"X-API-Key": "INVALID_KEY"}

# 1. Create Link Test


def test_create_link(client):
    """
    Verifies that a user can successfully create a link with tags,
    returning a 201 status code and matching schema structures.
    """
    payload = {
        "long_url": "https://www.google.com",
        "tags": ["search", "tech"]
    }
    response = client.post("/v1/links/", json=payload, headers=HEADERS_A)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert len(data["code"]) == 8
    assert data["long_url"] == "https://www.google.com"
    assert data["tags"] == ["search", "tech"]

# 2. Redirect Test (use GET /r/{code})


def test_redirect_correctness(client):
    """
    Verifies that public redirect endpoints successfully resolve codes, returning
    a 302 Found status and Location headers mapping back to the destination.
    """
    payload = {
        "long_url": "https://news.ycombinator.com",
        "tags": ["news"]
    }
    create_res = client.post("/v1/links/", json=payload, headers=HEADERS_A)
    assert create_res.status_code == 201
    code = create_res.json()["code"]

    # We set follow_redirects=False to inspect location headers on 302
    redirect_res = client.get(f"/r/{code}", follow_redirects=False)
    assert redirect_res.status_code == 302
    assert redirect_res.headers["location"] == "https://news.ycombinator.com"

# 3. Auth Behavior Test (returns 401)


def test_auth_protection(client):
    """
    Verifies that endpoints enforce authentication blocks, returning
    401 Unauthorized for missing or invalid header credentials.
    """
    payload = {"long_url": "https://www.wikipedia.org"}

    # Check missing API Key
    res_missing = client.post("/v1/links/", json=payload)
    assert res_missing.status_code == 401
    assert "missing" in res_missing.json()["error"]["message"].lower()

    res_invalid = client.post("/v1/links/", json=payload, headers=HEADERS_INVALID)
    assert res_invalid.status_code == 401
    assert "invalid" in res_invalid.json()["error"]["message"].lower()

# 4. Owner Scoping (IDOR) Test
# User A creates, User B cannot read/update/delete (returns 404)


def test_owner_scoping_idor(client):
    """
    Verifies owner scoping isolation: User B cannot access, modify, or delete
    links owned by User A, safely returning 404 Not Found to prevent enumeration.
    """
    payload = {"long_url": "https://github.com"}

    # User A creates a link
    create_res = client.post("/v1/links/", json=payload, headers=HEADERS_A)
    assert create_res.status_code == 201
    link_id = create_res.json()["id"]

    read_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_B)
    assert read_res.status_code == 404

    update_res = client.patch(f"/v1/links/{link_id}", json={"long_url": "https://evil.com"}, headers=HEADERS_B)
    assert update_res.status_code == 404

    delete_res = client.delete(f"/v1/links/{link_id}", headers=HEADERS_B)
    assert delete_res.status_code == 404

# 5. Retention Enforcement Test
# Create click event, run purge mechanism, assert old clicks are deleted


def test_retention_enforcement(client, db_session):
    """
    Verifies that old analytics click records are deleted safely while
    preserving recent history based on retention limits.
    """
    from models import Link, ClickEvent
    from datetime import timedelta

    # Seed link directly via SQLAlchemy to control timestamps and environment
    link = Link(code="retTest", long_url="https://finance.yahoo.com", created_by="user_a")
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    # Click 1: 45 days ago (should be purged under 30-day retention)
    from datetime import timezone
    old_click = ClickEvent(
        link_id=link.id,
        user_agent="TestBot",
        clicked_at=datetime.now(timezone.utc) - timedelta(days=45),
        request_id="old-req-id"
    )
    # Click 2: 5 days ago (should be preserved)
    new_click = ClickEvent(
        link_id=link.id,
        user_agent="TestBot",
        clicked_at=datetime.now(timezone.utc) - timedelta(days=5),
        request_id="new-req-id"
    )
    db_session.add(old_click)
    db_session.add(new_click)
    db_session.commit()

    # Assert initial database state has 2 click records
    assert db_session.query(ClickEvent).count() == 2

    # Trigger administrator purge endpoint
    purge_res = client.post("/v1/links/analytics/purge?retention_days=30", headers=HEADERS_A)
    assert purge_res.status_code == 200

    # In integration environments, we execute the background purge task directly
    # in the same thread to ensure deterministic results.
    # We temporarily patch SessionLocal in app.tasks to use our transactional db_session
    from app import tasks
    from app.tasks import purge_clicks_task
    original_session_local = tasks.SessionLocal
    tasks.SessionLocal = lambda: db_session
    try:
        purge_clicks_task(retention_days=30)
    finally:
        tasks.SessionLocal = original_session_local

    # Verify database state after purge
    clicks = db_session.query(ClickEvent).all()
    assert len(clicks) == 1
    assert clicks[0].request_id == "new-req-id"

# 6. URL Validation Test (rejects bypass strings)


def test_url_validation_bypasses(client):
    """
    Verifies that standard link validators block browser normalization bypass attempts
    (like illegal backslashes or authority credential routing).
    """
    # 1. Backslash character checks
    payload_backslash = {"long_url": "https://google.com\\evil.com"}
    res_backslash = client.post("/v1/links/", json=payload_backslash, headers=HEADERS_A)
    assert res_backslash.status_code == 422
    assert "backslash" in res_backslash.json()["error"]["message"].lower()

    # 2. Authority credential userinfo checks
    payload_userinfo = {"long_url": "https://good.com@evil.com"}
    res_userinfo = client.post("/v1/links/", json=payload_userinfo, headers=HEADERS_A)
    assert res_userinfo.status_code == 422
    assert "user information" in res_userinfo.json()["error"]["message"].lower()


def test_database_timeout_handler(client):
    """
    Verifies that when database connection pool timeout occurs (DBTimeoutError),
    the custom exception handler catches it and returns HTTP 503 Service Unavailable.
    """
    from unittest.mock import patch
    from sqlalchemy.exc import TimeoutError as DBTimeoutError

    with patch("app.services.links_service.create_link", side_effect=DBTimeoutError("Queue Pool limit of size 10 overflow 5 reached, connection timed out, timeout 10")):
        payload = {"long_url": "https://www.example.com"}
        response = client.post("/v1/links/", json=payload, headers=HEADERS_A)
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "Database connection pool exhausted" in data["error"]["message"]


def test_database_operational_handler(client):
    """
    Verifies that when a database operational/connection failure occurs (DBOperationalError),
    the custom exception handler catches it and returns HTTP 503 Service Unavailable.
    """
    from unittest.mock import patch
    from sqlalchemy.exc import OperationalError as DBOperationalError

    with patch("app.services.links_service.create_link", side_effect=DBOperationalError("connection refused", {}, None)):
        payload = {"long_url": "https://www.example.com"}
        response = client.post("/v1/links/", json=payload, headers=HEADERS_A)
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "Database service is temporarily unavailable" in data["error"]["message"]

