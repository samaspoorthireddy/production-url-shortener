import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Notification
from app.dependencies import get_current_user
from app.schemas.notifications import NotificationResponse

logger = logging.getLogger("url_shortener.notifications")
router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=List[NotificationResponse])
def get_notifications(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Returns all unread notifications for the authenticated user.
    """
    notifications = db.query(Notification).filter(
        Notification.recipient_id == current_user,
        Notification.is_read.is_(False)
    ).order_by(Notification.created_at.desc()).all()
    return notifications


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Marks a notification as read. Users can only mark their own notifications as read.
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    # Check permission boundary: user can only modify their own notification
    if notification.recipient_id != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this notification"
        )

    try:
        notification.is_read = True
        db.commit()
        db.refresh(notification)
        logger.info(f"Notification {notification_id} marked as read by user {current_user}")
        return notification
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
