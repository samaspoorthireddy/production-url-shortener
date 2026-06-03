from pydantic import BaseModel, field_validator
from datetime import datetime
import re
from urllib.parse import urlparse


class WebhookCreate(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        url = v.strip()
        # Reject hidden control characters (newlines, null bytes, tabs)
        if re.search(r"[\x00-\x1F\x7F]", url):
            raise ValueError("URL contains illegal control characters")
        # Reject backslashes to prevent browser normalisation bypasses
        if "\\" in url:
            raise ValueError("URL contains illegal backslash characters")
        # Restrict schemes strictly to http and https
        if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        try:
            parsed = urlparse(url)
            if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
                raise ValueError("URL scheme must be http or https")
            if not parsed.netloc:
                raise ValueError("URL must have a valid host")
            # Reject userinfo authority bypass
            if "@" in parsed.netloc or parsed.username or parsed.password:
                raise ValueError("URL contains unsafe user information authority")
        except ValueError as ve:
            raise ve
        except Exception as e:
            raise ValueError(f"Invalid URL structure: {str(e)}")
        return url


class WebhookResponse(BaseModel):
    id: int
    url: str
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True
