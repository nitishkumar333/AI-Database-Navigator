from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from datetime import datetime, timezone
from app.database import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("db_connections.id"), nullable=False)
    table_name = Column(String, nullable=False)
    table_description = Column(Text, default="")
    column_descriptions = Column(JSON, default=dict)
    sample_queries = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class KnowledgeBaseGroup(Base):
    __tablename__ = "knowledge_base_group"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    connection_id = Column(Integer, ForeignKey("db_connections.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class KnowledgeBaseGroupTable(Base):
    __tablename__ = "knowledge_base_group_table"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("knowledge_base_group.id", ondelete="CASCADE"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
