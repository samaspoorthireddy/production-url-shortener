"""
app/services/analytics_service.py — Pure query functions for advanced analytics.

All functions are stateless and side-effect-free. They accept a SQLAlchemy
Session and return plain Python dicts ready for JSON serialisation.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ClickEvent, Link


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _apply_date_filters(query, from_dt: Optional[datetime], to_dt: Optional[datetime]):
    """Attach optional date-range filters to a ClickEvent query."""
    if from_dt:
        query = query.filter(ClickEvent.clicked_at >= from_dt)
    if to_dt:
        query = query.filter(ClickEvent.clicked_at <= to_dt)
    return query


def _extract_domain(referrer: Optional[str]) -> str:
    """
    Extract the bare domain from a referrer URL.
    Returns 'Direct' for None / empty / unparseable values.
    """
    if not referrer or not referrer.strip():
        return "Direct"
    try:
        parsed = urlparse(referrer.strip())
        domain = parsed.netloc or parsed.path
        # Strip www. prefix for cleaner grouping
        domain = domain.removeprefix("www.")
        return domain or "Direct"
    except Exception:
        return "Direct"


# ---------------------------------------------------------------------------
# 1. Enriched summary for a single link
# ---------------------------------------------------------------------------

def get_link_summary(
    db: Session,
    link_id: int,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> dict:
    """
    Returns total_clicks, last_clicked, clicks_today, clicks_this_week,
    clicks_this_month — all scoped to the optional date window.
    """
    now = _now_utc()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    base = db.query(ClickEvent).filter(ClickEvent.link_id == link_id)
    base = _apply_date_filters(base, from_dt, to_dt)

    stats = (
        db.query(
            func.count(ClickEvent.id).label("total"),
            func.max(ClickEvent.clicked_at).label("last"),
        )
        .filter(ClickEvent.link_id == link_id)
    )
    stats = _apply_date_filters(stats, from_dt, to_dt)
    row = stats.first()

    def _period_count(since: datetime) -> int:
        q = db.query(func.count(ClickEvent.id)).filter(
            ClickEvent.link_id == link_id,
            ClickEvent.clicked_at >= since,
        )
        if to_dt:
            q = q.filter(ClickEvent.clicked_at <= to_dt)
        return q.scalar() or 0

    return {
        "link_id": link_id,
        "total_clicks": row.total if row else 0,
        "last_clicked": row.last.isoformat() if row and row.last else None,
        "clicks_today": _period_count(today_start),
        "clicks_this_week": _period_count(week_start),
        "clicks_this_month": _period_count(month_start),
    }


# ---------------------------------------------------------------------------
# 2. Time-series
# ---------------------------------------------------------------------------

def get_timeseries(
    db: Session,
    link_id: int,
    granularity: Literal["day", "hour"] = "day",
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> dict:
    """
    Returns click counts bucketed by day or hour.

    Uses Postgres ``date_trunc`` which handles timezone-aware timestamps
    correctly. Falls back to SQLite ``strftime`` if the dialect is not
    PostgreSQL (e.g. in-memory test databases).
    """
    dialect = db.bind.dialect.name if db.bind else "postgresql"

    if dialect == "postgresql":
        trunc_unit = "day" if granularity == "day" else "hour"
        period_expr = func.date_trunc(trunc_unit, ClickEvent.clicked_at).label("period")
    else:
        # SQLite fallback
        fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m-%dT%H:00"
        period_expr = func.strftime(fmt, ClickEvent.clicked_at).label("period")

    rows = (
        db.query(period_expr, func.count(ClickEvent.id).label("clicks"))
        .filter(ClickEvent.link_id == link_id)
    )
    rows = _apply_date_filters(rows, from_dt, to_dt)
    rows = rows.group_by("period").order_by("period").all()

    def _fmt_period(p) -> str:
        if hasattr(p, "isoformat"):
            # Postgres returns a datetime object from date_trunc
            return p.date().isoformat() if granularity == "day" else p.isoformat()
        return str(p)

    return {
        "granularity": granularity,
        "from": from_dt.date().isoformat() if from_dt else None,
        "to": to_dt.date().isoformat() if to_dt else None,
        "data": [{"period": _fmt_period(r.period), "clicks": r.clicks} for r in rows],
    }


# ---------------------------------------------------------------------------
# 3. Referrer breakdown
# ---------------------------------------------------------------------------

def get_referrer_breakdown(
    db: Session,
    link_id: int,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
    top_n: int = 10,
) -> dict:
    """
    Returns top-N referrer domains with click counts and percentage share.
    Null / empty referrers are bucketed as 'Direct'.
    """
    rows = (
        db.query(ClickEvent.referrer, func.count(ClickEvent.id).label("clicks"))
        .filter(ClickEvent.link_id == link_id)
    )
    rows = _apply_date_filters(rows, from_dt, to_dt)
    rows = rows.group_by(ClickEvent.referrer).all()

    # Aggregate by domain (multiple referrer URLs may share the same domain)
    domain_counts: dict[str, int] = {}
    for referrer, count in rows:
        domain = _extract_domain(referrer)
        domain_counts[domain] = domain_counts.get(domain, 0) + count

    total = sum(domain_counts.values())

    # Sort by count desc, take top N
    sorted_items = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    data = [
        {
            "referrer": domain,
            "clicks": count,
            "pct": round(count / total * 100, 1) if total > 0 else 0.0,
        }
        for domain, count in sorted_items
    ]

    return {"total_clicks": total, "data": data}


# ---------------------------------------------------------------------------
# 4. Device / browser breakdown
# ---------------------------------------------------------------------------

def get_device_breakdown(
    db: Session,
    link_id: int,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> dict:
    """
    Fetches all user-agent strings for this link and aggregates them into
    browser, OS, and device-type buckets using the pure-Python UA parser.
    """
    from app.services.ua_parser import aggregate_ua_list

    query = db.query(ClickEvent.user_agent).filter(ClickEvent.link_id == link_id)
    query = _apply_date_filters(query, from_dt, to_dt)
    ua_strings = [row[0] for row in query.all()]

    return aggregate_ua_list(ua_strings)


# ---------------------------------------------------------------------------
# 5. Cross-link summary (dashboard totals)
# ---------------------------------------------------------------------------

def get_user_summary(db: Session, created_by: str, top_n: int = 5) -> dict:
    """
    Returns aggregate stats across all links owned by `created_by`:
    - total_links
    - total_clicks
    - clicks_today
    - top_links (by total click count, limited to top_n)
    """
    now = _now_utc()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # All link IDs for this user
    link_ids = [
        row[0]
        for row in db.query(Link.id).filter(Link.created_by == created_by).all()
    ]

    total_links = len(link_ids)

    if not link_ids:
        return {
            "total_links": 0,
            "total_clicks": 0,
            "clicks_today": 0,
            "top_links": [],
        }

    total_clicks = (
        db.query(func.count(ClickEvent.id))
        .filter(ClickEvent.link_id.in_(link_ids))
        .scalar()
    ) or 0

    clicks_today = (
        db.query(func.count(ClickEvent.id))
        .filter(
            ClickEvent.link_id.in_(link_ids),
            ClickEvent.clicked_at >= today_start,
        )
        .scalar()
    ) or 0

    # Top N links by click count
    top_rows = (
        db.query(
            Link.id,
            Link.code,
            Link.long_url,
            func.count(ClickEvent.id).label("clicks"),
        )
        .outerjoin(ClickEvent, Link.id == ClickEvent.link_id)
        .filter(Link.created_by == created_by)
        .group_by(Link.id, Link.code, Link.long_url)
        .order_by(func.count(ClickEvent.id).desc())
        .limit(top_n)
        .all()
    )

    top_links = [
        {"id": r.id, "code": r.code, "long_url": r.long_url, "clicks": r.clicks}
        for r in top_rows
    ]

    return {
        "total_links": total_links,
        "total_clicks": total_clicks,
        "clicks_today": clicks_today,
        "top_links": top_links,
    }
