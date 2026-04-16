from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User
from app.models.query_history import QueryHistory
from app.utils.security import get_current_user

router = APIRouter(prefix="/api/history", tags=["Query History"])


class HistoryResponse(BaseModel):
    id: int
    connection_id: int
    nl_query: str
    generated_sql: str
    row_count: int
    success: bool
    error_message: str
    latency_ms: float
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=List[HistoryResponse])
def list_history(
    connection_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(QueryHistory).filter(QueryHistory.user_id == current_user.id)
    if connection_id:
        query = query.filter(QueryHistory.connection_id == connection_id)
    return query.order_by(QueryHistory.created_at.desc()).limit(limit).all()


@router.get("/{history_id}", response_model=HistoryResponse)
def get_history(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(QueryHistory).filter(
        QueryHistory.id == history_id,
        QueryHistory.user_id == current_user.id,
    ).first()
    if not entry:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="History entry not found")
    return entry
