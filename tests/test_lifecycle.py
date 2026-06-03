"""
Integration tests for Module 15: Link Lifecycle Management.

Three feature areas:
  1. TestVanityCode    — custom short codes (collision, invalid chars, length)
  2. TestLinkExpiry   — expires_at enforcement at redirect time
  3. TestClickCap     — max_clicks enforcement at redirect time
"""
import pytest
from datetime import datetime, timedelta, timezone
from models import ClickEvent

HEADERS_A = {"X-API-Key": "API_KEY_A"}
BASE_URL = "https://example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_link(client, **kwargs):
    """POST /v1/links/ helper; returns the full response object."""
    payload = {"long_url": BASE_URL, **kwargs}
    return client.post("/v1/links/", json=payload, headers=HEADERS_A)


def future(seconds: int = 3600) -> str:
    """ISO-8601 datetime string that is N seconds in the future."""
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def past(seconds: int = 1) -> str:
    """ISO-8601 datetime string that is N seconds in the past."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# 1. Vanity / Custom Short Codes
# ---------------------------------------------------------------------------

class TestVanityCode:
    """Custom code happy path, collision, and validation edge cases."""

    def test_vanity_code_accepted(self, client):
        """A valid custom code is persisted and returned in the response."""
        res = create_link(client, code="my-brand")
        assert res.status_code == 201
        assert res.json()["code"] == "my-brand"

    def test_vanity_code_used_as_redirect_slug(self, client):
        """The custom code actually works as the redirect slug."""
        create_link(client, code="go-here")
        redir = client.get("/r/go-here", follow_redirects=False)
        assert redir.status_code == 302
        assert redir.headers["location"] == BASE_URL

    def test_vanity_code_collision_returns_409(self, client):
        """Requesting a code that's already taken must return 409 Conflict."""
        create_link(client, code="taken-code")
        res2 = create_link(client, code="taken-code")
        assert res2.status_code == 409
        assert "already taken" in res2.json()["error"]["message"].lower()

    def test_vanity_code_too_short_rejected(self, client):
        """Codes shorter than 3 characters are invalid."""
        res = create_link(client, code="ab")
        assert res.status_code == 422

    def test_vanity_code_too_long_rejected(self, client):
        """Codes longer than 30 characters are invalid."""
        res = create_link(client, code="a" * 31)
        assert res.status_code == 422

    def test_vanity_code_invalid_chars_rejected(self, client):
        """Spaces and special characters are rejected."""
        for bad_code in ["my brand", "my@code", "code!", "my/path"]:
            res = create_link(client, code=bad_code)
            assert res.status_code == 422, f"Expected 422 for code: {bad_code!r}"

    def test_vanity_code_alphanumeric_hyphens_underscores_allowed(self, client):
        """Letters, digits, hyphens, and underscores are all valid."""
        res = create_link(client, code="My_Brand-2026")
        assert res.status_code == 201
        assert res.json()["code"] == "My_Brand-2026"

    def test_no_custom_code_generates_random_slug(self, client):
        """Omitting code still creates a link with an auto-generated slug."""
        res = create_link(client)
        assert res.status_code == 201
        assert len(res.json()["code"]) >= 8  # default random code length


# ---------------------------------------------------------------------------
# 2. Link Expiry (TTL)
# ---------------------------------------------------------------------------

