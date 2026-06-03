from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, field_validator, ConfigDict
import re


class LinkCreate(BaseModel):
    long_url: str
    code: Optional[str] = None          # Vanity / custom short code
    expires_at: Optional[datetime] = None
    max_clicks: Optional[int] = None    # Click cap; None = unlimited
    tags: Optional[List[str]] = None

    @field_validator("long_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        url = v.strip()

        # Fast-fail: cap URL length at 2048 characters to prevent abuse and
        # avoid expensive downstream operations (DNS, scraping) on huge inputs.
        if len(url) > 2048:
            raise ValueError("URL must be 2048 characters or fewer")

        # Fast-fail: reject URLs with 100+ identical consecutive characters.
        # A legitimate URL never needs a 100-char run of the same character;
        # this pattern is the hallmark of a ReDoS / stress-test payload.
        if re.search(r"(.)\1{99,}", url):
            raise ValueError("URL contains a suspicious repeating character sequence")

        # Reject hidden control characters (newlines, null bytes, tabs)
        if re.search(r"[\x00-\x1F\x7F]", url):
            raise ValueError("URL contains illegal control characters")

        # Reject backslashes to prevent browser normalisation bypasses
        if "\\" in url:
            raise ValueError("URL contains illegal backslash characters")

        # Restrict schemes strictly to http and https
        if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
            raise ValueError("URL must start with http:// or https://")

        # Strict structural parsing
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
                raise ValueError("URL scheme must be http or https")
            if not parsed.netloc:
                raise ValueError("URL must have a valid host")
            # Reject userinfo authority bypass (e.g. https://good.com@evil.com)
            if "@" in parsed.netloc or parsed.username or parsed.password:
                raise ValueError("URL contains unsafe user information authority")
        except ValueError as ve:
            raise ve
        except Exception as e:
            raise ValueError(f"Invalid URL structure: {str(e)}")

        return url

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Custom code must be at least 3 characters")
        if len(v) > 30:
            raise ValueError("Custom code must be 30 characters or fewer")
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError(
                "Custom code may only contain letters, digits, hyphens, and underscores"
            )
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            if v <= datetime.now(timezone.utc):
                raise ValueError("Expiration date must be in the future")
        return v

    @field_validator("max_clicks")
    @classmethod
    def validate_max_clicks(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("max_clicks must be at least 1")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            if len(v) > 10:
                raise ValueError("Cannot have more than 10 tags")
            for tag in v:
                if len(tag) > 30:
                    raise ValueError("Each tag must be 30 characters or less")
        return v


class LinkResponse(BaseModel):
    id: int
    code: str
    long_url: str
    short_url: str
    created_at: datetime
    created_by: Optional[str] = None
    tags: Optional[List[str]] = []
    expires_at: Optional[datetime] = None
    max_clicks: Optional[int] = None
    is_active: bool = True   # False when expired or over click cap
    title: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LinkResponseV2(LinkResponse):
    """
    V2 response — backwards-compatible superset of V1.

    Adds click_count so clients can see engagement without a
    separate analytics call. V2 MUST be a strict superset: every
    V1 field exists identically here, so a V1 client that ignores
    unknown fields will work transparently against the V2 endpoint.
    """
    click_count: int = 0


class LinkUpdate(BaseModel):
    long_url: str

    @field_validator("long_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return LinkCreate.validate_url(v)


class BulkCreateError(BaseModel):
    index: int
    long_url: str
    error: str


class BulkCreateRequest(BaseModel):
    items: List[dict]

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[dict]) -> List[dict]:
        if not (1 <= len(v) <= 100):
            raise ValueError("Batch size must be between 1 and 100 items")
        return v


class BulkCreateResult(BaseModel):
    created: List[LinkResponse]
    failed: List[BulkCreateError]
    total_requested: int
    total_created: int
    total_failed: int


class BulkDeleteRequest(BaseModel):
    ids: List[int]

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, v: List[int]) -> List[int]:
        if not (1 <= len(v) <= 100):
            raise ValueError("Batch size must be between 1 and 100 IDs")
        return v


class BulkDeleteResult(BaseModel):
    deleted_count: int
    deleted_ids: List[int]
    skipped_ids: List[int]
