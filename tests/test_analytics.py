"""
Integration tests for Module 16A: Advanced Analytics.

Four test classes mirroring the four analytics surfaces:
  1. TestAnalyticsSummary   — GET /analytics/summary
  2. TestLinkAnalytics      — upgraded GET /{id}/analytics (period counts)
  3. TestTimeseries         — GET /{id}/analytics/timeseries
  4. TestReferrerBreakdown  — GET /{id}/analytics/referrers
  5. TestDeviceBreakdown    — GET /{id}/analytics/devices
  6. TestUAParser           — pure unit tests for the UA parser (no HTTP)
"""
import pytest
from datetime import datetime, timedelta, timezone
from models import ClickEvent

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_link(client):
    """Create a link for user A and return the response JSON."""
    res = client.post(
        "/v1/links/",
        json={"long_url": "https://example.com"},
        headers=HEADERS_A,
    )
    assert res.status_code == 201
    return res.json()


def insert_clicks(db_session, link_id: int, uas=None, referrers=None, days_ago=None):
    """
    Insert ClickEvent rows directly into the test DB.
    uas / referrers / days_ago are parallel lists.
    """
    n = max(
        len(uas or []),
        len(referrers or []),
        len(days_ago or []),
        1,
    )
    uas = (uas or [None]) * n
    referrers = (referrers or [None]) * n
    days_ago = (days_ago or [0]) * n

    now = datetime.now(timezone.utc)
    for ua, ref, d in zip(uas[:n], referrers[:n], days_ago[:n]):
        db_session.add(
            ClickEvent(
                link_id=link_id,
                user_agent=ua,
                referrer=ref,
                clicked_at=now - timedelta(days=d),
            )
        )
    db_session.commit()


# ---------------------------------------------------------------------------
# 1. Summary endpoint
# ---------------------------------------------------------------------------

class TestAnalyticsSummary:
    """GET /v1/links/analytics/summary"""

    def test_summary_returns_200(self, client):
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_A)
        assert res.status_code == 200

    def test_summary_has_required_keys(self, client):
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_A)
        body = res.json()
        assert "total_links" in body
        assert "total_clicks" in body
        assert "clicks_today" in body
        assert "top_links" in body

    def test_summary_reflects_created_links(self, client):
        make_link(client)
        make_link(client)
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_A)
        assert res.json()["total_links"] >= 2

    def test_summary_top_links_is_list(self, client):
        make_link(client)
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_A)
        assert isinstance(res.json()["top_links"], list)

    def test_summary_top_links_has_required_fields(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], days_ago=[0])
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_A)
        top = res.json()["top_links"]
        assert len(top) >= 1
        assert "id" in top[0]
        assert "code" in top[0]
        assert "clicks" in top[0]

    def test_summary_requires_auth(self, client):
        res = client.get("/v1/links/analytics/summary")
        assert res.status_code == 401

    def test_summary_scoped_to_user(self, client):
        """User B's summary must not include User A's links."""
        make_link(client)
        res = client.get("/v1/links/analytics/summary", headers=HEADERS_B)
        # User B has no links in this test — total_links should be 0
        assert res.json()["total_links"] == 0


# ---------------------------------------------------------------------------
# 2. Enriched single-link analytics
# ---------------------------------------------------------------------------

