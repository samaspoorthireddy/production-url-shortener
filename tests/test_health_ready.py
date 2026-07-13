import pytest
from unittest.mock import patch
from fastapi import status

def test_live_endpoint_healthy(client):
    """
    Verify GET /live returns 200 and a simple, dependency-free schema.
    """
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_ready_endpoint_healthy(client):
    """
    Verify GET /ready returns 200 and details about dependency connectivity when everything is healthy.
    """
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["checks"]["database"] == "connected"
    assert data["checks"]["cache"] == "connected"
    assert isinstance(data["checks"]["uptime_seconds"], int)
    assert data["checks"]["uptime_seconds"] >= 0

def test_ready_endpoint_database_down(client):
    """
    Verify GET /ready returns 503 and reports database disconnected when database check fails.
    """
    # Mock database session execution to fail
    with patch("sqlalchemy.orm.Session.execute", side_effect=Exception("Connection refused")):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ok"] is False
        assert data["checks"]["database"] == "disconnected"
        assert data["checks"]["cache"] == "connected"
        assert isinstance(data["checks"]["uptime_seconds"], int)

def test_ready_endpoint_cache_down(client):
    """
    Verify GET /ready returns 503 and reports cache disconnected when redis ping fails.
    """
    # Mock redis ping to fail
    from app.services.cache_service import redis_client
    with patch.object(redis_client, "ping", side_effect=Exception("Redis timeout")):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ok"] is False
        assert data["checks"]["database"] == "connected"
        assert data["checks"]["cache"] == "disconnected"
        assert isinstance(data["checks"]["uptime_seconds"], int)
