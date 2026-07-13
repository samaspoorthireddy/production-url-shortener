from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from database import get_db
from models import CommentThread, Comment, Team, UserTeam, Link
from app.dependencies import get_current_user
from app.schemas.comments import (
    ThreadCreate,
    ThreadResponse,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
)
from app.services.mention_service import MentionService
from app.services.activity_feed import activity_feed_manager

logger = logging.getLogger("url_shortener.comments")

router = APIRouter(tags=["comments"])


@router.post("/threads", response_model=ThreadResponse)
def create_thread(
    payload: ThreadCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    if payload.target_type not in {"team", "link"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target_type. Must be 'team' or 'link'."
        )

    if payload.target_type == "team":
        team = db.query(Team).filter(Team.id == payload.target_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        membership = db.query(UserTeam).filter(
            UserTeam.team_id == payload.target_id,
            UserTeam.user_id == current_user
        ).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this team"
            )
    else:  # link
        link = db.query(Link).filter(Link.id == payload.target_id).first()
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found"
            )
        if link.created_by is not None and link.created_by != current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this link"
            )

    # Check if thread already exists
    thread = db.query(CommentThread).filter(
        CommentThread.target_type == payload.target_type,
        CommentThread.target_id == payload.target_id
    ).first()

    if thread:
        response.status_code = status.HTTP_200_OK
        return thread

    # Create new thread
    try:
        thread = CommentThread(
            target_type=payload.target_type,
            target_id=payload.target_id
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
        response.status_code = status.HTTP_201_CREATED
        return thread
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating thread: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )


@router.post("/threads/{thread_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    thread_id: int,
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    thread = db.query(CommentThread).filter(CommentThread.id == thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    if thread.target_type == "team":
        team = db.query(Team).filter(Team.id == thread.target_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        membership = db.query(UserTeam).filter(
            UserTeam.team_id == thread.target_id,
            UserTeam.user_id == current_user
        ).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this team"
            )
        if membership.role == "viewer":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Viewers cannot add comments"
            )
    else:  # link
        link = db.query(Link).filter(Link.id == thread.target_id).first()
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found"
            )
        if link.created_by is not None and link.created_by != current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this link"
            )

    try:
        comment = Comment(
            thread_id=thread_id,
            user_id=current_user,
            content=comment_in.content
        )
        db.add(comment)
        db.flush()

        # MentionService process mentions before committing
        MentionService.process_mentions(comment.content, comment.id, db)

        db.commit()
        db.refresh(comment)
        logger.info(
            f"Audit Log - Comment Created: thread_id={thread_id}, comment_id={comment.id}, user_id={current_user}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating comment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )

    # Broadcast event if target_type is team
    if thread.target_type == "team":
        event = {
            "event": "comment_created",
            "user_id": current_user,
            "team_id": thread.target_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": f"New comment added by {current_user} in thread {thread_id}"
        }
        await activity_feed_manager.broadcast(thread.target_id, event)

    return comment


@router.get("/threads/{thread_id}/comments", response_model=List[CommentResponse])
def get_comments(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    thread = db.query(CommentThread).filter(CommentThread.id == thread_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found"
        )

    if thread.target_type == "team":
        team = db.query(Team).filter(Team.id == thread.target_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        membership = db.query(UserTeam).filter(
            UserTeam.team_id == thread.target_id,
            UserTeam.user_id == current_user
        ).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this team"
            )
    else:  # link
        link = db.query(Link).filter(Link.id == thread.target_id).first()
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found"
            )
        if link.created_by is not None and link.created_by != current_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this link"
            )

    comments = db.query(Comment).filter(Comment.thread_id == thread_id).order_by(Comment.created_at.asc()).all()
    return comments


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )

    if comment.user_id != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this comment"
        )

    try:
        comment.content = comment_update.content
        db.commit()
        db.refresh(comment)
        return comment
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating comment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error occurred: {str(e)}"
        )
