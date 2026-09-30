import os
import sys

# Configure default test environment variables BEFORE any application imports
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/upsk_sdf_test")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("PORT", "8000")
os.environ.setdefault("JWT_SECRET", "testsecretkey12345")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:3000")

# Add project root to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from database import Base, get_db

# Create engine and session factory specifically for tests
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Session-scoped fixture that waits for PostgreSQL, creates target database if missing,
    builds the schema once at the start, and cleans tables at the end.
    """
    db_url = os.environ["DATABASE_URL"]

    # Retry loop connecting to postgres default db to ensure server is ready and db exists
    for i in range(20):
        try:
            if "postgresql" in db_url:
                base_url = db_url.rsplit('/', 1)[0] + '/postgres'
                db_name = db_url.rsplit('/', 1)[1]
                temp_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
                with temp_engine.connect() as conn:
                    res = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'"))
                    if not res.scalar():
                        conn.execute(text(f"CREATE DATABASE {db_name}"))
                temp_engine.dispose()
            with engine.connect():
                break
        except Exception as e:
            if i == 19:
                print(f"Database setup failed after retries: {e}")
                raise
            time.sleep(1)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """
    Function-scoped fixture that opens a database connection, starts a transaction,
    and rolls it back at the end of each test. This guarantees 100% clean isolation
    without the overhead of dropping and recreating tables.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """
    Function-scoped fixture that overrides the FastAPI database dependency
    to return our transactional session, returning an HTTP test client.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    """
    Automatically clears the in-memory rate limiter requests log before each test
    runs to prevent 429 Too Many Requests from failing independent tests.
    """
    from app.dependencies import limiter
    with limiter.lock:
        limiter.requests.clear()