class TestLinkAnalytics:
    """Upgraded GET /v1/links/{id}/analytics with period counts."""

    def test_returns_200_with_no_clicks(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics", headers=HEADERS_A)
        assert res.status_code == 200

    def test_has_period_count_keys(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics", headers=HEADERS_A)
        body = res.json()
        assert "clicks_today" in body
        assert "clicks_this_week" in body
        assert "clicks_this_month" in body
        assert "total_clicks" in body

    def test_clicks_today_increments(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], days_ago=[0, 0])
        res = client.get(f"/v1/links/{link['id']}/analytics", headers=HEADERS_A)
        assert res.json()["clicks_today"] >= 2

    def test_old_clicks_not_in_today(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], days_ago=[5])  # 5 days ago
        res = client.get(f"/v1/links/{link['id']}/analytics", headers=HEADERS_A)
        assert res.json()["clicks_today"] == 0

    def test_ownership_enforced(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics", headers=HEADERS_B)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# 3. Timeseries
# ---------------------------------------------------------------------------

class TestTimeseries:
    """GET /v1/links/{id}/analytics/timeseries"""

    def test_returns_200(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/timeseries", headers=HEADERS_A)
        assert res.status_code == 200

    def test_response_shape(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/timeseries", headers=HEADERS_A)
        body = res.json()
        assert "granularity" in body
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_default_granularity_is_day(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/timeseries", headers=HEADERS_A)
        assert res.json()["granularity"] == "day"

    def test_hour_granularity_accepted(self, client):
        link = make_link(client)
        res = client.get(
            f"/v1/links/{link['id']}/analytics/timeseries?granularity=hour",
            headers=HEADERS_A,
        )
        assert res.status_code == 200
        assert res.json()["granularity"] == "hour"

    def test_invalid_granularity_returns_422(self, client):
        link = make_link(client)
        res = client.get(
            f"/v1/links/{link['id']}/analytics/timeseries?granularity=week",
            headers=HEADERS_A,
        )
        assert res.status_code == 422

    def test_clicks_appear_in_timeseries(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], days_ago=[0, 0, 1])
        res = client.get(f"/v1/links/{link['id']}/analytics/timeseries", headers=HEADERS_A)
        data = res.json()["data"]
        total = sum(d["clicks"] for d in data)
        assert total == 3

    def test_ownership_enforced(self, client):
        link = make_link(client)
        res = client.get(
            f"/v1/links/{link['id']}/analytics/timeseries", headers=HEADERS_B
        )
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# 4. Referrer breakdown
# ---------------------------------------------------------------------------

class TestReferrerBreakdown:
    """GET /v1/links/{id}/analytics/referrers"""

    def test_returns_200(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_A)
        assert res.status_code == 200

    def test_response_shape(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_A)
        body = res.json()
        assert "total_clicks" in body
        assert "data" in body

    def test_null_referrer_bucketed_as_direct(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], referrers=[None, None])
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_A)
        domains = [item["referrer"] for item in res.json()["data"]]
        assert "Direct" in domains

    def test_referrer_domain_extracted(self, client, db_session):
        link = make_link(client)
        insert_clicks(
            db_session, link["id"],
            referrers=["https://www.google.com/search?q=test", "https://google.com/"],
        )
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_A)
        domains = [item["referrer"] for item in res.json()["data"]]
        assert "google.com" in domains

    def test_pct_sums_to_100(self, client, db_session):
        link = make_link(client)
        insert_clicks(
            db_session, link["id"],
            referrers=["https://google.com", "https://twitter.com", None],
        )
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_A)
        total_pct = sum(item["pct"] for item in res.json()["data"])
        assert abs(total_pct - 100.0) < 1.0  # allow floating point rounding

    def test_top_n_respected(self, client, db_session):
        link = make_link(client)
        refs = [f"https://site{i}.com" for i in range(20)]
        insert_clicks(db_session, link["id"], referrers=refs)
        res = client.get(
            f"/v1/links/{link['id']}/analytics/referrers?top_n=5", headers=HEADERS_A
        )
        assert len(res.json()["data"]) <= 5

    def test_ownership_enforced(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/referrers", headers=HEADERS_B)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# 5. Device / browser breakdown
# ---------------------------------------------------------------------------

class TestDeviceBreakdown:
    """GET /v1/links/{id}/analytics/devices"""

    def test_returns_200(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_A)
        assert res.status_code == 200

    def test_response_has_required_keys(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_A)
        body = res.json()
        assert "browsers" in body
        assert "os" in body
        assert "device_types" in body

    def test_chrome_detected(self, client, db_session):
        link = make_link(client)
        chrome_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        insert_clicks(db_session, link["id"], uas=[chrome_ua])
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_A)
        assert res.json()["browsers"].get("Chrome", 0) >= 1

    def test_mobile_detected(self, client, db_session):
        link = make_link(client)
        mobile_ua = (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
        )
        insert_clicks(db_session, link["id"], uas=[mobile_ua])
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_A)
        assert res.json()["device_types"].get("mobile", 0) >= 1

    def test_unknown_ua_bucketed_as_other(self, client, db_session):
        link = make_link(client)
        insert_clicks(db_session, link["id"], uas=[None])
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_A)
        assert res.json()["browsers"].get("Other", 0) >= 1

    def test_ownership_enforced(self, client):
        link = make_link(client)
        res = client.get(f"/v1/links/{link['id']}/analytics/devices", headers=HEADERS_B)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# 6. UA Parser — pure unit tests (no HTTP)
# ---------------------------------------------------------------------------

class TestUAParser:
    """Direct unit tests for app/services/ua_parser.py."""

    def test_chrome_on_windows(self):
        from app.services.ua_parser import parse_ua
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        r = parse_ua(ua)
        assert r.browser == "Chrome"
        assert r.os == "Windows"
        assert r.device_type == "desktop"

    def test_firefox_on_linux(self):
        from app.services.ua_parser import parse_ua
        ua = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
        r = parse_ua(ua)
        assert r.browser == "Firefox"
        assert r.os == "Linux"
        assert r.device_type == "desktop"

    def test_safari_on_ios(self):
        from app.services.ua_parser import parse_ua
        ua = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )
        r = parse_ua(ua)
        assert r.browser == "Safari"
        assert r.os == "iOS"
        assert r.device_type == "mobile"

    def test_edge_browser(self):
        from app.services.ua_parser import parse_ua
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 Edg/124.0"
        )
        r = parse_ua(ua)
        assert r.browser == "Edge"

    def test_android_tablet(self):
        from app.services.ua_parser import parse_ua
        ua = (
            "Mozilla/5.0 (Linux; Android 13; SM-T870) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        r = parse_ua(ua)
        assert r.device_type == "tablet"

    def test_none_returns_other(self):
        from app.services.ua_parser import parse_ua
        r = parse_ua(None)
        assert r.browser == "Other"
        assert r.os == "Other"
        assert r.device_type == "desktop"

    def test_aggregate_ua_list(self):
        from app.services.ua_parser import aggregate_ua_list
        uas = [
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]
        result = aggregate_ua_list(uas)
        assert result["browsers"]["Chrome"] == 2
        assert result["browsers"]["Firefox"] == 1
        assert result["os"]["Windows"] == 2
        assert result["os"]["Linux"] == 1
