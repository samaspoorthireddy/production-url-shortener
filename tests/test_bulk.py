"""
Integration tests for Module 17B: Bulk Operations.

Includes:
1. TestBulkCreate: Happy path, partial failure, all-fail, max-limit (101), empty list, vanity collision (DB and batch-internal), SSRF, auth, response shape.
2. TestBulkDelete: Happy path, skips non-owned IDs, skips non-existent IDs, empty result, auth, max-limit (101), empty list, cache eviction.
"""
import pytest
import asyncio
from datetime import datetime, timezone
from models import Link
from app.services import cache_service

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}
BASE_URL = "https://example.com"


# ---------------------------------------------------------------------------
# Test Bulk Create
# ---------------------------------------------------------------------------

class TestBulkCreate:
    """Tests POST /v1/links/bulk endpoint."""

    def test_bulk_create_happy_path(self, client):
        """Create 3 links successfully in one batch."""
        payload = {
            "items": [
                {"long_url": "https://google.com"},
                {"long_url": "https://github.com", "code": "my-gh-code"},
                {"long_url": "https://example.com", "tags": ["tech", "qa"]},
            ]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 201
        data = res.json()

        assert data["total_requested"] == 3
        assert data["total_created"] == 3
        assert data["total_failed"] == 0
        assert len(data["created"]) == 3
        assert len(data["failed"]) == 0

        # Assert correct order and details
        assert data["created"][0]["long_url"] == "https://google.com"
        assert len(data["created"][0]["code"]) >= 8

        assert data["created"][1]["long_url"] == "https://github.com"
        assert data["created"][1]["code"] == "my-gh-code"

        assert data["created"][2]["long_url"] == "https://example.com"
        assert "tech" in data["created"][2]["tags"]

    def test_bulk_create_partial_failure(self, client):
        """Create 3 links, where 1 is invalid (private IP block / SSRF). Should return 207."""
        payload = {
            "items": [
                {"long_url": "https://google.com"},
                {"long_url": "http://127.0.0.1/admin"},  # Blocked!
                {"long_url": "https://github.com"},
            ]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 207
        data = res.json()

        assert data["total_requested"] == 3
        assert data["total_created"] == 2
        assert data["total_failed"] == 1
        assert len(data["created"]) == 2
        assert len(data["failed"]) == 1

        # The failed item lists index 1
        assert data["failed"][0]["index"] == 1
        assert data["failed"][0]["long_url"] == "http://127.0.0.1/admin"
        assert "private" in data["failed"][0]["error"].lower()

        # The created list contains the successful 2
        assert data["created"][0]["long_url"] == "https://google.com"
        assert data["created"][1]["long_url"] == "https://github.com"

    def test_bulk_create_all_fail(self, client):
        """All items in the batch fail to create. Should return 422."""
        payload = {
            "items": [
                {"long_url": "http://127.0.0.1/admin"},
                {"long_url": "ftp://bad-scheme.com"},
                {"long_url": "https://google.com@evil.com"},
            ]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 422
        data = res.json()

        assert data["total_requested"] == 3
        assert data["total_created"] == 0
        assert data["total_failed"] == 3
        assert len(data["created"]) == 0
        assert len(data["failed"]) == 3

    def test_bulk_create_max_limit_exceeded(self, client):
        """Creating more than 100 links must be rejected with 422."""
        payload = {
            "items": [{"long_url": "https://google.com"} for _ in range(101)]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

    def test_bulk_create_empty_batch(self, client):
        """An empty batch must be rejected with 422."""
        payload = {"items": []}
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

    def test_bulk_create_vanity_collision_existing(self, client):
        """Requesting a code already in DB should fail that item and create others."""
        # Pre-create a link with code 'brand-slug'
        pre_res = client.post("/v1/links/", json={"long_url": "https://google.com", "code": "brand-slug"}, headers=HEADERS_A)
        assert pre_res.status_code == 201

        payload = {
            "items": [
                {"long_url": "https://github.com"},
                {"long_url": "https://google.com", "code": "brand-slug"},  # Collides!
                {"long_url": "https://example.com"},
            ]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 207
        data = res.json()

        assert data["total_requested"] == 3
        assert data["total_created"] == 2
        assert data["total_failed"] == 1
        assert len(data["created"]) == 2
        assert len(data["failed"]) == 1

        assert data["failed"][0]["index"] == 1
        assert "taken" in data["failed"][0]["error"].lower()

    def test_bulk_create_vanity_collision_in_batch(self, client):
        """Two items in the same batch request the same custom code. First succeeds, second fails."""
        payload = {
            "items": [
                {"long_url": "https://github.com", "code": "batch-duplicate"},
                {"long_url": "https://google.com", "code": "batch-duplicate"},  # Collides internally!
                {"long_url": "https://example.com"},
            ]
        }
        res = client.post("/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 207
        data = res.json()

        assert data["total_requested"] == 3
        assert data["total_created"] == 2
        assert data["total_failed"] == 1

        assert data["created"][0]["code"] == "batch-duplicate"
        assert data["failed"][0]["index"] == 1
        assert "taken" in data["failed"][0]["error"].lower()

    def test_bulk_create_auth_required(self, client):
        """POST /v1/links/bulk requires authentication."""
        payload = {"items": [{"long_url": "https://google.com"}]}
        res = client.post("/v1/links/bulk", json=payload)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Test Bulk Delete
# ---------------------------------------------------------------------------

class TestBulkDelete:
    """Tests DELETE /v1/links/bulk endpoint."""

    def test_bulk_delete_happy_path(self, client):
        """Delete 3 links successfully."""
        # Create 3 links
        ids = []
        for url in ["https://google.com", "https://github.com", "https://example.com"]:
            res = client.post("/v1/links/", json={"long_url": url}, headers=HEADERS_A)
            ids.append(res.json()["id"])

        # Delete all 3
        payload = {"ids": ids}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 200
        data = res.json()

        assert data["deleted_count"] == 3
        assert sorted(data["deleted_ids"]) == sorted(ids)
        assert len(data["skipped_ids"]) == 0

        # Verify they are actually deleted from database (404)
        for link_id in ids:
            assert client.get(f"/v1/links/{link_id}", headers=HEADERS_A).status_code == 404

    def test_bulk_delete_skips_non_owned_ids(self, client):
        """Deleting a mix of owned and unowned (other user's) IDs deletes owned ones and skips unowned."""
        # User A creates a link
        res_a = client.post("/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_A)
        id_a = res_a.json()["id"]

        # User B creates a link
        res_b = client.post("/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_B)
        id_b = res_b.json()["id"]

        # User A tries to delete both
        payload = {"ids": [id_a, id_b]}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 200
        data = res.json()

        assert data["deleted_count"] == 1
        assert data["deleted_ids"] == [id_a]
        assert data["skipped_ids"] == [id_b]

        # Verify owned link is deleted, unowned is NOT deleted
        assert client.get(f"/v1/links/{id_a}", headers=HEADERS_A).status_code == 404
        assert client.get(f"/v1/links/{id_b}", headers=HEADERS_B).status_code == 200

    def test_bulk_delete_skips_non_existent_ids(self, client):
        """Deleting non-existent IDs lists them in skipped_ids."""
        res_a = client.post("/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_A)
        id_a = res_a.json()["id"]

        payload = {"ids": [id_a, 99999, 88888]}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 200
        data = res.json()

        assert data["deleted_count"] == 1
        assert data["deleted_ids"] == [id_a]
        assert sorted(data["skipped_ids"]) == [88888, 99999]

    def test_bulk_delete_empty_result(self, client):
        """If all requested IDs are non-owned/non-existent, deleted_count is 0."""
        payload = {"ids": [99999, 88888]}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 200
        data = res.json()

        assert data["deleted_count"] == 0
        assert len(data["deleted_ids"]) == 0
        assert sorted(data["skipped_ids"]) == [88888, 99999]

    def test_bulk_delete_max_limit_exceeded(self, client):
        """Bulk deleting more than 100 IDs is rejected with 422."""
        payload = {"ids": list(range(1, 102))}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

    def test_bulk_delete_empty_ids(self, client):
        """Bulk deleting an empty list is rejected with 422."""
        payload = {"ids": []}
        res = client.request("DELETE", "/v1/links/bulk", json=payload, headers=HEADERS_A)
        assert res.status_code == 422

    def test_bulk_delete_auth_required(self, client):
        """DELETE /v1/links/bulk requires authentication."""
        payload = {"ids": [1, 2, 3]}
        res = client.request("DELETE", "/v1/links/bulk", json=payload)
        assert res.status_code == 401

    def test_bulk_delete_cache_eviction(self, client):
        """Deleting a link in bulk evicts it from the cache, so future redirects get 404."""
        # Create a link
        res = client.post("/v1/links/", json={"long_url": "https://example.com"}, headers=HEADERS_A)
        assert res.status_code == 201
        data = res.json()
        code = data["code"]
        link_id = data["id"]

        # 2. Redirect once to populate the cache
        redir = client.get(f"/r/{code}", follow_redirects=False)
        assert redir.status_code == 302
        assert redir.headers["location"] == "https://example.com"

        # 3. Bulk delete the link
        del_res = client.request("DELETE", "/v1/links/bulk", json={"ids": [link_id]}, headers=HEADERS_A)
        assert del_res.status_code == 200

        # 4. Redirect again — must return 404 since cache is evicted and link is deleted
        redir_after = client.get(f"/r/{code}", follow_redirects=False)
        assert redir_after.status_code == 404
