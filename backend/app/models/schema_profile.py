from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class SchemaProfileRecord(Base):
    """Latest schema profile of a connection (see services/schema_index)."""
    __tablename__ = "schema_profiles"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(
        Integer, ForeignKey("db_connections.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )
    status = Column(String, nullable=False, default="pending")        # pending | running | ready | failed
    description_status = Column(String, nullable=False, default="idle")  # idle | running | done | partial | failed | disabled
    schema_hash = Column(String)
    profile = Column(JSON)                      # SchemaProfile.to_dict()
    described_tables = Column(JSON, default=dict)   # {table: structure_hash it was described at}
    error = Column(Text)
    # Bumped whenever the profile or any description changes; cache keys use it.
    version = Column(Integer, nullable=False, default=0)
    profiled_at = Column(DateTime)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class SchemaAnnotation(Base):
    """A table or column description. source="user" rows are never
    overwritten by generated ones."""
    __tablename__ = "schema_annotations"
    __table_args__ = (UniqueConstraint("connection_id", "table_name", "column_name"),)

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(
        Integer, ForeignKey("db_connections.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    table_name = Column(String, nullable=False)
    column_name = Column(String, nullable=False, default="")    # "" = the table itself
    description = Column(Text, nullable=False)
    source = Column(String, nullable=False)                     # generated | user
    updated_at = Column(DateTime, default=_now, onupdate=_now)
