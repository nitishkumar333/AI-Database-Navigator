from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Float
from datetime import datetime, timezone
from app.database import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    connection_id = Column(Integer, ForeignKey("db_connections.id"), nullable=False)
    nl_query = Column(Text, nullable=False)
    generated_sql = Column(Text, default="")
    row_count = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(Text, default="")
    latency_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
