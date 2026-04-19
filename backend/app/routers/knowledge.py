from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.utils.security import get_current_user
from app.services.redis_client import redis_client
from fastapi.encoders import jsonable_encoder
import json

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])


class KnowledgeBaseCreate(BaseModel):
    name: str
    table_names: List[str]


class KnowledgeBaseResponse(BaseModel):
    id: int
    connection_id: int
    name: str
    tables: List[str]
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


def _get_connection(conn_id: int, user: User, db: Session) -> DBConnection:
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.user_id == user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.get("/user/groups/all", response_model=List[KnowledgeBaseResponse])
def list_all_user_knowledge_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all knowledge bases across all connections for the current user."""

    cache_key = f"kb:user:{current_user.id}:connections:all"
    cached = redis_client.get(cache_key)
    if cached is not None:
        return cached

    user_connections = db.query(DBConnection).filter(
        DBConnection.user_id == current_user.id
    ).all()
    conn_ids = [c.id for c in user_connections]
    if not conn_ids:
        redis_client.set(cache_key, [])
        return []
    
    kbs = db.query(KnowledgeBase).filter(
        KnowledgeBase.connection_id.in_(conn_ids)
    ).all()
    
    result = []
    for kb in kbs:
        result.append(KnowledgeBaseResponse(
            id=kb.id,
            connection_id=kb.connection_id,
            name=kb.name,
            tables=kb.tables,
            created_at=str(kb.created_at) if kb.created_at else None
        ))
    redis_client.set(cache_key, json.dumps(jsonable_encoder(result)))
    return result


@router.get("/{conn_id}/groups", response_model=List[KnowledgeBaseResponse])
def list_knowledge_groups(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all knowledge bases for a specific connection."""

    cache_key = f"kb:user:{current_user.id}:connection:{conn_id}:groups"
    cached = redis_client.get(cache_key)
    if cached is not None:
        print("Cache hit", cache_key)
        return cached

    _get_connection(conn_id, current_user, db)
    
    kbs = db.query(KnowledgeBase).filter(
        KnowledgeBase.connection_id == conn_id
    ).all()
    
    result = []
    for kb in kbs:
        result.append(KnowledgeBaseResponse(
            id=kb.id,
            connection_id=kb.connection_id,
            name=kb.name,
            tables=kb.tables,
            created_at=str(kb.created_at) if kb.created_at else None
        ))
    
    redis_client.set(cache_key, json.dumps(jsonable_encoder(result)))
    return result


@router.post("/{conn_id}/group", response_model=KnowledgeBaseResponse, status_code=201)
def create_knowledge_group(
    conn_id: int,
    req: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new named knowledge base containing specific tables."""
    conn = _get_connection(conn_id, current_user, db)
    
    # Check if a KnowledgeBase with the same name already exists
    existing_kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.connection_id == conn_id,
        KnowledgeBase.name == req.name
    ).first()
    if existing_kb:
        raise HTTPException(status_code=409, detail="A Knowledge Base with this name already exists")
        
    kb = KnowledgeBase(
        name=req.name,
        tables=req.table_names,
        connection_id=conn_id
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)

    cache_key = f"kb:user:{current_user.id}:connection:{conn_id}:groups"
    redis_client.delete(cache_key)

    cache_key = f"kb:user:{current_user.id}:connections:all"
    redis_client.delete(cache_key)
    
    return KnowledgeBaseResponse(
        id=kb.id,
        connection_id=kb.connection_id,
        name=kb.name,
        tables=kb.tables,
        created_at=str(kb.created_at) if kb.created_at else None
    )


@router.delete("/group/{group_id}")
def delete_knowledge_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a knowledge base."""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == group_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found")
        
    _get_connection(kb.connection_id, current_user, db)
    
    db.delete(kb)
    db.commit()

    cache_key = f"kb:user:{current_user.id}:connection:{kb.connection_id}:groups"
    redis_client.delete(cache_key)

    cache_key = f"kb:user:{current_user.id}:connections:all"
    redis_client.delete(cache_key)
    
    return {"message": "Knowledge Base deleted"}
