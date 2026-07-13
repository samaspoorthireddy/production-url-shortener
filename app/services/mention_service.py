import re
import logging
from typing import List
from sqlalchemy.orm import Session

from models import Notification
from app.dependencies import API_KEYS

logger = logging.getLogger("url_shortener.mention_service")


class MentionService:
    """
    Service containing business logic for parsing, extracting, and processing @mentions from comments.
    """

    @staticmethod
    def extract_mentions(text: str) -> List[str]:
        """
        Parses a text string and extracts unique @usernames.
        
        Rules:
        - Normalizes all extracted usernames to lowercase.
        - Usernames must start with '@' preceded by start of string or whitespace.
        - Mentions can only contain alphanumeric characters and underscores [a-zA-Z0-9_].
        - Returns a list of unique usernames in the order they appear (without the leading '@').
        """
        if not text:
            return []

        # Match '@' preceded by start of string or space, followed by alphanumeric/underscore chars
        pattern = r"(?:^|\s)@([a-zA-Z0-9_]+)"
        matches = re.findall(pattern, text)

        unique_users = []
        seen = set()

        for username in matches:
            normalized = username.lower()
            if normalized not in seen:
                seen.add(normalized)
                unique_users.append(normalized)

        logger.info(f"Extracted mentions from text: {unique_users}")
        return unique_users

    @classmethod
    def process_mentions(cls, text: str, comment_id: int, db: Session) -> List[str]:
        """
        Processes mentions in comment content. Checks usernames against active registry,
        creates notifications for valid mentioned users (silently ignoring unknown users),
        and adds them to the DB session without committing.
        
        Returns the list of valid usernames that were processed.
        """
        candidate_usernames = cls.extract_mentions(text)
        if not candidate_usernames:
            return []

        # Registry usernames normalized to lowercase for case-insensitive matching
        valid_registry_users = {user.lower() for user in API_KEYS.values()}

        processed_users = []
        for username in candidate_usernames:
            if username in valid_registry_users:
                # Check if notification already exists for this recipient and comment
                existing = db.query(Notification).filter(
                    Notification.recipient_id == username,
                    Notification.comment_id == comment_id
                ).first()

                if not existing:
                    db_notification = Notification(
                        recipient_id=username,
                        comment_id=comment_id,
                        is_read=False
                    )
                    db.add(db_notification)
                    db.flush()
                    logger.info(f"Created notification in session for user: {username}, comment: {comment_id}")
                else:
                    logger.info(f"Notification already exists for user: {username}, comment: {comment_id}")

                processed_users.append(username)

        return processed_users