class TestLinkExpiry:
    """expires_at is enforced at redirect time; cache TTL is shortened accordingly."""

    def test_non_expired_link_redirects_normally(self, client):
        """A link with a future expiry should redirect with 302."""
        res = create_link(client, expires_at=future(3600))
        assert res.status_code == 201
        code = res.json()["code"]
        redir = client.get(f"/r/{code}", follow_redirects=False)
        assert redir.status_code == 302

    def test_expired_link_returns_410(self, client, db_session):
        """
        A link whose expires_at is in the past must return 410 Gone.
        We create the link with a future timestamp, then manually backdate
        it in the test DB to simulate passage of time.
        """
        res = create_link(client, expires_at=future(3600))
        assert res.status_code == 201
        link_id = res.json()["id"]
        code = res.json()["code"]

        # Backdate the expiry to the past
        from models import Link
        db_session.query(Link).filter(Link.id == link_id).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        db_session.commit()

        redir = client.get(f"/r/{code}", follow_redirects=False)
        assert redir.status_code == 410
        assert "expired" in redir.json()["error"]["message"].lower()

    def test_expiry_in_past_rejected_at_creation(self, client):
        """
        Pydantic validator must reject expires_at that is already in the past
        at creation time — no dead-on-arrival links.
        """
        res = create_link(client, expires_at=past(60))
        assert res.status_code == 422

    def test_is_active_false_for_expired_link(self, client, db_session):
        """The API response for an expired link must show is_active: false."""
        res = create_link(client, expires_at=future(3600))
        link_id = res.json()["id"]

        from models import Link
        db_session.query(Link).filter(Link.id == link_id).update(
            {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        db_session.commit()

        get_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_A)
        assert get_res.status_code == 200
        assert get_res.json()["is_active"] is False

    def test_is_active_true_for_non_expired_link(self, client):
        """A link with a future expiry must have is_active: true."""
        res = create_link(client, expires_at=future(3600))
        link_id = res.json()["id"]
        get_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_A)
        assert get_res.json()["is_active"] is True

    def test_expires_at_present_in_response(self, client):
        """expires_at must be echoed back in the creation response."""
        ts = future(7200)
        res = create_link(client, expires_at=ts)
        assert res.status_code == 201
        assert res.json()["expires_at"] is not None


# ---------------------------------------------------------------------------
# 3. Click Cap (max_clicks)
# ---------------------------------------------------------------------------

class TestClickCap:
    """max_clicks enforcement — redirect blocked once cap is reached."""

    def test_max_clicks_present_in_response(self, client):
        """max_clicks is echoed in the creation response."""
        res = create_link(client, max_clicks=5)
        assert res.status_code == 201
        assert res.json()["max_clicks"] == 5

    def test_redirect_allowed_under_cap(self, client, db_session):
        """With 1 click recorded and max_clicks=5, redirect should succeed."""
        res = create_link(client, max_clicks=5)
        link_id = res.json()["id"]
        code = res.json()["code"]

        # 1 click — well under the cap of 5
        db_session.add(ClickEvent(link_id=link_id, clicked_at=datetime.now(timezone.utc)))
        db_session.commit()

        redir = client.get(f"/r/{code}", follow_redirects=False)
        assert redir.status_code == 302

    def test_redirect_blocked_at_cap(self, client, db_session):
        """Once click_count == max_clicks the redirect must return 410 Gone."""
        res = create_link(client, max_clicks=3)
        link_id = res.json()["id"]
        code = res.json()["code"]

        # Insert exactly 3 click events (== cap)
        for _ in range(3):
            db_session.add(ClickEvent(link_id=link_id, clicked_at=datetime.now(timezone.utc)))
        db_session.commit()

        redir = client.get(f"/r/{code}", follow_redirects=False)
        assert redir.status_code == 410
        assert "click limit" in redir.json()["error"]["message"].lower()

    def test_single_use_link(self, client, db_session):
        """max_clicks=1 creates a single-use link: first hit 302, second hit 410."""
        res = create_link(client, max_clicks=1)
        link_id = res.json()["id"]
        code = res.json()["code"]

        # First redirect succeeds
        first = client.get(f"/r/{code}", follow_redirects=False)
        assert first.status_code == 302

        # Simulate the Celery click event being persisted
        db_session.add(ClickEvent(link_id=link_id, clicked_at=datetime.now(timezone.utc)))
        db_session.commit()

        # Second redirect is blocked
        second = client.get(f"/r/{code}", follow_redirects=False)
        assert second.status_code == 410

    def test_max_clicks_zero_rejected(self, client):
        """max_clicks=0 is nonsensical and must be rejected by the validator."""
        res = create_link(client, max_clicks=0)
        assert res.status_code == 422

    def test_max_clicks_negative_rejected(self, client):
        """Negative max_clicks must be rejected by the validator."""
        res = create_link(client, max_clicks=-1)
        assert res.status_code == 422

    def test_is_active_false_when_cap_reached(self, client, db_session):
        """API response must show is_active: false once the cap is hit."""
        res = create_link(client, max_clicks=2)
        link_id = res.json()["id"]

        for _ in range(2):
            db_session.add(ClickEvent(link_id=link_id, clicked_at=datetime.now(timezone.utc)))
        db_session.commit()

        get_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_A)
        assert get_res.json()["is_active"] is False

    def test_no_cap_link_is_always_active(self, client):
        """A link without max_clicks should show is_active: true."""
        res = create_link(client)
        link_id = res.json()["id"]
        get_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_A)
        assert get_res.json()["is_active"] is True
