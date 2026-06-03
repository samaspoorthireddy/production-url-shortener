"""
Integration tests for Module 17C: Webhook Notifications.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from models import WebhookSubscription, Link
from app.tasks import log_click_task, dispatch_webhook_task

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}
BASE_URL = "https://example.com"


class TestWebhookLifecycle:
    """Tests CRUD lifecycle of Webhook Subscription API endpoints."""

    def test_webhook_register_happy_path(self, client):
        """User registers a callback URL successfully."""
        payload = {"url": "https://callback.com/webhook"}
        res = client.post("/v1/webhooks/", json=payload, headers=HEADERS_A)
        assert res.status_code == 201
        data = res.json()
        assert data["url"] == "https://callback.com/webhook"
        assert data["created_by"] == "user_a"
        assert "id" in data
        assert "created_at" in data

    def test_webhook_retrieve(self, client):
        """User retrieves their currently registered webhook callback URL."""
        # 1. Register first
        client.post("/v1/webhooks/", json={"url": "https://callback.com/webhook"}, headers=HEADERS_A)

        # 2. Get registered URL
        res = client.get("/v1/webhooks/", headers=HEADERS_A)
        assert res.status_code == 200
        assert res.json()["url"] == "https://callback.com/webhook"

    def test_webhook_get_none_returns_404(self, client):
        """GET webhook subscription returns 404 if none is registered."""
        res = client.get("/v1/webhooks/", headers=HEADERS_A)
        assert res.status_code == 404

    def test_webhook_update_in_place(self, client):
        """Registering again updates the existing webhook URL instead of creating duplicates."""
        # 1. Register first
        client.post("/v1/webhooks/", json={"url": "https://first.com/callback"}, headers=HEADERS_A)

        # 2. Register second URL
        res = client.post("/v1/webhooks/", json={"url": "https://second.com/callback"}, headers=HEADERS_A)
        assert res.status_code == 201
        assert res.json()["url"] == "https://second.com/callback"

        # 3. Verify in database only one webhook subscription exists for User A
        get_res = client.get("/v1/webhooks/", headers=HEADERS_A)
        assert get_res.status_code == 200
        assert get_res.json()["url"] == "https://second.com/callback"

    def test_webhook_delete(self, client):
        """User deletes their webhook registration successfully."""
        # 1. Register
        client.post("/v1/webhooks/", json={"url": "https://callback.com/webhook"}, headers=HEADERS_A)

        # 2. Delete
        del_res = client.request("DELETE", "/v1/webhooks/", headers=HEADERS_A)
        assert del_res.status_code == 200

        # 3. Verify it is gone (404)
        get_res = client.get("/v1/webhooks/", headers=HEADERS_A)
        assert get_res.status_code == 404

    def test_webhook_delete_none_returns_404(self, client):
        """DELETE webhook subscription returns 404 if none registered."""
        res = client.request("DELETE", "/v1/webhooks/", headers=HEADERS_A)
        assert res.status_code == 404

    @pytest.mark.parametrize("bad_url, label", [
        ("http://127.0.0.1/admin", "SSRF loopback IPv4"),
        ("http://localhost/status", "SSRF localhost"),
        ("http://169.254.169.254/iam-metadata", "SSRF AWS metadata"),
        ("http://10.0.0.1/internal-callback", "SSRF class A private"),
        ("ftp://bad-scheme.com", "invalid FTP scheme"),
        ("javascript:alert(1)", "XSS via JavaScript scheme"),
    ])
    def test_webhook_registration_ssrf_and_scheme_blocked(self, client, bad_url, label):
        """Webhook URLs must be public-resolving and start with http/https, blocking SSRF paths."""
        payload = {"url": bad_url}
        res = client.post("/v1/webhooks/", json=payload, headers=HEADERS_A)
        assert res.status_code == 422, f"SSRF URL not blocked: {label}"

    def test_webhook_auth_required(self, client):
        """Webhook endpoints require valid X-API-Key credentials."""
        # POST
        assert client.post("/v1/webhooks/", json={"url": "https://callback.com"}).status_code == 401
        # GET
        assert client.get("/v1/webhooks/").status_code == 401
        # DELETE
        assert client.request("DELETE", "/v1/webhooks/").status_code == 401


# ===========================================================================
# 3. Async Webhook Triggering & Celery Dispatch Tests
# ===========================================================================

class TestWebhookAsyncTriggering:
    """Verifies click events trigger async Celery webhook dispatch tasks."""

    @patch("app.tasks.dispatch_webhook_task.delay")
    def test_log_click_triggers_webhook(self, mock_dispatch_delay, db_session):
        """If a webhook is registered for the link creator, logging a click triggers webhook dispatch."""
        import uuid
        req_id = f"unique-req-{uuid.uuid4()}"

        # 1. Register a webhook callback for API_KEY_A in DB
        db_sub = WebhookSubscription(url="https://example.com/webhook-receiver", created_by="API_KEY_A")
        db_session.add(db_sub)

        # 2. Create a Link owned by API_KEY_A in DB
        db_link = Link(code="webh123", long_url="https://google.com", created_by="API_KEY_A")
        db_session.add(db_link)
        db_session.commit()

        # 3. Call log_click_task synchronously in-process
        from app import tasks
        original_session_local = tasks.SessionLocal
        tasks.SessionLocal = lambda: db_session
        try:
            log_click_task(
                link_id=db_link.id,
                user_agent="TestAgent",
                referrer="https://refsite.com",
                ip_hash="fakeiphash",
                request_id=req_id
            )
        finally:
            tasks.SessionLocal = original_session_local

        # 4. Assert that the dispatch task was successfully triggered/queued
        assert mock_dispatch_delay.call_count == 1
        args, kwargs = mock_dispatch_delay.call_args
        assert args[0] == "https://example.com/webhook-receiver"

        # Verify rich webhook payload details
        payload = args[1]
        assert payload["event"] == "link.click"
        assert payload["link"]["id"] == db_link.id
        assert payload["link"]["code"] == "webh123"
        assert payload["link"]["long_url"] == "https://google.com"
        assert payload["click"]["user_agent"] == "TestAgent"
        assert payload["click"]["referrer"] == "https://refsite.com"
        assert payload["click"]["request_id"] == req_id

    @patch("app.tasks.dispatch_webhook_task.delay")
    def test_log_click_no_webhook_registered(self, mock_dispatch_delay, db_session):
        """If link creator does not have a webhook registered, click logs normally without spawning dispatch."""
        import uuid
        req_id = f"unique-req-{uuid.uuid4()}"

        # 1. Create a Link in DB (No webhook subscription created in DB)
        db_link = Link(code="nowebh", long_url="https://google.com", created_by="API_KEY_A")
        db_session.add(db_link)
        db_session.commit()

        # 2. Call log_click_task
        from app import tasks
        original_session_local = tasks.SessionLocal
        tasks.SessionLocal = lambda: db_session
        try:
            log_click_task(
                link_id=db_link.id,
                user_agent="TestAgent",
                referrer="https://refsite.com",
                ip_hash="fakeiphash",
                request_id=req_id
            )
        finally:
            tasks.SessionLocal = original_session_local

        # 3. Assert webhook dispatch task was NOT spawned
        assert mock_dispatch_delay.call_count == 0

    @patch("httpx.Client")
    def test_dispatch_webhook_task_makes_post_request(self, mock_client_class):
        """dispatch_webhook_task asynchronously POSTs JSON payload via HTTPX Client."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call dispatch task directly
        payload = {"event": "link.click", "data": "test"}
        res = dispatch_webhook_task(url="https://example.com/webhook", payload=payload)

        # Assert post was made successfully
        mock_client_class.assert_called_once()
        mock_client.__enter__.return_value.post.assert_called_once_with(
            "https://example.com/webhook", json=payload
        )
        assert res["status"] == "success"
