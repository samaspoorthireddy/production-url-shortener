"""
Integration tests for Module 17A: QR Code Generation.
"""
import pytest
import io
from PIL import Image

HEADERS_A = {"X-API-Key": "API_KEY_A"}
HEADERS_B = {"X-API-Key": "API_KEY_B"}
BASE_URL = "https://example.com"


class TestQrGeneration:
    """Tests GET /v1/links/{id}/qr endpoint."""

    def test_qr_generation_happy_path(self, client):
        """Standard request with no size returns 200 OK, image/png content type, and 300x300 image."""
        # 1. Create a link
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        assert res.status_code == 201
        link_id = res.json()["id"]

        # 2. Fetch the QR code
        qr_res = client.get(f"/v1/links/{link_id}/qr", headers=HEADERS_A)
        assert qr_res.status_code == 200
        assert qr_res.headers["content-type"] == "image/png"

        # 3. Read image using Pillow and check dimensions
        img = Image.open(io.BytesIO(qr_res.content))
        assert img.format == "PNG"
        assert img.size == (300, 300)

    def test_qr_generation_custom_size(self, client):
        """Custom size parameter returns a correctly sized image."""
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        qr_res = client.get(f"/v1/links/{link_id}/qr?size=550", headers=HEADERS_A)
        assert qr_res.status_code == 200
        assert qr_res.headers["content-type"] == "image/png"

        img = Image.open(io.BytesIO(qr_res.content))
        assert img.format == "PNG"
        assert img.size == (550, 550)

    def test_qr_generation_size_too_small(self, client):
        """Size below 100 must be rejected with 422."""
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        qr_res = client.get(f"/v1/links/{link_id}/qr?size=99", headers=HEADERS_A)
        assert qr_res.status_code == 422

    def test_qr_generation_size_too_large(self, client):
        """Size above 1000 must be rejected with 422."""
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        qr_res = client.get(f"/v1/links/{link_id}/qr?size=1001", headers=HEADERS_A)
        assert qr_res.status_code == 422

    def test_qr_generation_unowned_link(self, client):
        """Attempting to generate a QR code for a link owned by another user returns 404."""
        # User A creates a link
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        # User B tries to fetch the QR code
        qr_res = client.get(f"/v1/links/{link_id}/qr", headers=HEADERS_B)
        assert qr_res.status_code == 404

    def test_qr_generation_non_existent_link(self, client):
        """Requesting QR code for non-existent ID returns 404."""
        qr_res = client.get("/v1/links/999999/qr", headers=HEADERS_A)
        assert qr_res.status_code == 404

    def test_qr_generation_auth_required(self, client):
        """Endpoint must enforce authentication."""
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        qr_res = client.get(f"/v1/links/{link_id}/qr")
        assert qr_res.status_code == 401

    def test_qr_generation_independent_of_dest_change(self, client):
        """Updating the destination URL keeps the QR code working since the short code doesn't change."""
        # Create link
        res = client.post("/v1/links/", json={"long_url": BASE_URL}, headers=HEADERS_A)
        link_id = res.json()["id"]

        # Fetch QR code before update
        qr_res1 = client.get(f"/v1/links/{link_id}/qr", headers=HEADERS_A)
        assert qr_res1.status_code == 200

        # Update destination URL
        patch_res = client.patch(f"/v1/links/{link_id}", json={"long_url": "https://google.com"}, headers=HEADERS_A)
        assert patch_res.status_code == 200

        # Fetch QR code after update
        qr_res2 = client.get(f"/v1/links/{link_id}/qr", headers=HEADERS_A)
        assert qr_res2.status_code == 200

        # Compare image contents (they encode the same short link code so they should be identical)
        assert qr_res1.content == qr_res2.content
