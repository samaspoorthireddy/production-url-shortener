"""
Integration tests for API versioning & backwards compatibility.

Core principle tested:
  "A client written for V1 must continue to work after V2 ships."
  "A V2 client gets richer data and deprecation signals."
"""
import pytest
from datetime import datetime, UTC
from models import ClickEvent

HEADERS_A = {"X-API-Key": "API_KEY_A"}


class TestV1StillWorks:
    """
    Backwards compatibility guarantee: every V1 endpoint must continue
    to return exactly the same shape it always did.
    """

    def test_v1_create_returns_201(self, client):
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert res.status_code == 201

    def test_v1_create_response_has_all_v1_fields(self, client):
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com", "tags": ["test"]},
            headers=HEADERS_A,
        )
        data = res.json()
        # Every V1 field must be present
        assert "id" in data
        assert "code" in data
        assert "long_url" in data
        assert "short_url" in data
        assert "created_at" in data
        assert "tags" in data

    def test_v1_response_does_NOT_include_click_count(self, client):
        """V1 clients must not receive surprise fields that break strict parsers."""
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert "click_count" not in res.json()

    def test_v1_security_still_enforced(self, client):
        """Security hardening must apply to both versions."""
        res = client.post(
            "/v1/links/",
            json={"long_url": "http://169.254.169.254/latest/meta-data/"},
            headers=HEADERS_A,
        )
        assert res.status_code == 422

    def test_v1_auth_still_enforced(self, client):
        res = client.post("/v1/links/", json={"long_url": "https://example.com"})
        assert res.status_code == 401


class TestV2EnrichedResponse:
    """V2 endpoints return a superset of V1 — all V1 fields plus click_count."""

    def test_v2_create_returns_201(self, client):
        res = client.post(
            "/v2/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert res.status_code == 201

    def test_v2_response_includes_click_count(self, client):
        res = client.post(
            "/v2/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        data = res.json()
        assert "click_count" in data
        assert data["click_count"] == 0  # zero on creation

    def test_v2_response_still_has_all_v1_fields(self, client):
        """Strict superset rule: V2 must contain every V1 field unchanged."""
        res = client.post(
            "/v2/links/",
            json={"long_url": "https://example.com", "tags": ["v2test"]},
            headers=HEADERS_A,
        )
        data = res.json()
        assert "id" in data
        assert "code" in data
        assert "long_url" in data
        assert "short_url" in data
        assert "created_at" in data
        assert "tags" in data
        assert "click_count" in data  # the V2 addition

    def test_v2_click_count_increments_after_redirect(self, client, db_session):
        """
        After a redirect, the click_count on the V2 GET response must increment.
        This is the core business value V2 adds — no separate analytics call needed.

        In tests, Celery workers don't run, so we insert the ClickEvent directly
        into the transactional test DB — this is exactly what the Celery task does.
        """
        # Create via V2
        create_res = client.post(
            "/v2/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert create_res.status_code == 201
        link_id = create_res.json()["id"]
        code = create_res.json()["code"]

        # Trigger the redirect (enqueues Celery task, but task doesn't run in tests)
        client.get(f"/r/{code}", follow_redirects=False)

        # Directly insert the ClickEvent that Celery would have written
        click = ClickEvent(link_id=link_id, clicked_at=datetime.now(UTC))
        db_session.add(click)
        db_session.commit()

        # V2 GET must now show click_count = 1
        get_res = client.get(f"/v2/links/{link_id}", headers=HEADERS_A)
        assert get_res.status_code == 200
        assert get_res.json()["click_count"] == 1

    def test_v2_security_enforced(self, client):
        """V2 shares all security validation with V1."""
        res = client.post(
            "/v2/links/",
            json={"long_url": "http://10.0.0.1/internal"},
            headers=HEADERS_A,
        )
        assert res.status_code == 422


class TestDeprecationHeaders:
    """
    RFC 8594 deprecation signals must be present on /v1/ responses
    and absent from /v2/ responses.
    """

    def test_v1_responses_carry_deprecation_header(self, client):
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert "deprecation" in res.headers
        assert res.headers["deprecation"] == "true"

    def test_v1_responses_carry_sunset_header(self, client):
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert "sunset" in res.headers
        assert "2027" in res.headers["sunset"]  # gives 6+ months notice

    def test_v1_responses_carry_successor_link_header(self, client):
        """Link header must point clients to the V2 migration path."""
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert "link" in res.headers
        assert "/v2/links/" in res.headers["link"]
        assert "successor-version" in res.headers["link"]

    def test_v2_responses_have_no_deprecation_header(self, client):
        """V2 is the current version — must NOT carry deprecation signals."""
        res = client.post(
            "/v2/links/",
            json={"long_url": "https://example.com"},
            headers=HEADERS_A,
        )
        assert "deprecation" not in res.headers

    def test_unversioned_health_endpoint_has_no_deprecation(self, client):
        """System endpoints outside /v1/ must not get the deprecation header."""
        res = client.get("/health")
        assert "deprecation" not in res.headers
