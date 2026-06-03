from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
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
