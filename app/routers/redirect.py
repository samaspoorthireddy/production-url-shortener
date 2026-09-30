import hashlib
import logging
from datetime import datetime, timezone
import pybreaker
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from models import ClickEvent
from app.services import links_service, cache_service
from app.services.resilience import execute_db_with_resilience
from app.dependencies import rate_limit_redirect
from app.config import settings
from app.metrics import record_redirect, record_cache_op

logger = logging.getLogger("url_shortener")

router = APIRouter(prefix="/r", tags=["Redirect"])


@router.get("/{code}", dependencies=[Depends(rate_limit_redirect)])
async def redirect_to_url(code: str, request: Request, db: Session = Depends(get_db)):
    """
    Handles public short link redirects. Performs lookup via Redis cache first,
    falling back to database if needed (Graceful Degradation).

    Lifecycle guards (checked in order):
      1. Expiry  — 410 Gone if expires_at is in the past
      2. Click cap — 410 Gone if click count >= max_clicks

    Logs metadata (user-agent, referrer, hashed IP) and redirects with HTTP 302.
    """
    # 1. Cache lookup
    cached_val = await cache_service.get_redirect(code)

    if cached_val == cache_service.NEGATIVE_SENTINEL:
        record_cache_op("get", "hit")   # negative cache hit — still a cache hit
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found"
        )

    link_id = None
    long_url = None

    if cached_val is not None:
        record_cache_op("get", "hit")
        try:
            parts = cached_val.split(":", 1)
            if len(parts) == 2:
                link_id = int(parts[0])
                long_url = parts[1]
        except Exception as e:
            logger.warning(f"Failed to parse cached value '{cached_val}': {str(e)}")
            link_id = None
            long_url = None

    # 2. Cache miss or parsing fallback: Query PostgreSQL database
    if long_url is None or link_id is None:
        record_cache_op("get", "miss")
        try:
            db_link = await execute_db_with_resilience(lambda: links_service.get_link_by_code(db, code))
        except pybreaker.CircuitBreakerError as cb_exc:
            logger.warning(f"Database circuit open on cache miss for code '{code}'. Error: {str(cb_exc)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service is temporarily unavailable. Please retry shortly."
            )
        except Exception as exc:
            raise exc

        if not db_link:
            # Prevent stampede via negative lookup caching (60s TTL)
            await cache_service.set_negative_lookup(code)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found"
            )
        link_id = db_link.id
        long_url = db_link.long_url

        # Cache TTL: shorten to match expiry window if expires_at is set
        ttl = 300
        if db_link.expires_at:
            seconds_left = int((db_link.expires_at - datetime.now(timezone.utc)).total_seconds())
            if seconds_left <= 0:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="link expired"
                )
            ttl = min(ttl, seconds_left)

        await cache_service.set_redirect(code, f"{link_id}:{long_url}", ttl=ttl)
    else:
        # We got a cache hit — still need to verify expiry against the DB
        # (cache TTL is already shortened, but we re-check if it slipped through)
        try:
            db_link = await execute_db_with_resilience(lambda: links_service.get_link_by_code(db, code))
        except Exception as e:
            logger.warning(
                f"Database unavailable during cache hit verification for code '{code}'. "
                f"Proceeding to redirect client (graceful degradation). Error: {str(e)}"
            )
            db_link = None

    # -----------------------------------------------------------------------
    # Lifecycle Guard 1: Expiry check (authoritative — always use DB time)
    # -----------------------------------------------------------------------
    if db_link and db_link.expires_at:
        now = datetime.now(timezone.utc)
        exp = db_link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            # Evict the stale cache entry so future requests also get 410
            await cache_service.invalidate_redirect(code)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="link expired"
            )

    # -----------------------------------------------------------------------
    # Lifecycle Guard 2: Click cap check
    # -----------------------------------------------------------------------
    if db_link and db_link.max_clicks is not None:
        try:
            click_count = await execute_db_with_resilience(
                lambda: (
                    db.query(func.count(ClickEvent.id))
                    .filter(ClickEvent.link_id == link_id)
                    .scalar()
                ) or 0
            )
        except Exception as e:
            logger.warning(
                f"Database unavailable during click limit check for link_id={link_id}. "
                f"Bypassing click limit enforcement. Error: {str(e)}"
            )
            click_count = 0

        if click_count >= db_link.max_clicks:
            await cache_service.invalidate_redirect(code)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="link click limit reached"
            )

    # Extract client headers safely
    user_agent = request.headers.get("user-agent")
    referrer = request.headers.get("referer")  # spelled 'referer' in HTTP headers

    # Privacy Safeguard: Salt and Hash the IP address (never store raw PII)
    client_ip = request.client.host if request.client else "unknown"
    ip_salt = settings.ip_hash_salt
    ip_hash = hashlib.sha256(f"{client_ip}:{ip_salt}".encode("utf-8")).hexdigest()

    # Asynchronously record click events via Celery background tasks
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        import uuid
        request_id = str(uuid.uuid4())

    try:
        from app.tasks import log_click_task
        log_click_task.delay(
            link_id=link_id,
            user_agent=user_agent,
            referrer=referrer,
            ip_hash=ip_hash,
            request_id=request_id
        )
        logger.info(f"Successfully enqueued click event for link_id={link_id} (request_id={request_id})")
    except Exception as e:
        # Graceful Degradation: If Redis/broker is offline, log a warning and proceed
        logger.error(
            f"Broker offline: Failed to enqueue click analytics for link_id={link_id} (request_id={request_id}). "
            f"Error: {str(e)}. Proceeding to redirect client anyway."
        )

    # 302 Found is ideal for short URLs so that clicks are always tracked via the server
    record_redirect()
    return RedirectResponse(
        url=long_url,
        status_code=status.HTTP_302_FOUND
    )
