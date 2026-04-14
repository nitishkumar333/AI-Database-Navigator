from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from pydantic import BaseModel
from typing import Dict, List, Optional
from app.database import get_db
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.utils.security import get_current_user
from app.utils.db_manager import get_user_engine
from app.services.embeddings import embed_knowledge

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])


class KnowledgeCreate(BaseModel):
    table_name: str
    table_description: str = ""
    column_descriptions: Dict[str, str] = {}
    sample_queries: List[str] = []


class KnowledgeUpdate(BaseModel):
    table_description: Optional[str] = None
    column_descriptions: Optional[Dict[str, str]] = None
    sample_queries: Optional[List[str]] = None


class KnowledgeResponse(BaseModel):
    id: int
    connection_id: int
    table_name: str
    table_description: str
    column_descriptions: dict
    sample_queries: list

    class Config:
        from_attributes = True


class KnowledgeBaseGroupCreate(BaseModel):
    name: str
    table_names: List[str]


class KnowledgeBaseGroupResponse(BaseModel):
    id: int
    connection_id: int
    name: str
    tables: List[KnowledgeResponse]
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


# NOTE: /user/all must be defined BEFORE /{conn_id} to prevent
# FastAPI from matching "user" as a conn_id path parameter.


@router.get("/user/groups/all", response_model=List[KnowledgeBaseGroupResponse])
def list_all_user_knowledge_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all knowledge base groups across all connections for the current user."""
    from app.models.knowledge import KnowledgeBaseGroup, KnowledgeBaseGroupTable
    user_connections = db.query(DBConnection).filter(
        DBConnection.user_id == current_user.id
    ).all()
    conn_ids = [c.id for c in user_connections]
    if not conn_ids:
        return []
    
    groups = db.query(KnowledgeBaseGroup).filter(
        KnowledgeBaseGroup.connection_id.in_(conn_ids)
    ).all()
    
    result = []
    for g in groups:
        kb_links = db.query(KnowledgeBaseGroupTable).filter(KnowledgeBaseGroupTable.group_id == g.id).all()
        kb_ids = [link.knowledge_base_id for link in kb_links]
        kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all() if kb_ids else []
        
        result.append(KnowledgeBaseGroupResponse(
            id=g.id,
            connection_id=g.connection_id,
            name=g.name,
            tables=[KnowledgeResponse.model_validate(kb) for kb in kbs],
            created_at=str(g.created_at) if g.created_at else None
        ))
    return result


@router.post("/{conn_id}", response_model=KnowledgeResponse, status_code=201)
def add_to_knowledge_base(
    conn_id: int,
    req: KnowledgeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conn = _get_connection(conn_id, current_user, db)

    # Check if already exists
    existing = db.query(KnowledgeBase).filter(
        KnowledgeBase.connection_id == conn_id,
        KnowledgeBase.table_name == req.table_name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Table already in knowledge base")

    kb = KnowledgeBase(
        connection_id=conn_id,
        table_name=req.table_name,
        table_description=req.table_description,
        column_descriptions=req.column_descriptions,
        sample_queries=req.sample_queries,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)

    # Embed into ChromaDB
    try:
        embed_knowledge(conn_id, kb)
    except Exception as e:
        print(f"Warning: Failed to embed knowledge: {e}")

    return kb


@router.get("/{conn_id}", response_model=List[KnowledgeResponse])
def list_knowledge(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_connection(conn_id, current_user, db)
    return db.query(KnowledgeBase).filter(KnowledgeBase.connection_id == conn_id).all()


@router.put("/{conn_id}/{kb_id}", response_model=KnowledgeResponse)
def update_knowledge(
    conn_id: int,
    kb_id: int,
    req: KnowledgeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_connection(conn_id, current_user, db)
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id, KnowledgeBase.connection_id == conn_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")

    if req.table_description is not None:
        kb.table_description = req.table_description
    if req.column_descriptions is not None:
        kb.column_descriptions = req.column_descriptions
    if req.sample_queries is not None:
        kb.sample_queries = req.sample_queries

    db.commit()
    db.refresh(kb)

    try:
        embed_knowledge(conn_id, kb)
    except Exception as e:
        print(f"Warning: Failed to embed knowledge: {e}")

    return kb


@router.delete("/{conn_id}/{kb_id}")
def delete_knowledge(
    conn_id: int,
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_connection(conn_id, current_user, db)
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id, KnowledgeBase.connection_id == conn_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    db.delete(kb)
    db.commit()
    return {"message": "Knowledge entry deleted"}


class BulkKnowledgeCreate(BaseModel):
    table_names: List[str]


@router.post("/{conn_id}/bulk", response_model=List[KnowledgeResponse], status_code=201)
def bulk_add_to_knowledge_base(
    conn_id: int,
    req: BulkKnowledgeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add multiple tables to the knowledge base at once."""
    conn = _get_connection(conn_id, current_user, db)
    created = []

    for table_name in req.table_names:
        # Skip if already exists
        existing = db.query(KnowledgeBase).filter(
            KnowledgeBase.connection_id == conn_id,
            KnowledgeBase.table_name == table_name,
        ).first()
        if existing:
            created.append(existing)
            continue

        kb = KnowledgeBase(
            connection_id=conn_id,
            table_name=table_name,
            table_description="",
            column_descriptions={},
            sample_queries=[],
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)

        try:
            embed_knowledge(conn_id, kb)
        except Exception as e:
            print(f"Warning: Failed to embed knowledge for {table_name}: {e}")

        created.append(kb)

    return created


