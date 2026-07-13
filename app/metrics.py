"""
app/metrics.py — Prometheus RED metrics for the URL shortener

Exposes:
  http_requests_total        — Counter by method, endpoint, status_code
  http_request_duration_seconds — Histogram of latency by method, endpoint
  active_redirects_total     — Counter of successful short-link redirects
  cache_hits_total           — Counter split by hit/miss
  url_validation_blocks_total — Counter of security-blocked URL attempts
"""

from prometheus_client import Counter, Histogram, Gauge, REGISTRY, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# R — Rate: total requests labelled by method, endpoint pattern, status class
# ---------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

# ---------------------------------------------------------------------------
# E — Errors: tracked as status_code label on HTTP_REQUESTS_TOTAL
#    (a request with status_code="5xx" or "4xx" is an error)
#    We also track security blocks explicitly for alerting
# ---------------------------------------------------------------------------
URL_VALIDATION_BLOCKS_TOTAL = Counter(
    "url_validation_blocks_total",
    "Total URL submissions blocked by security validation (SSRF, scheme, etc.)",
    ["reason"],  # e.g. "ssrf", "scheme", "hostname"
)

# ---------------------------------------------------------------------------
# D — Duration: latency histogram with standard Prometheus buckets (seconds)
# ---------------------------------------------------------------------------
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500, 1.0, 2.5, 5.0],
)

# ---------------------------------------------------------------------------
# Business metrics — useful for product dashboards alongside RED
# ---------------------------------------------------------------------------
REDIRECTS_TOTAL = Counter(
    "active_redirects_total",
    "Total successful short-link redirects served",
)

CACHE_OPS_TOTAL = Counter(
    "cache_ops_total",
    "Redis cache operations",
    ["operation", "result"],  # operation: get/set, result: hit/miss/error
)

# ---------------------------------------------------------------------------
# Business Gauge — tracks total URLs stored in database
# ---------------------------------------------------------------------------
STORED_URLS_COUNT = Gauge(
    "stored_urls_count",
    "Total number of shortened URLs stored in the database",
)

# System Gauge — tracks process memory usage in bytes
PROCESS_MEMORY_BYTES = Gauge(
    "process_memory_bytes",
    "Current RSS memory usage of the process in bytes",
)


def _normalize_endpoint(path: str) -> str:
    """
    Collapse dynamic path segments to avoid high cardinality in metric labels.

    High cardinality means one label value per unique short code, e.g.:
      /r/abc123, /r/xyz999, /r/q1w2e3 ...  → thousands of label combinations
    This explodes Prometheus memory. Instead we normalise to the route template:
      /r/{code}
      /links/{id}
    """
    import re
    # Collapse 8-char alphanumeric short codes  →  {code}
    path = re.sub(r"/r/[A-Za-z0-9]{4,12}", "/r/{code}", path)
    # Collapse numeric IDs  →  {id}
    path = re.sub(r"/links/\d+", "/links/{id}", path)
    return path


def record_request(method: str, path: str, status_code: int, duration_seconds: float):
    """
    Called by middleware after every request completes.
    Records all three RED signals in one call.
    """
    endpoint = _normalize_endpoint(path)
    status_class = f"{status_code // 100}xx"   # 200→"2xx", 429→"4xx", 500→"5xx"

    HTTP_REQUESTS_TOTAL.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_class,
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method,
        endpoint=endpoint,
    ).observe(duration_seconds)


def record_redirect():
    """Increment the redirect success counter."""
    REDIRECTS_TOTAL.inc()


def record_cache_op(operation: str, result: str):
    """
    Track Redis cache hit/miss/error rates.
    operation: "get" or "set"
    result:    "hit", "miss", or "error"
    """
    CACHE_OPS_TOTAL.labels(operation=operation, result=result).inc()


def record_security_block(reason: str):
    """
    Track how many URLs we block and why.
    reason: "ssrf_private_ip", "blocked_hostname", "unsafe_scheme", etc.
    """
    URL_VALIDATION_BLOCKS_TOTAL.labels(reason=reason).inc()


def get_metrics_output() -> tuple[bytes, str]:
    """Returns (body_bytes, content_type) for the /metrics endpoint."""
    # 1. Update database connection count gauge
    try:
        from database import SessionLocal
        from models import Link
        db = SessionLocal()
        try:
            count = db.query(Link).count()
            STORED_URLS_COUNT.set(count)
        finally:
            db.close()
    except Exception:
        # Prevent metrics endpoint from crashing if db is unreachable
        pass

    # 2. Update process RSS memory usage gauge
    try:
        import resource
        import sys
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != 'darwin':
            # Convert Linux KB to bytes
            usage *= 1024
        PROCESS_MEMORY_BYTES.set(usage)
    except Exception:
        pass

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
