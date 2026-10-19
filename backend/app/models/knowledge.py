from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from datetime import datetime, timezone
from app.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    tables = Column(JSON, default=list)
    connection_id = Column(Integer, ForeignKey("db_connections.id", ondelete="CASCADE"), nullable=False,
                           index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