@router.get("/{conn_id}/groups", response_model=List[KnowledgeBaseGroupResponse])
def list_knowledge_groups(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all knowledge base groups for a specific connection."""
    from app.models.knowledge import KnowledgeBaseGroup, KnowledgeBaseGroupTable
    _get_connection(conn_id, current_user, db)
    
    groups = db.query(KnowledgeBaseGroup).filter(
        KnowledgeBaseGroup.connection_id == conn_id
    ).all()
    
    result = []
    for g in groups:
        kb_links = db.query(KnowledgeBaseGroupTable).filter(KnowledgeBaseGroupTable.group_id == g.id).all()
        kb_ids = [link.knowledge_base_id for link in kb_links]
        kbs = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all() if kb_ids else []
        
        result.append(KnowledgeBaseGroupResponse(
            id=g.id,
            connection_id=g.connection_id,
            name=g.name,
            tables=[KnowledgeResponse.model_validate(kb) for kb in kbs],
            created_at=str(g.created_at) if g.created_at else None
        ))
    return result


@router.post("/{conn_id}/group", response_model=KnowledgeBaseGroupResponse, status_code=201)
def create_knowledge_group(
    conn_id: int,
    req: KnowledgeBaseGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new named knowledge base group containing specific tables."""
    from app.models.knowledge import KnowledgeBaseGroup, KnowledgeBaseGroupTable
    conn = _get_connection(conn_id, current_user, db)
    
    # Check if a group with the same name already exists
    existing_group = db.query(KnowledgeBaseGroup).filter(
        KnowledgeBaseGroup.connection_id == conn_id,
        KnowledgeBaseGroup.name == req.name
    ).first()
    if existing_group:
        raise HTTPException(status_code=409, detail="A Knowledge Base with this name already exists")
        
    group = KnowledgeBaseGroup(
        name=req.name,
        connection_id=conn_id
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    
    tables_added = []
    # Find or create KB entries, and link them
    for table_name in req.table_names:
        kb = db.query(KnowledgeBase).filter(
            KnowledgeBase.connection_id == conn_id,
            KnowledgeBase.table_name == table_name
        ).first()
        
        if not kb:
            kb = KnowledgeBase(
                connection_id=conn_id,
                table_name=table_name,
                table_description="",
                column_descriptions={},
                sample_queries=[],
            )
            db.add(kb)
            db.commit()
            db.refresh(kb)
            
            # Embed if new
            try:
                embed_knowledge(conn_id, kb)
            except Exception as e:
                print(f"Warning: Failed to embed knowledge for {table_name}: {e}")
                
        # Create link
        link = KnowledgeBaseGroupTable(
            group_id=group.id,
            knowledge_base_id=kb.id
        )
        db.add(link)
        tables_added.append(kb)
        
    db.commit()
    
    return KnowledgeBaseGroupResponse(
        id=group.id,
        connection_id=group.connection_id,
        name=group.name,
        tables=[KnowledgeResponse.model_validate(kb) for kb in tables_added],
        created_at=str(group.created_at) if group.created_at else None
    )


@router.delete("/group/{group_id}")
def delete_knowledge_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a knowledge base group and its links. Keeps the underlying table metadata."""
    from app.models.knowledge import KnowledgeBaseGroup, KnowledgeBaseGroupTable
    group = db.query(KnowledgeBaseGroup).filter(KnowledgeBaseGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Knowledge Base Group not found")
        
    _get_connection(group.connection_id, current_user, db)
    
    db.query(KnowledgeBaseGroupTable).filter(KnowledgeBaseGroupTable.group_id == group_id).delete()
    db.delete(group)
    db.commit()
    return {"message": "Knowledge Base Group deleted"}




@router.post("/{conn_id}/auto-describe")
def auto_describe_tables(
    conn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Use LLM to auto-generate descriptions for all KB tables."""
    from app.services.nl_to_sql import get_llm
    conn = _get_connection(conn_id, current_user, db)
    engine = get_user_engine(conn)
    inspector = inspect(engine)

    kb_entries = db.query(KnowledgeBase).filter(KnowledgeBase.connection_id == conn_id).all()
    results = []

    for kb in kb_entries:
        columns = inspector.get_columns(kb.table_name)
        col_info = ", ".join([f"{c['name']} ({c['type']})" for c in columns])

        try:
            llm = get_llm()
            prompt = f"""Describe this database table concisely.
Table: {kb.table_name}
Columns: {col_info}

Provide:
1. A one-line table description
2. A brief description for each column

Format as JSON: {{"table_description": "...", "column_descriptions": {{"col_name": "description"}}}}"""

            response = llm.invoke(prompt)
            import json
            # Try to parse structured response
            content = response.content
            # Find JSON in response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
                kb.table_description = data.get("table_description", kb.table_description)
                kb.column_descriptions = data.get("column_descriptions", kb.column_descriptions)
                db.commit()
                db.refresh(kb)
                results.append({"table": kb.table_name, "status": "success"})
            else:
                results.append({"table": kb.table_name, "status": "failed", "error": "Could not parse LLM response"})
        except Exception as e:
            results.append({"table": kb.table_name, "status": "failed", "error": str(e)})

    return {"results": results}
