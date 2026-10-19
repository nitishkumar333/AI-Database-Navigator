from sqlalchemy import JSON, Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime, timezone
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, index=True)  # UUID from frontend
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, default="New Conversation")
    suggestions = Column(JSON, nullable=True)  # latest follow-up suggestions (list of str)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ConversationConnection(Base):
    """A database connection a conversation queried at least once. Deleting
    the connection deletes these conversations (see services/connection_cleanup.py)."""
    __tablename__ = "conversation_connections"

    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    connection_id = Column(Integer, ForeignKey("db_connections.id", ondelete="CASCADE"), primary_key=True,
                           index=True)
    first_used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,
                             index=True)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)  # The text content
    message_type = Column(String, default="text")  # "text", "result"
    metadata_json = Column(Text, default="{}")  # JSON blob for SQL, rows, etc.
    query_id = Column(String, nullable=True)  # Groups user+assistant messages
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
