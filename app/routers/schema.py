from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine

router = APIRouter(prefix="/api/schema", tags=["Schema Explorer"])


def _get_connection(conn_id: int, user: User, db: Session) -> DBConnection:
    conn = db.query(DBConnection).filter(
        DBConnection.id == conn_id, DBConnection.user_id == user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.get("/{conn_id}/tables")
def list_tables(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    result = []
    for table in tables:
        columns = inspector.get_columns(table)
        result.append({
            "name": table,
            "column_count": len(columns),
        })
    return result


@router.get("/{conn_id}/tables/{table_name}/columns")
def get_columns(
    conn_id: int,
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)
    inspector = inspect(engine)

    columns = inspector.get_columns(table_name)
    pk_constraint = inspector.get_pk_constraint(table_name)
    fk_constraints = inspector.get_foreign_keys(table_name)

    pk_columns = pk_constraint.get("constrained_columns", []) if pk_constraint else []
    fk_map = {}
    for fk in fk_constraints:
        for col in fk.get("constrained_columns", []):
            fk_map[col] = {
                "referred_table": fk.get("referred_table"),
                "referred_columns": fk.get("referred_columns"),
            }

    result = []
    for col in columns:
        result.append({
            "name": col["name"],
            "type": str(col["type"]),
            "nullable": col.get("nullable", True),
            "default": str(col.get("default", "")) if col.get("default") else None,
            "is_primary_key": col["name"] in pk_columns,
            "foreign_key": fk_map.get(col["name"]),
        })
    return result


@router.get("/{conn_id}/tables/{table_name}/preview")
def preview_table(
    conn_id: int,
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)

    # Sanitize table name
    from app.utils.sql_guard import sanitize_table_name
    safe_name = sanitize_table_name(table_name)

    with engine.connect() as connection:
        result = connection.execute(text(f'SELECT * FROM "{safe_name}" LIMIT 10'))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return {"columns": columns, "rows": rows}


@router.get("/{conn_id}/relationships")
def get_relationships(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    relationships = []
    for table in tables:
        fks = inspector.get_foreign_keys(table)
        for fk in fks:
            relationships.append({
                "from_table": table,
                "from_columns": fk.get("constrained_columns", []),
                "to_table": fk.get("referred_table"),
                "to_columns": fk.get("referred_columns", []),
            })
    return relationships
