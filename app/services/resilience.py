import asyncio
import logging
import random
import pybreaker
from sqlalchemy.exc import TimeoutError as DBTimeoutError, OperationalError as DBOperationalError
import redis.exceptions as redis_exc

logger = logging.getLogger("url_shortener")

# Custom listener to log state changes in circuit breakers
class BreakerLogger(pybreaker.CircuitBreakerListener):
    def __init__(self, name: str):
        self.name = name

    def state_change(self, cb, old_state, new_state):
        logger.info(
            "circuit_state_change",
            extra={
                "dependency": self.name,
                "old_state": str(old_state),
                "new_state": str(new_state)
            }
        )

# Define DB circuit breaker: Open after 5 consecutive failures, retry after 30s
db_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    listeners=[BreakerLogger("database")]
)

# Define Redis circuit breaker: Open after 5 consecutive failures, retry after 30s
redis_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    listeners=[BreakerLogger("redis")]
)

async def call_async_with_breaker(breaker: pybreaker.CircuitBreaker, func, *args, **kwargs):
    """
    Safely executes an async function within the pybreaker.CircuitBreaker state machine,
    handling state transitions, listeners, and custom exceptions.
    """
    # If the circuit is open and the reset timeout has elapsed, transition to half-open.
    # This prevents pybreaker's sync before_call from attempting to synchronously execute
    # our async coroutine function, which generates a RuntimeWarning.
    if breaker.current_state == "open":
        from datetime import datetime, timedelta
        from pybreaker import UTC
        opened_at = breaker._state_storage.opened_at
        if opened_at:
            timeout = timedelta(seconds=breaker.reset_timeout)
            if datetime.now(UTC) >= opened_at + timeout:
                breaker.half_open()

    state = breaker.state
    state.before_call(func, *args, **kwargs)
    for listener in breaker.listeners:
        listener.before_call(breaker, func, *args, **kwargs)
    try:
        result = await func(*args, **kwargs)
    except BaseException as e:
        state._handle_error(e, reraise=True)
    else:
        state._handle_success()
        return result

async def retry_with_backoff(
    fn,
    max_retries: int = 3,
    base_delay: float = 0.1,    # 100ms
    max_delay: float = 2.0,     # 2 seconds
    jitter: float = 0.05,       # +/- 50ms
    retryable_exceptions: tuple = (
        ConnectionError,
        asyncio.TimeoutError,
        OSError,
        DBTimeoutError,
        DBOperationalError,
        redis_exc.ConnectionError,
        redis_exc.TimeoutError
    )
):
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as e:
            last_error = e

            if attempt == max_retries:
                break

            # Exponential backoff with jitter
            exponential_delay = min(base_delay * (2 ** attempt), max_delay)
            jitter_offset = random.uniform(-jitter, jitter)
            delay = max(0, exponential_delay + jitter_offset)

            logger.warning(
                "retry_attempt",
                extra={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "delay_ms": round(delay * 1000),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

            await asyncio.sleep(delay)
        except Exception:
            # Non-retryable error (e.g. Validation, CircuitBreakerError) -- fail immediately
            raise

    raise last_error

async def execute_db_with_resilience(fn, timeout: float = 1.0):
    """
    Executes a blocking database function with a circuit breaker, timeout,
    and retry with exponential backoff. Runs the blocking query in a worker thread.
    """
    async def run_query():
        try:
            # Run the synchronous function in a separate thread pool thread and wait with timeout
            return await asyncio.wait_for(
                asyncio.to_thread(fn),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dependency_timeout",
                extra={
                    "dependency": "database",
                    "timeout_ms": round(timeout * 1000)
                }
            )
            # Re-raise as DBTimeoutError to make it retryable/catchable
            raise DBTimeoutError("Database query execution timed out")

    # Wrap the query call in the db_breaker and retry_with_backoff
    return await retry_with_backoff(
        lambda: call_async_with_breaker(db_breaker, run_query)
    )

async def execute_redis_with_resilience(fn, timeout: float = 0.5):
    """
    Executes an async Redis function with a circuit breaker, timeout,
    and retry with exponential backoff.
    """
    async def run_redis_cmd():
        try:
            return await asyncio.wait_for(
                fn(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dependency_timeout",
                extra={
                    "dependency": "redis",
                    "timeout_ms": round(timeout * 1000)
                }
            )
            raise redis_exc.TimeoutError("Redis command execution timed out")

    return await retry_with_backoff(
        lambda: call_async_with_breaker(redis_breaker, run_redis_cmd)
    )
