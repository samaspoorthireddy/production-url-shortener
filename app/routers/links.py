from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from database import get_db
from models import Link, ClickEvent
from app.schemas.link import (
    LinkCreate,
    LinkResponse,
    LinkUpdate,
    BulkCreateRequest,
    BulkCreateResult,
    BulkDeleteRequest,
    BulkDeleteResult,
)
from app.services import links_service, cache_service
from app.services.links_service import compute_is_active
from app.services import analytics_service
from app.dependencies import get_current_user, rate_limit_post_links, rate_limit_search


def _parse_date_range(from_date: Optional[str], to_date: Optional[str]):
    """Parse YYYY-MM-DD strings into datetime objects. Raises 422 on bad format."""
    from_dt = None
    to_dt = None
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid 'from' date format. Use YYYY-MM-DD.",
            )
    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid 'to' date format. Use YYYY-MM-DD.",
            )
    return from_dt, to_dt


router = APIRouter(prefix="/links", tags=["Links"])


def _build_response(db_link: Link, db: Session, click_count: Optional[int] = None) -> LinkResponse:
    """Construct a V1 LinkResponse including lifecycle fields."""
    return LinkResponse(
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
        title=db_link.title,
        description=db_link.description,
        image_url=db_link.image_url,
    )


@router.post("/", response_model=LinkResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit_post_links)])
def create_new_link(
    link_in: LinkCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Creates a new short link slug and maps it to the long URL.
    Scoped to the current authenticated user.
    Returns 422 if the destination URL fails security validation.
    Returns 409 if a custom vanity code is already taken.
    """
    try:
        db_link = links_service.create_link(db, link_in, created_by=current_user)
    except ValueError as exc:
        msg = str(exc)
        if "code already taken" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return _build_response(db_link, db)


@router.get("/", response_model=list[LinkResponse])
def get_all_links(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Retrieves all links owned by the current authenticated user with paging.
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

    return [_build_response(row[0], db, click_count=row[1]) for row in results]


@router.get("/search", dependencies=[Depends(rate_limit_search)])
def search_links(
    q: Optional[str] = None,
    tag: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Safe and predictable link searching with keyword FTS, tag filtering,
    allowlisted sorting, and memory-capped pagination.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    elif page_size > 100:
        page_size = 100

    offset = (page - 1) * page_size
    query = db.query(Link).filter(Link.created_by == current_user)

    if q and q.strip():
        search_term = q.strip()
        from sqlalchemy import or_
        query = query.filter(
            or_(
                func.to_tsvector('english', Link.long_url).op('@@')(
                    func.plainto_tsquery('english', search_term)
                ),
                Link.long_url.ilike(f"%{search_term}%")
            )
        )

    if tag:
        query = query.filter(Link.tags.any(tag))

    total_records = query.count()

    click_count_subquery = db.query(
        ClickEvent.link_id,
        func.count(ClickEvent.id).label("count")
    ).group_by(ClickEvent.link_id).subquery()

    query_with_clicks = db.query(
        Link,
        func.coalesce(click_count_subquery.c.count, 0).label("click_count")
    ).outerjoin(
        click_count_subquery, Link.id == click_count_subquery.c.link_id
    ).filter(Link.created_by == current_user)

    if q and q.strip():
        search_term = q.strip()
        from sqlalchemy import or_
        query_with_clicks = query_with_clicks.filter(
            or_(
                func.to_tsvector('english', Link.long_url).op('@@')(
                    func.plainto_tsquery('english', search_term)
                ),
                Link.long_url.ilike(f"%{search_term}%")
            )
        )
    if tag:
        query_with_clicks = query_with_clicks.filter(Link.tags.any(tag))

    allowed_sort_fields = {"created_at", "click_count"}
    clean_sort_by = sort_by if sort_by in allowed_sort_fields else "created_at"

    from sqlalchemy import desc, asc
    order_func = desc if sort_order.lower() == "desc" else asc

    if clean_sort_by == "click_count":
        query_with_clicks = query_with_clicks.order_by(order_func("click_count"), desc(Link.id))
    else:
        query_with_clicks = query_with_clicks.order_by(order_func(Link.created_at), desc(Link.id))

    results = query_with_clicks.offset(offset).limit(page_size).all()
    total_pages = (total_records + page_size - 1) // page_size if total_records > 0 else 0

    response_items = []
    for db_link, click_count in results:
        response_items.append({
            "id": db_link.id,
            "code": db_link.code,
            "long_url": db_link.long_url,
            "short_url": f"http://localhost:8000/r/{db_link.code}",
            "created_at": db_link.created_at.isoformat(),
            "created_by": db_link.created_by,
            "tags": db_link.tags,
            "click_count": click_count,
            "expires_at": db_link.expires_at.isoformat() if db_link.expires_at else None,
            "max_clicks": db_link.max_clicks,
            "is_active": compute_is_active(db_link, db),
        })

    return {
        "results": response_items,
        "metadata": {
            "page": page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": total_pages
        }
    }


@router.get("/analytics/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Cross-link dashboard totals for the authenticated user:
    total links, total clicks, clicks today, and top 5 links by traffic.
    """
    return analytics_service.get_user_summary(db, created_by=current_user)


@router.post(
    "/bulk",
    status_code=status.HTTP_201_CREATED,
    response_model=BulkCreateResult,
    dependencies=[Depends(rate_limit_post_links)]
)
async def bulk_create_links(
    payload: BulkCreateRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Creates multiple short links in a single request.
    Allows partial successes: individual failures are collected and reported
    without rolling back successful creations.
    """
    created_links, failed_items = links_service.bulk_create_links(db, payload.items, created_by=current_user)

    total_requested = len(payload.items)
    total_created = len(created_links)
    total_failed = len(failed_items)

    created_responses = [_build_response(link, db) for link in created_links]

    result = BulkCreateResult(
        created=created_responses,
        failed=failed_items,
        total_requested=total_requested,
        total_created=total_created,
        total_failed=total_failed
    )

    if total_created == 0:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif total_failed > 0:
        response.status_code = 207  # Multi-Status

    return result


@router.delete("/bulk", response_model=BulkDeleteResult, status_code=status.HTTP_200_OK)
async def bulk_delete_links(
    payload: BulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Deletes multiple links in a single request.
    This is an all-or-nothing operation, but non-existent or non-owned links
    are silently ignored (skipped) rather than causing errors, to preserve idempotency.
    """
    deleted_ids, deleted_codes, skipped_ids = links_service.bulk_delete_links(db, payload.ids, current_user)

    for code in deleted_codes:
        await cache_service.invalidate_redirect(code)

    return BulkDeleteResult(
        deleted_count=len(deleted_ids),
        deleted_ids=deleted_ids,
        skipped_ids=skipped_ids
    )


@router.get("/{link_id}", response_model=LinkResponse)
def get_link(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Retrieves a single link details by its numeric ID.
    Enforces ownership check. Returns 404 for non-existent or unowned links.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return _build_response(db_link, db)


@router.get("/{link_id}/qr")
def get_link_qr(
    link_id: int,
    size: int = 300,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Generates a QR code image (PNG) for the short link.
    Enforces ownership check.
    """
    if not (100 <= size <= 1000):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="QR code size must be between 100 and 1000 pixels."
        )

    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    short_url = f"http://localhost:8000/r/{db_link.code}"
    img_bytes = links_service.generate_qr_code(short_url, size)

    return Response(content=img_bytes, media_type="image/png")


@router.patch("/{link_id}", response_model=LinkResponse)
async def update_link(
    link_id: int,
    link_update: LinkUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Updates the destination URL of an existing link.
    Enforces ownership check. Evicts the old destination from the cache.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    code = db_link.code
    try:
        updated_link = links_service.update_link(db, db_link, link_update.long_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    await cache_service.invalidate_redirect(code)
    return _build_response(updated_link, db)


@router.delete("/{link_id}", status_code=status.HTTP_200_OK)
async def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Deletes a link by its numeric ID. Enforces ownership check.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    code = db_link.code
    links_service.delete_link(db, db_link)
    await cache_service.invalidate_redirect(code)

    return {"detail": "Link deleted successfully"}


@router.get("/{link_id}/analytics")
def get_link_analytics(
    link_id: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Enriched analytics for a single link.
    Returns total_clicks, last_clicked, plus period counts:
    clicks_today, clicks_this_week, clicks_this_month.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    from_dt, to_dt = _parse_date_range(from_date, to_date)
    return analytics_service.get_link_summary(db, link_id, from_dt=from_dt, to_dt=to_dt)


@router.get("/{link_id}/analytics/timeseries")
def get_link_timeseries(
    link_id: int,
    granularity: str = "day",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Clicks grouped by day or hour over an optional date range.
    granularity: 'day' (default) | 'hour'
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    if granularity not in ("day", "hour"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="granularity must be 'day' or 'hour'",
        )
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    return analytics_service.get_timeseries(db, link_id, granularity=granularity, from_dt=from_dt, to_dt=to_dt)


@router.get("/{link_id}/analytics/referrers")
def get_link_referrers(
    link_id: int,
    top_n: int = 10,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Top-N referrer domains with click counts and percentage share.
    Null / empty referrers are bucketed as 'Direct'.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    if top_n < 1 or top_n > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="top_n must be between 1 and 100",
        )
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    return analytics_service.get_referrer_breakdown(db, link_id, from_dt=from_dt, to_dt=to_dt, top_n=top_n)


@router.get("/{link_id}/analytics/devices")
def get_link_devices(
    link_id: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Browser, OS, and device-type breakdown derived from User-Agent strings.
    """
    db_link = links_service.get_link_by_id(db, link_id)
    if not db_link or db_link.created_by != current_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    from_dt, to_dt = _parse_date_range(from_date, to_date)
    return analytics_service.get_device_breakdown(db, link_id, from_dt=from_dt, to_dt=to_dt)


@router.post("/analytics/purge")
def trigger_analytics_purge(
    retention_days: int = 30,
    current_user: str = Depends(get_current_user)
):
    """
    Triggers a background Celery task to purge click logs older than retention_days.
    """
    from app.tasks import purge_clicks_task
    try:
        purge_clicks_task.delay(retention_days=retention_days)
        return {
            "detail": "Retention purge job enqueued successfully.",
            "retention_days": retention_days
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue purge job: {str(e)}"
        )
