import pytest
from sqlalchemy.orm import Session
from models import CommentThread, Comment, Notification
from app.services.mention_service import MentionService
from app.dependencies import API_KEYS


def test_extract_mentions_basic():
    """Test standard mention extraction and normalization."""
    # Basic mention
    assert MentionService.extract_mentions("Hello @user_a!") == ["user_a"]

    # Mentions at start and with spaces
    assert MentionService.extract_mentions("@user_b @user_a") == ["user_b", "user_a"]

    # Duplicate elimination preserving order
    assert MentionService.extract_mentions("Hey @user_b, tell @user_a and @user_b.") == ["user_b", "user_a"]

    # Case normalization to lowercase
    assert MentionService.extract_mentions("Hello @USER_A and @User_B") == ["user_a", "user_b"]

    # Invalid prefix (must be preceded by start of string or whitespace)
    assert MentionService.extract_mentions("email@user_a") == []
    assert MentionService.extract_mentions("abc@user_a") == []


def test_process_mentions_flow(db_session: Session):
    """Test process_mentions logic, including registry filtering, duplication checking, and DB insertion."""
    # Ensure our registry has user_a and user_b
    assert "user_a" in API_KEYS.values()
    assert "user_b" in API_KEYS.values()

    # Create dummy comment thread and comment to reference
    thread = CommentThread(target_type="link", target_id=1)
    db_session.add(thread)
    db_session.flush()

    comment = Comment(thread_id=thread.id, user_id="user_c", content="Calling @user_a and @user_unknown!")
    db_session.add(comment)
    db_session.flush()

    # Process mentions
    processed = MentionService.process_mentions(comment.content, comment.id, db_session)

    # user_a is valid, user_unknown is silently ignored
    assert processed == ["user_a"]

    # Check notification in database session (not committed yet)
    notifications = db_session.query(Notification).filter(Notification.comment_id == comment.id).all()
    assert len(notifications) == 1
    assert notifications[0].recipient_id == "user_a"
    assert notifications[0].is_read is False

    # Check that calling process_mentions again on the same text does not duplicate notifications
    processed_again = MentionService.process_mentions(comment.content, comment.id, db_session)
    assert processed_again == ["user_a"]

    notifications_again = db_session.query(Notification).filter(Notification.comment_id == comment.id).all()
    assert len(notifications_again) == 1
