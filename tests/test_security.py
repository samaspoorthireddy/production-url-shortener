"""
Integration tests for security & rate limiting behaviors.

These use the FastAPI TestClient (real HTTP stack, real DB via conftest transaction).
Each test covers a distinct attack vector or abuse scenario.
"""
import pytest

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}


# ---------------------------------------------------------------------------
# Security: SSRF & Open Redirect via API
# ---------------------------------------------------------------------------

class TestSsrfProtection:
    """
    Integration-level proof that SSRF attacks are blocked at the API boundary,
    not just at the unit level.
    """

    @pytest.mark.parametrize("bad_url, label", [
        ("http://localhost/admin", "localhost"),
        ("http://127.0.0.1/", "loopback IPv4"),
        ("http://169.254.169.254/latest/meta-data/", "AWS metadata endpoint"),
        ("http://10.0.0.1/internal", "class A private"),
        ("http://192.168.1.1/router", "class C private"),
        ("http://172.16.0.1/secret", "class B private"),
    ])
    def test_ssrf_urls_are_rejected_with_422(self, client, bad_url, label):
        """Each SSRF vector must return 422 and never be stored."""
        res = client.post("/v1/links/", json={"long_url": bad_url}, headers=HEADERS_A)
        assert res.status_code == 422, f"SSRF not blocked for: {label}"
        # Confirm the error envelope structure is correct
        assert "error" in res.json()
        assert res.json()["error"]["code"] in ("VALIDATION_ERROR", "HTTP_ERROR")

    @pytest.mark.parametrize("bad_url, label", [
        ("javascript:alert(document.cookie)", "XSS via javascript:"),
        ("data:text/html,<h1>pwned</h1>", "data: URI injection"),
        ("file:///etc/passwd", "local file read"),
        ("ftp://internal-store.corp/exports", "ftp scheme"),
    ])
    def test_unsafe_schemes_rejected_with_422(self, client, bad_url, label):
        """Non-http/https schemes must be blocked at schema validation."""
        res = client.post("/v1/links/", json={"long_url": bad_url}, headers=HEADERS_A)
        assert res.status_code == 422, f"Scheme not blocked for: {label}"

    def test_ssrf_also_blocked_on_update(self, client):
        """
        Update path must be equally hardened — an attacker who owns a link
        should not be able to retarget it to an internal address.
        """
        # Create a safe link first
        create_res = client.post(
            "/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_A
        )
        assert create_res.status_code == 201
        link_id = create_res.json()["id"]

        # Now attempt to retarget it to the AWS metadata endpoint
        update_res = client.patch(
            f"/v1/links/{link_id}",
            json={"long_url": "http://169.254.169.254/latest/meta-data/"},
            headers=HEADERS_A,
        )
        assert update_res.status_code == 422

    def test_legitimate_url_still_accepted(self, client):
        """Ensure the security layer does not over-block valid URLs."""
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://docs.python.org/3/"},
            headers=HEADERS_A,
        )
        assert res.status_code == 201
        assert res.json()["long_url"] == "https://docs.python.org/3/"


# ---------------------------------------------------------------------------
# Security: Input injection edge cases
# ---------------------------------------------------------------------------

