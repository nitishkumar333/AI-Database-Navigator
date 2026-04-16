from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.utils.security import get_current_user, encrypt_value
from app.utils.db_manager import test_connection as test_db_conn, remove_engine
from datetime import datetime

router = APIRouter(prefix="/api/connections", tags=["Database Connections"])


class ConnectionCreate(BaseModel):
    name: str
    host: str
    port: int = 5432
    db_name: str
    username: str
    password: str


class ConnectionResponse(BaseModel):
    id: int
    name: str
    host: str
    port: int
    db_name: str
    username: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    host: str
    port: int = 5432
    db_name: str
    username: str
    password: str


@router.post("", response_model=ConnectionResponse, status_code=201)
def create_connection(
    req: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Test connection first
    result = test_db_conn(req.host, req.port, req.db_name, req.username, req.password)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=f"Connection failed: {result['message']}")

    conn = DBConnection(
        user_id=current_user.id,
        name=req.name,
        host=req.host,
        port=req.port,
        db_name=req.db_name,
        username=req.username,
        encrypted_password=encrypt_value(req.password),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.get("", response_model=List[ConnectionResponse])
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(DBConnection).filter(DBConnection.user_id == current_user.id).all()


@router.post("/test")
def test_connection(
    req: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
):
    return test_db_conn(req.host, req.port, req.db_name, req.username, req.password)


@router.delete("/{conn_id}")
def delete_connection(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.user_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    remove_engine(conn_id)
    db.delete(conn)
    db.commit()
    return {"message": "Connection deleted"}
