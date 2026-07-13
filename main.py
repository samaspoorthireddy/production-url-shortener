import os
import json
import contextvars
import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.config import settings, Environment
from database import Base, engine
from app.routers import links, redirect, webhooks, teams, activity, comments, notifications
from sqlalchemy.exc import TimeoutError as DBTimeoutError, OperationalError as DBOperationalError
from app.routers import links_v2
from app.metrics import record_request, get_metrics_output

start_time = time.time()

# ContextVar to store request ID across the async request lifecycle
request_id_var = contextvars.ContextVar("request_id", default="N/A")


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "N/A"),
            "message": record.getMessage()
        }
        
        # Include custom extra fields passed to logger (like environment, port, etc.)
        standard_fields = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName", "request_id"
        }
        for key, value in record.__dict__.items():
            if key not in standard_fields:
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


# Setup structured console logging (JSON formatted)
log_level_env = settings.log_level.upper()
log_level = getattr(logging, log_level_env, logging.INFO)

logging.basicConfig(level=log_level)
# Clear default handlers to avoid duplicate output streams
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

console_handler = logging.StreamHandler()
formatter = JSONFormatter()
console_handler.setFormatter(formatter)
console_handler.addFilter(RequestIDFilter())
root_logger.addHandler(console_handler)
root_logger.setLevel(log_level)

logger = logging.getLogger("url_shortener")

# Automatically generate database tables if they do not exist
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.error(f"Database table generation failed on startup: {str(e)}")

# Resilient dynamic alters for Module 17D and 17C
try:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE links ADD COLUMN IF NOT EXISTS title VARCHAR(255);"))
        conn.execute(text("ALTER TABLE links ADD COLUMN IF NOT EXISTS description TEXT;"))
        conn.execute(text("ALTER TABLE links ADD COLUMN IF NOT EXISTS image_url VARCHAR(1024);"))
        conn.execute(text("ALTER TABLE links ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE;"))
        conn.execute(text("ALTER TABLE links ADD COLUMN IF NOT EXISTS max_clicks INTEGER;"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                id SERIAL PRIMARY KEY,
                url VARCHAR(1024) NOT NULL,
                created_by VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))
except Exception as e:
    logger.warning(f"Resilient migrations failed or columns exist: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: log startup sequence with environment details
    logger.info(
        "Service starting",
        extra={
            "environment": settings.app_env.value,
            "port": settings.port,
            "log_level": settings.log_level,
        },
    )
    yield
    # Shutdown: graceful drainage of Redis client and SQLAlchemy engine connections
    logger.info("Application shutting down. Draining active connections...")

    # Close Redis asyncio client
    try:
        from app.services.cache_service import redis_client
        await redis_client.aclose()
        logger.info("Redis cache client closed successfully.")
    except Exception as e:
        logger.error(f"Error closing Redis client during graceful shutdown: {str(e)}")

    # Dispose of database engine pools
    try:
        engine.dispose()
        logger.info("SQLAlchemy database connection pool disposed successfully.")
    except Exception as e:
        logger.error(f"Error disposing database connection pool: {str(e)}")

    logger.info("Graceful shutdown completed successfully.")


app = FastAPI(
    title="Upsk URL Shortener",
    description="A high-performance system design URL shortener built with FastAPI and PostgreSQL.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Error Envelope JSON response helper


def build_error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id
            }
        }
    )

# Request ID Generation, Latency Timing, and Secret Masking Middleware


@app.middleware("http")
async def log_and_time_requests(request: Request, call_next):
    # Generate unique request ID
    req_id = str(uuid.uuid4())
    request_id_var.set(req_id)

    # Store request_id in request state for exception handlers
    request.state.request_id = req_id

    start_time = time.perf_counter()

    # Redact credentials/secrets from logged headers
    safe_headers = {}
    for k, v in request.headers.items():
        if k.lower() in ("x-api-key", "authorization", "cookie", "set-cookie"):
            safe_headers[k] = "[REDACTED]"
        else:
            safe_headers[k] = v

    # Log incoming request details safely
    logger.info(f"Incoming request: {request.method} {request.url.path} headers={safe_headers}")

    try:
        response = await call_next(request)
        duration_s = time.perf_counter() - start_time
        latency_ms = int(duration_s * 1000)

        # Record Prometheus RED metrics for every request
        record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration_s,
        )

        # Log response status and latency
        logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"status_code={response.status_code} latency_ms={latency_ms}"
        )

        # Inject Request ID header to client response
        response.headers["X-Request-ID"] = req_id
        return response
    except Exception as e:
        duration_s = time.perf_counter() - start_time
        latency_ms = int(duration_s * 1000)
        logger.error(
            f"Request failed: {request.method} {request.url.path} "
            f"latency_ms={latency_ms} error={str(e)}"
        )
        record_request(
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_seconds=duration_s,
        )
        raise e

# Global Exception Handlers mapping to clean Error envelopes


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", "N/A")
    # Simplify validation error details to a friendly string
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "invalid value")
        errors.append(f"{loc}: {msg}")
    friendly_msg = "; ".join(errors) if errors else "Validation failed"

    logger.warning(f"Validation error: {friendly_msg}")

    return build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message=friendly_msg,
        request_id=req_id
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", "N/A")
    logger.warning(f"HTTP exception: status_code={exc.status_code} detail={exc.detail}")

    # Map status codes to stable error string codes
    if exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 429:
        code = "TOO_MANY_REQUESTS"
    else:
        code = "HTTP_ERROR"

    # Forward any extra headers set on the exception (e.g. Retry-After from rate limiter)
    extra_headers = dict(exc.headers) if exc.headers else {}

    response = build_error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        request_id=req_id
    )
    for header_name, header_value in extra_headers.items():
        response.headers[header_name] = header_value
    return response


