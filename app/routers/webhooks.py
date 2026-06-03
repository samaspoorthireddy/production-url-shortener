from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import WebhookSubscription
from app.schemas.webhook import WebhookCreate, WebhookResponse
from app.services.url_validator import validate_destination_url
from app.dependencies import get_current_user

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def register_webhook(
    payload: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Registers or updates the webhook callback URL for the authenticated user.
    Reuses the secure SSRF validator to block callbacks to internal resources.
    """
    try:
        # Enforce security: Webhook URL must pass same SSRF/security checks as short links!
        safe_url = validate_destination_url(payload.url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid webhook callback URL: {str(e)}"
        )

    # Check if subscription already exists for this user
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.created_by == current_user).first()
    if sub:
        # Update existing
        sub.url = safe_url
        db.commit()
        db.refresh(sub)
    else:
        # Create new
        sub = WebhookSubscription(url=safe_url, created_by=current_user)
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


@router.get("/", response_model=WebhookResponse)
def get_webhook(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Retrieves the currently registered webhook details for the user.
    """
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.created_by == current_user).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No webhook subscription registered for this user."
        )
    return sub


@router.delete("/", status_code=status.HTTP_200_OK)
def delete_webhook(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Deletes the registered webhook subscription for the user.
    """
    sub = db.query(WebhookSubscription).filter(WebhookSubscription.created_by == current_user).first()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No webhook subscription registered for this user."
        )
    db.delete(sub)
    db.commit()
    return {"detail": "Webhook subscription deleted successfully"}
