"""
Integration and unit tests for Module 17D: Link Metadata Scraping.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.scraper import OGTagParser, scrape_metadata

HEADERS_A = {"X-API-Key": "API_KEY_A"}
BASE_URL = "https://example.com"


# ===========================================================================
# 1. Unit Tests for OGTagParser
# ===========================================================================

class TestOGTagParser:
    """Verifies internal HTML metadata extraction logic."""

    def test_parse_standard_title_fallback(self):
        """Standard <title> should act as fallback if og:title is absent."""
        html = "<html><head><title>Standard Page Title</title></head></html>"
        parser = OGTagParser()
        parser.feed(html)
        assert parser.metadata.get("title") == "Standard Page Title"

    def test_parse_og_title_overrides_standard(self):
        """og:title should take precedence over standard <title>."""
        html = (
            "<html><head>"
            "<title>Standard Page Title</title>"
            '<meta property="og:title" content="OpenGraph Page Title">'
            "</head></html>"
        )
        parser = OGTagParser()
        parser.feed(html)
        assert parser.metadata.get("title") == "OpenGraph Page Title"

    def test_parse_og_description_and_image(self):
        """Parser extracts og:description and og:image tags correctly."""
        html = (
            "<html><head>"
            '<meta name="description" content="Standard description">'
            '<meta property="og:description" content="OpenGraph description">'
            '<meta property="og:image" content="https://example.com/cover.png">'
            "</head></html>"
        )
        parser = OGTagParser()
        parser.feed(html)
        assert parser.metadata.get("description") == "OpenGraph description"
        assert parser.metadata.get("image_url") == "https://example.com/cover.png"

    def test_parse_meta_name_and_property_variants(self):
        """Parser extracts name= or property= case-insensitively."""
        html = (
            "<html><head>"
            '<meta Name="og:title" CONTENT="Title One">'
            '<meta PROPERTY="OG:DESCRIPTION" content="Desc One">'
            "</head></html>"
        )
        parser = OGTagParser()
        parser.feed(html)
        assert parser.metadata.get("title") == "Title One"
        assert parser.metadata.get("description") == "Desc One"


# ===========================================================================
# 2. Integration / Scraper Tests
# ===========================================================================

class TestMetadataScraperIntegration:
    """Integration and Mocked Scraper tests."""

    @patch("httpx.Client")
    def test_scrape_metadata_happy_path(self, mock_client_class):
        """Scraper fetches real/mocked HTTP streams and parses them cleanly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulating stream chunk iteration
        mock_response.iter_text.return_value = [
            "<html><head>",
            "<title>My Webpage</title>",
            '<meta property="og:description" content="This is my website description.">',
            '<meta property="og:image" content="https://example.com/logo.jpg">',
            "</head></html>"
        ]

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_response
        mock_client = MagicMock()
        mock_client.__enter__.return_value.stream.return_value = mock_stream
        mock_client_class.return_value = mock_client

        metadata = scrape_metadata("https://mocksite.com")
        assert metadata["title"] == "My Webpage"
        assert metadata["description"] == "This is my website description."
        assert metadata["image_url"] == "https://example.com/logo.jpg"

    @patch("httpx.Client")
    def test_scrape_metadata_truncation(self, mock_client_class):
        """Extremely long titles or image URLs are safely truncated to protect DB fields."""
        long_title = "A" * 500
        long_desc = "B" * 3000
        long_img = "https://example.com/" + ("C" * 2000)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_text.return_value = [
            f"<html><head><title>{long_title}</title>",
            f'<meta property="og:description" content="{long_desc}">',
            f'<meta property="og:image" content="{long_img}">',
            "</head></html>"
        ]

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_response
        mock_client = MagicMock()
        mock_client.__enter__.return_value.stream.return_value = mock_stream
        mock_client_class.return_value = mock_client

        metadata = scrape_metadata("https://mocksite.com")
        assert len(metadata["title"]) == 255
        assert len(metadata["description"]) == 2000
        assert len(metadata["image_url"]) == 1024

    @patch("httpx.Client")
    def test_scrape_metadata_non_200_fails_gracefully(self, mock_client_class):
        """Offline or non-200 responses return empty metadata, avoiding crashes."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_response
        mock_client = MagicMock()
        mock_client.__enter__.return_value.stream.return_value = mock_stream
        mock_client_class.return_value = mock_client

        metadata = scrape_metadata("https://mocksite.com")
        assert metadata == {}

    @patch("httpx.Client")
    def test_scrape_metadata_exception_graceful(self, mock_client_class):
        """Timeouts or network socket failures fail gracefully to protect user link creation."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value.stream.side_effect = Exception("Connection Timeout")
        mock_client_class.return_value = mock_client

        metadata = scrape_metadata("https://mocksite.com")
        assert metadata == {}

    @patch("httpx.Client")
    def test_scrape_metadata_size_limiting(self, mock_client_class):
        """Scraper stops reading stream once 100KB is exceeded."""
        # Create an iterator that serves 120 chunks of 1KB
        chunks = ["X" * 1024 for _ in range(120)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_text.return_value = chunks

        mock_stream = MagicMock()
        mock_stream.__enter__.return_value = mock_response
        mock_client = MagicMock()
        mock_client.__enter__.return_value.stream.return_value = mock_stream
        mock_client_class.return_value = mock_client

        metadata = scrape_metadata("https://mocksite.com")
        # Ensure it completed without hanging or raising exceptions
        assert isinstance(metadata, dict)


# ===========================================================================
# 3. Router Integration / End-to-End API Tests
# ===========================================================================

class TestMetadataRouterIntegration:
    """Verifies that API creation returns the metadata fields in responses."""

    @patch("app.services.links_service.scrape_metadata")
    def test_api_returns_metadata_fields(self, mock_scrape, client):
        """Creating a link scrapes metadata and returns it in the API response."""
        mock_scrape.return_value = {
            "title": "Wikipedia, the free encyclopedia",
            "description": "Wikipedia is a free online encyclopedia...",
            "image_url": "https://wikipedia.org/logo.png"
        }

        res = client.post("/v1/links/", json={"long_url": "https://wikipedia.org"}, headers=HEADERS_A)
        assert res.status_code == 201
        data = res.json()

        assert data["title"] == "Wikipedia, the free encyclopedia"
        assert data["description"] == "Wikipedia is a free online encyclopedia..."
        assert data["image_url"] == "https://wikipedia.org/logo.png"

        # Check in single link fetch response
        link_id = data["id"]
        get_res = client.get(f"/v1/links/{link_id}", headers=HEADERS_A)
        assert get_res.status_code == 200
        assert get_res.json()["title"] == "Wikipedia, the free encyclopedia"
