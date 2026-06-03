import secrets
import string
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from models import Link, ClickEvent
from app.schemas.link import LinkCreate
from app.services.url_validator import validate_destination_url
from app.services.scraper import scrape_metadata


def compute_is_active(db_link: Link, db: Session, click_count: Optional[int] = None) -> bool:
    """
    Returns False if the link has expired or reached its click cap.
    Used by both V1 and V2 routers to populate the is_active field.
    """
    now = datetime.now(timezone.utc)
    if db_link.expires_at:
        exp = db_link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            return False
    if db_link.max_clicks is not None:
        if click_count is None:
            click_count = (
                db.query(func.count(ClickEvent.id))
                .filter(ClickEvent.link_id == db_link.id)
                .scalar()
            ) or 0
        if click_count >= db_link.max_clicks:
            return False
    return True


def generate_short_code(db: Session, length: int = 8) -> str:
    """
    Generates a cryptographically secure random alphanumeric short code
    and verifies that it does not already exist in the database to prevent collisions.
    """
    characters = string.ascii_letters + string.digits
    for _ in range(10):  # Retry up to 10 times in case of extreme collision scenarios
        code = "".join(secrets.choice(characters) for _ in range(length))
        exists = db.query(Link).filter(Link.code == code).first()
        if not exists:
            return code
    raise RuntimeError("System failed to generate a unique short code after 10 attempts")


def create_link(db: Session, link_in: LinkCreate, created_by: Optional[str] = None, commit: bool = True) -> Link:
    """
    Creates a new short link in the database.

    Raises ValueError (surfaced as HTTP 422 by the router) if the destination
    URL fails security validation (blocked scheme, private IP, SSRF, etc.).

    Raises ValueError("code already taken") if a custom vanity code is requested
    but already exists — surfaced as HTTP 409 by the router.
    """
    # Security: validate before any DB write
    safe_url = validate_destination_url(link_in.long_url)

    # Vanity code: use supplied code or generate a random one
    if link_in.code:
        exists = db.query(Link).filter(Link.code == link_in.code).first()
        if exists:
            raise ValueError("code already taken")
        code = link_in.code
    else:
        code = generate_short_code(db)

    # Scrape target URL metadata dynamically
    metadata = scrape_metadata(safe_url)

    db_link = Link(
        code=code,
        long_url=safe_url,
        created_by=created_by,
        tags=link_in.tags or [],
        expires_at=link_in.expires_at,
        max_clicks=link_in.max_clicks,
        title=metadata.get("title"),
        description=metadata.get("description"),
        image_url=metadata.get("image_url"),
    )
    db.add(db_link)
    if commit:
        db.commit()
        db.refresh(db_link)
    else:
        db.flush()
        db.refresh(db_link)
    return db_link


def bulk_create_links(db: Session, items: list[dict], created_by: Optional[str] = None) -> tuple[list[Link], list[dict]]:
    from pydantic import ValidationError
    created = []
    failed = []

    try:
        for index, item in enumerate(items):
            try:
                try:
                    link_in = LinkCreate(**item)
                except ValidationError as ve:
                    err_msgs = []
                    for err in ve.errors():
                        loc = " -> ".join(str(x) for x in err.get("loc", []))
                        msg = err.get("msg", "invalid value")
                        err_msgs.append(f"{loc}: {msg}")
                    raise ValueError("; ".join(err_msgs))
                except Exception as ex:
                    raise ValueError(str(ex))

                db_link = create_link(db, link_in, created_by=created_by, commit=False)
                created.append(db_link)
            except ValueError as ve:
                failed.append({
                    "index": index,
                    "long_url": item.get("long_url", ""),
                    "error": str(ve)
                })
            except Exception as e:
                db.rollback()
                raise e
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

    return created, failed


def bulk_delete_links(db: Session, ids: list[int], created_by: str) -> tuple[list[int], list[str], list[int]]:
    db_links = db.query(Link).filter(Link.id.in_(ids), Link.created_by == created_by).all()
    deleted_ids = [link.id for link in db_links]
    deleted_codes = [link.code for link in db_links]
    skipped_ids = [link_id for link_id in ids if link_id not in deleted_ids]

    if db_links:
        db.query(Link).filter(Link.id.in_(deleted_ids)).delete(synchronize_session=False)
        db.commit()

    return deleted_ids, deleted_codes, skipped_ids


def get_link_by_code(db: Session, code: str) -> Optional[Link]:
    """
    Queries and returns a link by its short code.
    """
    return db.query(Link).filter(Link.code == code).first()


def get_link_by_id(db: Session, link_id: int) -> Optional[Link]:
    """
    Queries and returns a link by its primary key ID.
    """
    return db.query(Link).filter(Link.id == link_id).first()


def list_links(db: Session, created_by: str, skip: int = 0, limit: int = 20) -> list[Link]:
    """
    Lists links created by a specific user with pagination support.
    """
    return db.query(Link).filter(Link.created_by == created_by).order_by(Link.id.desc()).offset(skip).limit(limit).all()


def delete_link(db: Session, db_link: Link) -> None:
    """
    Deletes a link from the database.
    """
    db.delete(db_link)
    db.commit()


def update_link(db: Session, db_link: Link, long_url: str) -> Link:
    """
    Updates the destination URL of a short link.

    Raises ValueError if the new URL fails security validation.
    """
    # Security: re-validate on every update — an old safe URL being replaced
    # with a malicious one must not slip through.
    safe_url = validate_destination_url(long_url)
    db_link.long_url = safe_url
    db.commit()
    db.refresh(db_link)
    return db_link


def log_click_event(db: Session, link_id: int, user_agent: Optional[str] = None, referrer: Optional[str] = None, ip_hash: Optional[str] = None) -> ClickEvent:
    """
    Logs a click event for redirects.
    """
    db_click = ClickEvent(
        link_id=link_id,
        user_agent=user_agent,
        referrer=referrer,
        ip_hash=ip_hash
    )
    db.add(db_click)
    db.commit()
    db.refresh(db_click)
    return db_click


def generate_qr_code(short_url: str, size: int) -> bytes:
    """
    Generates a QR code image encoding the given short URL,
    resized to the requested dimensions (size x size), in PNG format.
    """
    import qrcode
    import io
    from PIL import Image

    # 1. Create QR code instance
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(short_url)
    qr.make(fit=True)

    # 2. Render as image
    img = qr.make_image(fill_color="black", back_color="white")

    # 3. Resize using high-quality filter
    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.LANCZOS

    resized_img = img.resize((size, size), resample=resample_filter)

    # 4. Save to buffer
    buf = io.BytesIO()
    resized_img.save(buf, format="PNG")
    return buf.getvalue()
