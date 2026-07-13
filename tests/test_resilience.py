import asyncio
import pytest
import pybreaker
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.resilience import (
    retry_with_backoff,
    db_breaker,
    redis_breaker,
    execute_db_with_resilience,
    execute_redis_with_resilience,
    call_async_with_breaker
)
from sqlalchemy.exc import TimeoutError as DBTimeoutError

@pytest.mark.anyio
async def test_retry_with_backoff_success():
    """Verify retry_with_backoff returns the result on immediate success."""
    mock_fn = AsyncMock(return_value="success_val")
    result = await retry_with_backoff(mock_fn, max_retries=3, base_delay=0.01, jitter=0)
    assert result == "success_val"
    assert mock_fn.call_count == 1

@pytest.mark.anyio
async def test_retry_with_backoff_transient_failures_then_success():
    """Verify retry_with_backoff retries on transient errors and eventually succeeds."""
    call_count = 0
    async def mock_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise asyncio.TimeoutError("Transient timeout")
        return "success"

    result = await retry_with_backoff(mock_fn, max_retries=3, base_delay=0.01, jitter=0)
    assert result == "success"
    assert call_count == 3

@pytest.mark.anyio
async def test_retry_with_backoff_exhaust_retries():
    """Verify retry_with_backoff raises the final error after max retries."""
    mock_fn = AsyncMock(side_effect=asyncio.TimeoutError("Fatal timeout"))
    with pytest.raises(asyncio.TimeoutError):
        await retry_with_backoff(mock_fn, max_retries=2, base_delay=0.01, jitter=0)
    assert mock_fn.call_count == 3  # Initial + 2 retries

@pytest.mark.anyio
async def test_retry_with_backoff_non_retryable_error():
    """Verify retry_with_backoff fails fast without retrying on non-retryable exceptions."""
    mock_fn = AsyncMock(side_effect=ValueError("Validation failed"))
    with pytest.raises(ValueError):
        await retry_with_backoff(mock_fn, max_retries=3, base_delay=0.01, jitter=0)
    assert mock_fn.call_count == 1

@pytest.mark.anyio
async def test_circuit_breaker_trips_and_opens():
    """Verify circuit breaker opens after failure threshold is breached."""
    # Create a fresh breaker for the test to avoid polluting global state
    test_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10)
    assert test_breaker.current_state == "closed"

    async def fail_func():
        raise ConnectionError("DB down")

    # First 2 failures raise ConnectionError
    for _ in range(2):
        with pytest.raises(ConnectionError):
            await call_async_with_breaker(test_breaker, fail_func)

    # 3rd failure trips breaker and raises CircuitBreakerError
    with pytest.raises(pybreaker.CircuitBreakerError):
        await call_async_with_breaker(test_breaker, fail_func)

    assert test_breaker.current_state == "open"

    # Subsequent requests should raise CircuitBreakerError immediately without calling the function
    mock_fn = AsyncMock()
    with pytest.raises(pybreaker.CircuitBreakerError):
        await call_async_with_breaker(test_breaker, mock_fn)
    assert mock_fn.call_count == 0

@pytest.mark.anyio
async def test_execute_db_with_resilience_timeout():
    """Verify execute_db_with_resilience raises DBTimeoutError on query timeout."""
    def slow_query():
        import time
        time.sleep(0.2)  # Simulate slow query
        return "done"

    # Run with a very low timeout
    with pytest.raises(DBTimeoutError):
        await execute_db_with_resilience(slow_query, timeout=0.05)
