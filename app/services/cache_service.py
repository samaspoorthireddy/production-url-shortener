import logging
import os
from typing import Optional
import redis.asyncio as aioredis
from app.config import settings
from app.services.resilience import execute_redis_with_resilience

logger = logging.getLogger("url_shortener")

# Initialize Redis client using pool configuration
# We load the connection URL from the centralized configuration settings
REDIS_URL = settings.redis_url

# Setup connection pool
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)


# Prefix to ensure key isolation between cache concerns.
# IMPORTANT: each prefix must be unique — sharing a namespace between two
# different systems means an operation on one (e.g. cache invalidation on
# delete) can silently corrupt the other (e.g. analytics dedup flags).
KEY_PREFIX = "redirect:"          # short-code → target URL for fast redirects
DEDUP_PREFIX = "analytics:dedup:"  # job_id → processed flag for analytics dedup
NEGATIVE_SENTINEL = "__NULL__"


async def get_redirect(code: str) -> Optional[str]:
    """
    Retrieves the cached long URL for the given short-code.
    Returns:
      - The cached URL (string) on a hit.
      - "__NULL__" on a cached negative lookup hit (non-existence).
      - None on a cache miss, or if Redis is down.
    """
    key = f"{KEY_PREFIX}{code}"
    try:
        val = await execute_redis_with_resilience(
            lambda: redis_client.get(key)
        )
        if val is not None:
            logger.info(f"Cache HIT for code '{code}' -> '{val}'")
        else:
            logger.info(f"Cache MISS for code '{code}'")
        return val
    except Exception as e:
        logger.warning(f"Redis get_redirect failed for code '{code}', degrading gracefully. Error: {str(e)}")
        return None


async def set_redirect(code: str, target: str, ttl: int = 300) -> bool:
    """
    Caches the mapping from short-code to long URL with a TTL.
    """
    key = f"{KEY_PREFIX}{code}"
    try:
        await execute_redis_with_resilience(
            lambda: redis_client.set(key, target, ex=ttl)
        )
        logger.info(f"Cached redirect mapping: '{code}' -> '{target}' (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Redis set_redirect failed for code '{code}', degrading gracefully. Error: {str(e)}")
        return False


async def set_negative_lookup(code: str, ttl: int = 60) -> bool:
    """
    Caches a non-existent short-code with a short TTL sentinel value to prevent cache stampedes.
    """
    key = f"{KEY_PREFIX}{code}"
    try:
        await execute_redis_with_resilience(
            lambda: redis_client.set(key, NEGATIVE_SENTINEL, ex=ttl)
        )
        logger.info(f"Cached negative lookup for non-existent code '{code}' (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Redis set_negative_lookup failed for code '{code}', degrading gracefully. Error: {str(e)}")
        return False


async def invalidate_redirect(code: str) -> bool:
    """
    Evicts the short-code mapping from the cache (for update/delete consistency).
    """
    key = f"{KEY_PREFIX}{code}"
    try:
        res = await execute_redis_with_resilience(
            lambda: redis_client.delete(key)
        )
        logger.info(f"Cache invalidated for code '{code}', keys deleted: {res}")
        return True
    except Exception as e:
        logger.warning(f"Redis invalidate_redirect failed for code '{code}', degrading gracefully. Error: {str(e)}")
        return False


async def is_analytics_job_processed(job_id: str) -> bool:
    """
    Checks whether an analytics job has already been processed.
    Uses a dedicated 'analytics:dedup:' prefix, entirely separate from
    the redirect cache namespace, so link deletions never accidentally
    clear deduplication flags for in-flight analytics jobs.
    """
    key = f"{DEDUP_PREFIX}{job_id}"
    try:
        val = await execute_redis_with_resilience(
            lambda: redis_client.get(key)
        )
        return val is not None
    except Exception as e:
        logger.warning(f"Redis dedup check failed for job '{job_id}', assuming not processed. Error: {str(e)}")
        return False


async def mark_analytics_job_processed(job_id: str, ttl: int = 86400) -> bool:
    """
    Marks an analytics job as processed in the dedup cache.
    TTL defaults to 24 hours — long enough to prevent replay within a
    reasonable window, without growing the Redis keyspace indefinitely.
    """
    key = f"{DEDUP_PREFIX}{job_id}"
    try:
        await execute_redis_with_resilience(
            lambda: redis_client.set(key, "1", ex=ttl)
        )
        logger.info(f"Marked analytics job '{job_id}' as processed (TTL: {ttl}s)")
        return True
    except Exception as e:
        logger.warning(f"Redis dedup mark failed for job '{job_id}', degrading gracefully. Error: {str(e)}")
        return False