@app.exception_handler(DBTimeoutError)
async def database_timeout_exception_handler(request: Request, exc: DBTimeoutError):
    req_id = getattr(request.state, "request_id", "N/A")
    logger.error(f"Database connection pool exhausted or query timed out (checkout timeout): {str(exc)}")
    return build_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="SERVICE_UNAVAILABLE",
        message="Database connection pool exhausted or query timed out. Please retry shortly.",
        request_id=req_id
    )


@app.exception_handler(DBOperationalError)
async def database_operational_exception_handler(request: Request, exc: DBOperationalError):
    req_id = getattr(request.state, "request_id", "N/A")
    logger.error(f"Database connectivity failure: {str(exc)}")
    return build_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="SERVICE_UNAVAILABLE",
        message="Database service is temporarily unavailable. Please retry shortly.",
        request_id=req_id
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "N/A")
    # Log the complete traceback inside the server log where it belongs
    logger.exception(f"Unhandled server error: {str(exc)}")

    # Return environment-aware 500 error envelope to the client
    show_details = settings.app_env in (
        Environment.development,
        Environment.staging,
    )
    message = "An unexpected error occurred. Please contact support and reference the Request ID."
    if show_details:
        message = f"Internal Server Error: {str(exc)}"

    return build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message=message,
        request_id=req_id
    )

# ---------------------------------------------------------------------------
# API versioning — mount routers under explicit version prefixes.
#
# /v1/links/   — current stable API (all existing routes, no changes)
# /v2/links/   — enhanced API (superset: adds click_count to responses)
# /r/{code}    — redirect endpoint has no version (it's a public UX surface)
# ---------------------------------------------------------------------------
app.include_router(links.router, prefix="/v1")
app.include_router(webhooks.router, prefix="/v1")
app.include_router(links_v2.router, prefix="/v2")
app.include_router(teams.router)
app.include_router(activity.router)
app.include_router(comments.router)
app.include_router(notifications.router)
app.include_router(redirect.router)


@app.middleware("http")
async def deprecation_header_middleware(request: Request, call_next):
    """
    Injects standard HTTP deprecation headers on every /v1/ response.

    Deprecation  — RFC 8594 header signalling the API version is deprecated.
    Sunset       — Date after which v1 will be decommissioned (6 months notice).
    Link         — Points clients to the migration guide.

    Clients that parse these headers (e.g. Retrofit, axios-retry plugins)
    can surface warnings to their developers automatically.
    """
    response = await call_next(request)
    if request.url.path.startswith("/v1/"):
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Sat, 01 Jan 2027 00:00:00 GMT"
        response.headers["Link"] = '</v2/links/>; rel="successor-version"'
    return response


@app.get("/trigger-500", tags=["System"])
def trigger_500():
    """
    Simulates a critical database failure or unhandled exception.
    """
    raise RuntimeError("Simulated database connection failure")


@app.get("/health", tags=["System"])
def health_check():
    """
    Liveness check endpoint. Fast and always returns 200 if process is up.
    """
    return {"status": "healthy"}


@app.get("/live", tags=["System"])
async def live_check():
    """
    Fast and lightweight liveness check.
    """
    return {"ok": True}


@app.get("/ready", tags=["System"])
async def readiness_check():
    """
    Readiness check endpoint that verifies connectivity to PostgreSQL and Redis.
    """
    from sqlalchemy import text
    from database import SessionLocal
    from app.services.cache_service import redis_client

    checks = {}
    ready = True

    # 1. Check PostgreSQL Database Connectivity
    try:
        db = SessionLocal()
        try:
            # Set statement timeout for this session to 2 seconds to fail fast
            db.execute(text("SET statement_timeout = 2000"))
            db.execute(text("SELECT 1"))
            checks["database"] = "connected"
        except Exception as query_exc:
            logger.error(f"Readiness check database query failure: {query_exc}")
            checks["database"] = "disconnected"
            ready = False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Readiness check database session failure: {e}")
        checks["database"] = "disconnected"
        ready = False

    # 2. Check Redis Cache Connectivity
    try:
        # Ping Redis with a fast liveness check and 2s timeout
        import asyncio
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        checks["cache"] = "connected"
    except Exception as e:
        logger.error(f"Readiness check redis failure: {e}")
        checks["cache"] = "disconnected"
        ready = False

    # 3. Include Uptime
    checks["uptime_seconds"] = int(time.time() - start_time)

    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={"ok": ready, "checks": checks}
    )


@app.get("/metrics", tags=["System"], include_in_schema=False)
def prometheus_metrics():
    """
    Prometheus scrape endpoint — returns all RED metrics in Prometheus text format.
    Excluded from OpenAPI docs (include_in_schema=False) to avoid cluttering the
    Swagger UI; Prometheus discovers it via static scrape config.
    """
    from fastapi.responses import Response
    body, content_type = get_metrics_output()
    return Response(content=body, media_type=content_type)
