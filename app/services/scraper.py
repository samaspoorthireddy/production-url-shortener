from html.parser import HTMLParser
import httpx
import logging

logger = logging.getLogger("url_shortener")


class OGTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.in_title = False
        self.title_chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            attrs_dict = dict(attrs)
            prop = attrs_dict.get("property") or attrs_dict.get("name")
            content = attrs_dict.get("content")
            if prop and content:
                # Standardize property case/spaces
                prop = prop.strip().lower()
                content = content.strip()
                if prop == "og:title":
                    self.metadata["title"] = content
                elif prop in ("og:description", "description"):
                    # og:description overrides standard description if both present,
                    # or standard description acts as fallback.
                    if prop == "og:description" or "description" not in self.metadata:
                        self.metadata["description"] = content
                elif prop == "og:image":
                    self.metadata["image_url"] = content
        elif tag == "title":
            self.in_title = True

    def handle_data(self, data):
        if self.in_title:
            self.title_chunks.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
            if "title" not in self.metadata and self.title_chunks:
                full_title = "".join(self.title_chunks).strip()
                if full_title:
                    self.metadata["title"] = full_title


def scrape_metadata(url: str) -> dict:
    """
    Scrapes Open Graph (og:) tags and standard titles from a destination URL.

    Resource-friendly & secure:
      - Synchronous streaming of first 100KB only.
      - 3.0s timeout.
      - Truncation protection to avoid database character-overflow exceptions.
      - Graceful silent failure on non-200, offline, or timeout to avoid blocking link creation.
    """
    metadata = {}
    try:
        headers = {"User-Agent": "UpskMetadataScraper/1.0"}
        # Strict 3.0s timeout
        with httpx.Client(timeout=3.0, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 200:
                    html_content = []
                    bytes_read = 0
                    # Read up to 100KB
                    for chunk in response.iter_text(chunk_size=1024):
                        html_content.append(chunk)
                        bytes_read += len(chunk.encode("utf-8", errors="ignore"))
                        if bytes_read > 102400:  # 100KB cap
                            break

                    full_html = "".join(html_content)
                    parser = OGTagParser()
                    parser.feed(full_html)
                    metadata = parser.metadata
    except Exception as e:
        logger.warning(f"Metadata scraping failed for URL '{url}', degrading gracefully. Error: {str(e)}")

    # Truncate values to prevent database schema violations/exceptions
    if "title" in metadata and metadata["title"]:
        metadata["title"] = metadata["title"][:255]
    if "description" in metadata and metadata["description"]:
        metadata["description"] = metadata["description"][:2000]
    if "image_url" in metadata and metadata["image_url"]:
        metadata["image_url"] = metadata["image_url"][:1024]

    return metadata
