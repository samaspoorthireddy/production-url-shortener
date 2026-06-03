import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Default local database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/upsk_sdf"
)

# Create the SQLAlchemy engine with production-grade timeouts and connection checks
engine = create_engine(
    DATABASE_URL,
    connect_args={"connect_timeout": 5},
    pool_pre_ping=True,
    pool_recycle=300,
    # Bug #10 fix: explicit pool bounds prevent connection exhaustion.
    # API workers + Celery tasks share this pool; cap it so a retry storm
    # cannot silently drain all connections and hang the API indefinitely.
    pool_size=10,        # maintained open connections
    max_overflow=5,      # allowed burst above pool_size (total max: 15)
    pool_timeout=10,     # raise after 10s instead of hanging indefinitely
)


# Create a sessionmaker factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for models
Base = declarative_base()

# Dependency to get db session in FastAPI routes


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
