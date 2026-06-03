import time
from threading import Lock
from fastapi import Header, HTTPException, Request, status

# API key definitions matching our static user matrix
API_KEYS = {
    "API_KEY_A": "user_a",
    "API_KEY_B": "user_b",
}


async def get_current_user(x_api_key: str = Header(None, alias="X-API-Key")) -> str:
    """
    Dependency that extracts the API key from the header.
    Returns the username if valid, otherwise raises a 401 Unauthorized exception.

    Defense-in-depth validation:
      1. Header must be present (not None)
      2. Header must contain non-whitespace content (not empty/blank)
      3. Key must match a known user in the API_KEYS registry
    """
    # Guard 1: header missing entirely
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing from headers. Use X-API-Key: <your_key>."
        )
    # Guard 2: header present but empty or whitespace-only
    if not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing from headers. Use X-API-Key: <your_key>."
        )
    user = API_KEYS.get(x_api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key provided."
        )
    return user


class RateLimiter:
    """
    A thread-safe, in-memory rate limiter that tracks client requests per IP and endpoint.

    Analogy: Rate limiting is like a nightclub bouncer who only lets in a certain number of guests
    per minute. Once that limit is reached, any new guest is turned away (or told to wait) until
    the next minute starts. In our web application, this protects the server from being overwhelmed
    by a flood of requests from a single client.
    """

    def __init__(self):
        self.requests = {}  # Maps (client_ip, endpoint) to a list of timestamps
        self.lock = Lock()

    def check_rate_limit(self, request: Request, endpoint: str, limit: int, period: int = 60):
        # Real-IP extraction: trust proxy forwarding headers before falling back to
        # the TCP socket address (which is always the load balancer behind a proxy).
        # X-Forwarded-For may contain a comma-separated chain; take the leftmost entry
        # (the original client). X-Real-IP is set by Nginx single-proxy deployments.
        forwarded_for = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip.strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        key = (client_ip, endpoint)
        now = time.time()

        with self.lock:
            if key not in self.requests:
                self.requests[key] = []

            # Clean up timestamps that fall outside the sliding time window (60s)
            self.requests[key] = [t for t in self.requests[key] if now - t < period]

            # If the client has breached the limit, raise 429 and supply a Retry-After header
            if len(self.requests[key]) >= limit:
                oldest_request = self.requests[key][0]
                retry_after = int(period - (now - oldest_request))
                if retry_after <= 0:
                    retry_after = 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down.",
                    headers={"Retry-After": str(retry_after)}
                )

            # Record the timestamp of the successful request
            self.requests[key].append(now)


limiter = RateLimiter()


def rate_limit_post_links(request: Request):
    """
    Limits POST /links/ to 5 requests per minute.
    """
    limiter.check_rate_limit(request, "create_link", limit=5)


def rate_limit_redirect(request: Request):
    """
    Limits GET /r/{code} to 60 requests per minute per IP.
    Generous enough for genuine users; tight enough to stop link-enumeration bots.
    """
    limiter.check_rate_limit(request, "redirect", limit=60)


def rate_limit_search(request: Request):
    """
    Limits GET /links/search to 20 requests per minute per IP.
    Search queries are expensive (FTS index scans) so we apply a tighter cap.
    """
    limiter.check_rate_limit(request, "search", limit=20)