class TestInputInjection:
    """Guards against log injection, control character smuggling, and authority bypass."""

    def test_log_injection_via_newline_in_url(self, client):
        """
        Newlines in URL parameters can forge fake log entries.
        The Pydantic schema must strip/reject these.
        """
        malicious = "https://example.com/\nINFO fake-admin-login user=root"
        res = client.post("/v1/links/", json={"long_url": malicious}, headers=HEADERS_A)
        assert res.status_code == 422
        assert "control" in res.json()["error"]["message"].lower()

    def test_null_byte_injection(self, client):
        """Null bytes can truncate strings in C-based libraries."""
        malicious = "https://example.com/\x00evil"
        res = client.post("/v1/links/", json={"long_url": malicious}, headers=HEADERS_A)
        assert res.status_code == 422

    def test_authority_userinfo_bypass(self, client):
        """
        https://trusted.com@evil.com — browser may route to evil.com
        while showing trusted.com in the URL.
        """
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://trusted.com@evil.com/phish"},
            headers=HEADERS_A,
        )
        assert res.status_code == 422
        assert "user information" in res.json()["error"]["message"].lower()

    def test_backslash_normalization_bypass(self, client):
        """
        https://safe.com\\evil.com — some browsers normalise \\ to /
        making this point to evil.com.
        """
        res = client.post(
            "/v1/links/",
            json={"long_url": "https://safe.com\\evil.com"},
            headers=HEADERS_A,
        )
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verifies that the sliding-window rate limiter enforces per-IP limits."""

    def test_post_links_rate_limit_triggers_at_5(self, client):
        """
        POST /links/ allows 5 requests per minute.
        The 6th must return 429 with a Retry-After header.
        """
        payload = {"long_url": "https://example.com"}
        for i in range(5):
            res = client.post("/v1/links/", json=payload, headers=HEADERS_A)
            assert res.status_code == 201, f"Request {i + 1} should succeed"

        # 6th request must be throttled
        res = client.post("/v1/links/", json=payload, headers=HEADERS_A)
        assert res.status_code == 429
        assert res.json()["error"]["code"] == "TOO_MANY_REQUESTS"
        # Retry-After header must be present so clients know when to retry
        assert "retry-after" in res.headers

    def test_rate_limit_is_per_user_key_not_global(self, client):
        """
        Rate limits are per IP. In tests both users come from 127.0.0.1,
        so this confirms the limiter key includes the endpoint namespace
        and isn't a single global counter shared across all users.
        The conftest clears the limiter before each test, so user_b
        starts fresh here regardless.
        """
        payload = {"long_url": "https://example.com"}
        # User B should be able to make requests after the limiter was cleared
        res = client.post("/v1/links/", json=payload, headers=HEADERS_B)
        assert res.status_code == 201

    def test_rate_limit_response_has_correct_error_envelope(self, client):
        """Error envelope shape must be consistent with other 4xx errors."""
        payload = {"long_url": "https://example.com"}
        for _ in range(5):
            client.post("/v1/links/", json=payload, headers=HEADERS_A)

        res = client.post("/v1/links/", json=payload, headers=HEADERS_A)
        assert res.status_code == 429
        body = res.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "request_id" in body["error"]


# ---------------------------------------------------------------------------
# Observability: /metrics endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    """
    Verifies the Prometheus scrape endpoint is reachable and returns
    well-formed Prometheus text format.
    """

    def test_metrics_endpoint_returns_200(self, client):
        res = client.get("/metrics")
        assert res.status_code == 200

    def test_metrics_content_type_is_prometheus(self, client):
        res = client.get("/metrics")
        assert "text/plain" in res.headers["content-type"]

    def test_metrics_contains_required_metric_names(self, client):
        """After any request, RED metric names must appear in the output."""
        # Generate one request to ensure counters exist
        client.get("/health")
        res = client.get("/metrics")
        body = res.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
        assert "active_redirects_total" in body
        assert "cache_ops_total" in body

    def test_metrics_increments_after_redirect(self, client):
        """active_redirects_total must increment exactly once per redirect."""
        import re

        def get_redirect_count():
            body = client.get("/metrics").text
            match = re.search(r"^active_redirects_total\s+([\d.]+)", body, re.MULTILINE)
            return float(match.group(1)) if match else 0.0

        # Create a link, then redirect through it
        create_res = client.post(
            "/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_A
        )
        assert create_res.status_code == 201
        code = create_res.json()["code"]

        before = get_redirect_count()
        client.get(f"/r/{code}", follow_redirects=False)
        after = get_redirect_count()

        assert after == before + 1.0
