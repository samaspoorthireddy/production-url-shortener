from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, validates
from database import Base


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    long_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(String(255), nullable=True)
    tags = Column(ARRAY(String(30)), nullable=False, server_default='{}')
    expires_at = Column(DateTime(timezone=True), nullable=True)   # None = never expires
    max_clicks = Column(Integer, nullable=True)                   # None = no cap

    # Metadata Scraping
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(1024), nullable=True)

    # Relationship to click events (cascade delete clicks if a link is deleted)
    clicks = relationship("ClickEvent", back_populates="link", cascade="all, delete-orphan")


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    link_id = Column(Integer, ForeignKey("links.id", ondelete="CASCADE"), nullable=False)
    clicked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    user_agent = Column(String(512), nullable=True)
    referrer = Column(String(512), nullable=True)
    ip_hash = Column(String(64), nullable=True)
    request_id = Column(String(255), unique=True, index=True, nullable=True)

    # Back-reference to the Link model
    link = relationship("Link", back_populates="clicks")


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(1024), nullable=False)
    created_by = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), index=True, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(String(255), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    memberships = relationship("UserTeam", back_populates="team", cascade="all, delete-orphan")
    invitations = relationship("TeamInvitation", back_populates="team", cascade="all, delete-orphan")


class UserTeam(Base):
    __tablename__ = "user_teams"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(255), index=True, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(30), nullable=False, default="member")
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    team = relationship("Team", back_populates="memberships")

    @validates("role")
    def validate_role(self, key, role):
        if role not in {"owner", "admin", "member", "viewer"}:
            raise ValueError("Role must be one of 'owner', 'admin', 'member', or 'viewer'")
        return role


class CommentThread(Base):
    __tablename__ = "comment_threads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    target_type = Column(String(50), index=True, nullable=False)
    target_id = Column(Integer, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    comments = relationship("Comment", back_populates="thread", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    thread_id = Column(Integer, ForeignKey("comment_threads.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), index=True, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    thread = relationship("CommentThread", back_populates="comments")
    notifications = relationship("Notification", back_populates="comment", cascade="all, delete-orphan")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    recipient_id = Column(String(255), index=True, nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    comment = relationship("Comment", back_populates="notifications")


class TeamInvitation(Base):
    __tablename__ = "team_invitations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="member")
    token = Column(String(255), unique=True, index=True, nullable=False)
    status = Column(String(30), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    team = relationship("Team", back_populates="invitations")
