"""
url_validator.py — Defence-in-depth URL validation

Protects against:
  1. Dangerous URL schemes (javascript:, file://, data:, ftp://, etc.)
  2. Open Redirect to private/loopback/link-local IP ranges (SSRF)
  3. Known malicious or reserved hostnames (localhost, internal hostnames)
"""

import ipaddress
import socket
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. ALLOWED SCHEMES — only http and https are safe for a redirector
# ---------------------------------------------------------------------------
ALLOWED_SCHEMES = {"http", "https"}

# ---------------------------------------------------------------------------
# 2. BLOCKED HOSTNAMES — reserved or internal names regardless of resolved IP
# ---------------------------------------------------------------------------
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "ip6-localhost",
    "ip6-loopback",
    "ip6-localnet",
    "ip6-mcastprefix",
    "ip6-allnodes",
    "ip6-allrouters",
    "ip6-allhosts",
}

# ---------------------------------------------------------------------------
# 3. PRIVATE / RESERVED IP NETWORKS — blocks SSRF via DNS rebinding
# ---------------------------------------------------------------------------
PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("10.0.0.0/8"),          # Private class A
    ipaddress.ip_network("100.64.0.0/10"),       # Shared address space (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local / AWS metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),       # Private class B
    ipaddress.ip_network("192.0.0.0/24"),        # IETF protocol assignments
    ipaddress.ip_network("192.168.0.0/16"),      # Private class C
    ipaddress.ip_network("198.18.0.0/15"),       # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2 (documentation)
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3 (documentation)
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    ipaddress.ip_network("::1/128"),             # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),            # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),           # IPv6 link-local
]


def _is_private_ip(hostname: str) -> bool:
    """
    Resolves the hostname to its IP address(es) and checks if any of them
    fall within a private or reserved IP range.

    Fast-path: if the hostname IS already a literal IP address (e.g. "10.0.0.1",
    "169.254.169.254"), parse it directly — no DNS round-trip needed, no timeout risk.

    For actual hostnames, a 2-second DNS timeout prevents event-loop stalls from
    slow or unresolvable names.
    """
    # --- Fast-path: literal IP address (no DNS needed) ---
    try:
        ip = ipaddress.ip_address(hostname)  # raises ValueError if not a valid IP
        for network in PRIVATE_NETWORKS:
            if ip in network:
                logger.warning(
                    "url_validator: literal IP=%s is in private network=%s — SSRF blocked",
                    ip,
                    network,
                )
                return True
        return False  # It's a routable public IP — allow it
    except ValueError:
        pass  # Not a literal IP, fall through to DNS resolution

    # --- Hostname: resolve with a strict 2-second timeout ---
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(2.0)
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.timeout:
        logger.warning("url_validator: DNS resolution timed out for hostname=%r — blocking", hostname)
        return True
    except socket.gaierror:
        logger.warning("url_validator: DNS resolution failed for hostname=%r — blocking", hostname)
        return True
    finally:
        socket.setdefaulttimeout(old_timeout)

    for addr_info in addr_infos:
        raw_ip = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue

        for network in PRIVATE_NETWORKS:
            if ip in network:
                logger.warning(
                    "url_validator: hostname=%r resolved to private IP=%s (network=%s) — SSRF blocked",
                    hostname,
                    ip,
                    network,
                )
                return True

    return False


def validate_destination_url(url: str) -> str:
    """
    Validates a destination URL is safe to store and redirect to.

    Raises ValueError with a human-readable message on failure.
    Returns the (stripped) URL on success.

    Layers:
      1. Parse & scheme allowlist
      2. Hostname presence check
      3. Blocked hostname exact-match
      4. Private IP / SSRF guard via DNS resolution
    """
    url = url.strip()

    # --- Layer 1: Parse and scheme check ---
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Malformed URL: could not be parsed.")

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsafe URL scheme '{scheme}': only 'http' and 'https' are allowed. "
            f"Schemes like 'javascript:', 'file://', and 'data:' are blocked."
        )

    # --- Layer 2: Hostname must be present ---
    hostname = parsed.hostname  # lowercase, port stripped
    if not hostname:
        raise ValueError("URL must contain a valid hostname.")

    # --- Layer 3: Blocked hostname exact-match ---
    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError(
            f"Hostname '{hostname}' is a reserved name and cannot be used as a redirect destination."
        )

    # --- Layer 4: SSRF private IP guard (DNS resolution) ---
    if _is_private_ip(hostname):
        raise ValueError(
            f"Hostname '{hostname}' resolves to a private or reserved IP address. "
            f"Redirects to internal network addresses are not allowed (SSRF protection)."
        )

    logger.debug("url_validator: URL passed all security checks — url=%r", url)
    return url
