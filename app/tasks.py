from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models import ClickEvent
from app.celery_app import celery_app

logger = logging.getLogger("url_shortener")


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_ignore_result=True
)
def log_click_task(self, link_id: int, user_agent: str, referrer: str, ip_hash: str, request_id: str):
    """
    Asynchronously writes a click event to the database.
    Ensures idempotency using a unique database constraint on request_id.
    """
    logger.info(f"Background task starting: log_click_task for link_id={link_id}, request_id={request_id}")

    db = SessionLocal()
    try:
        # Create ClickEvent instance
        click = ClickEvent(
            link_id=link_id,
            user_agent=user_agent,
            referrer=referrer,
            ip_hash=ip_hash,
            request_id=request_id
        )
        db.add(click)
        db.commit()
        logger.info(f"Successfully recorded click for link_id={link_id}, request_id={request_id}")

        # Check for Webhook Subscriptions
        try:
            from models import Link, WebhookSubscription
            db_link = db.query(Link).filter(Link.id == link_id).first()
            if db_link and db_link.created_by:
                sub = db.query(WebhookSubscription).filter(WebhookSubscription.created_by == db_link.created_by).first()
                if sub:
                    payload = {
                        "event": "link.click",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "link": {
                            "id": db_link.id,
                            "code": db_link.code,
                            "long_url": db_link.long_url
                        },
                        "click": {
                            "user_agent": user_agent,
                            "referrer": referrer,
                            "ip_hash": ip_hash,
                            "request_id": request_id
                        }
                    }
                    dispatch_webhook_task.delay(sub.url, payload)
        except Exception as we:
            logger.error(f"Error initiating webhook dispatch: {str(we)}")

        return {"status": "success", "request_id": request_id}

    except IntegrityError:
        db.rollback()
        # Unique constraint violation means this click was already processed (idempotency key match)
        logger.warning(
            f"Idempotency hit: click event with request_id={request_id} "
            f"already exists in the database. Skipping to prevent double-counting."
        )
        return {"status": "duplicate_ignored", "request_id": request_id}

    except Exception as exc:
        db.rollback()
        logger.error(f"Error logging click event (request_id={request_id}): {str(exc)}. Retrying...")
        # Re-raise the exception to trigger the Celery autoretry mechanism
        raise exc

    finally:
        db.close()


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    autoretry_for=(Exception,)
)
def purge_clicks_task(self, retention_days: int):
    """
    Cleans up old ClickEvent records older than the specified retention_days.
    """
    logger.info(f"Background task starting: purge_clicks_task with retention_days={retention_days}")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    db = SessionLocal()
    try:
        # Delete old records
        deleted_count = db.query(ClickEvent).filter(ClickEvent.clicked_at < cutoff_date).delete()
        db.commit()

        logger.info(f"Purge complete. Permanently deleted {deleted_count} click records older than {cutoff_date}")
        return {"status": "success", "deleted_count": deleted_count, "cutoff_date": str(cutoff_date)}

    except Exception as exc:
        db.rollback()
        logger.error(f"Error during click event purge: {str(exc)}")
        raise exc

    finally:
        db.close()


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=10,
    retry_backoff=True,
    autoretry_for=(Exception,),
    retry_ignore_result=True
)
def dispatch_webhook_task(self, url: str, payload: dict):
    """
    Asynchronously POSTs the webhook payload to the registered callback URL.
    Retries up to 5 times with exponential backoff on failure.
    """
    import httpx
    logger.info(f"Dispatching webhook to URL '{url}' for event '{payload.get('event')}'")
    try:
        # Enforce 5.0 second timeout for webhook POST
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, json=payload)
            if response.status_code not in (200, 201, 202, 204):
                raise Exception(f"Webhook receiver returned status code {response.status_code}")
            logger.info(f"Successfully dispatched webhook to '{url}' (status {response.status_code})")
            return {"status": "success", "url": url}
    except Exception as exc:
        logger.error(f"Failed to dispatch webhook to '{url}': {str(exc)}")
        # Raise to trigger Celery retry
        raise exc
