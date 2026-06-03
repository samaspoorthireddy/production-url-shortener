"""
app/routers/links_v2.py — V2 Links API

Changes from V1:
  - Response includes click_count (total redirect events) inline
  - Lifecycle fields (expires_at, max_clicks, is_active) also included
  - Deprecation-Warning header added on all V1 endpoints (mounted in main.py)

Design contract:
  - All V1 fields are present and unchanged — strict superset rule
  - V2 only ADDS fields, never removes or renames them
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models import Link, ClickEvent
from app.schemas.link import LinkCreate, LinkResponseV2
from app.services import links_service
from app.services.links_service import compute_is_active
from app.dependencies import get_current_user, rate_limit_post_links

router = APIRouter(prefix="/links", tags=["Links V2"])


def _build_v2_response(db_link: Link, db: Session, click_count: Optional[int] = None) -> LinkResponseV2:
    """
    Constructs a V2 response. If click_count is not provided, fetches it
    individually (safe fallback for single resource lookups).
    """
    if click_count is None:
        click_count = (
            db.query(func.count(ClickEvent.id))
            .filter(ClickEvent.link_id == db_link.id)
            .scalar()
        ) or 0

    return LinkResponseV2(
        id=db_link.id,
        code=db_link.code,
        long_url=db_link.long_url,
        short_url=f"http://localhost:8000/r/{db_link.code}",
        created_at=db_link.created_at,
        created_by=db_link.created_by,
        tags=db_link.tags or [],
        expires_at=db_link.expires_at,
        max_clicks=db_link.max_clicks,
        is_active=compute_is_active(db_link, db, click_count=click_count),
        click_count=click_count,
        title=db_link.title,
        description=db_link.description,
        image_url=db_link.image_url,
    )


@router.post(
    "/",
    response_model=LinkResponseV2,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_post_links)],
)
def create_new_link_v2(
    link_in: LinkCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    [V2] Creates a new short link.
    Returns all V1 fields plus click_count and lifecycle fields.
    Returns 409 if a custom vanity code is already taken.
    """
    try:
        db_link = links_service.create_link(db, link_in, created_by=current_user)
    except ValueError as exc:
        msg = str(exc)
        if "code already taken" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return _build_v2_response(db_link, db)


@router.get("/{link_id}", response_model=LinkResponseV2)
def get_link_v2(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    [V2] Retrieves a single link by ID with current click_count and lifecycle state.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Link not found"
        )
    return _build_v2_response(db_link, db)


@router.get("/", response_model=list[LinkResponseV2])
def list_links_v2(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    [V2] Lists all links owned by the current user, each with click_count and lifecycle state.
    """
    # Pre-aggregate click count using an outer join to completely avoid N+1 query loops
    click_count_subquery = (
        db.query(ClickEvent.link_id, func.count(ClickEvent.id).label("count"))
        .group_by(ClickEvent.link_id)
        .subquery()
    )

    results = (
        db.query(Link, func.coalesce(click_count_subquery.c.count, 0).label("click_count"))
        .outerjoin(click_count_subquery, Link.id == click_count_subquery.c.link_id)
        .filter(Link.created_by == current_user)
        .order_by(Link.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [_build_v2_response(row[0], db, click_count=row[1]) for row in results]
