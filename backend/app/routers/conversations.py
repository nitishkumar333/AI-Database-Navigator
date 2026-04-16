from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
import json
from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, ConversationMessage
from app.utils.security import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


class CreateConversationRequest(BaseModel):
    id: str
    name: str = "New Conversation"


class UpdateConversationRequest(BaseModel):
    name: str


class MessageResponse(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    message_type: str
    metadata_json: str
    query_id: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0

    class Config:
        from_attributes = True


class ConversationDetailResponse(BaseModel):
    id: str
    name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


@router.get("", response_model=List[ConversationListResponse])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all conversations for the current user with message counts."""
    results = (
        db.query(
            Conversation,
            func.count(ConversationMessage.id).label("message_count"),
        )
        .outerjoin(ConversationMessage, Conversation.id == ConversationMessage.conversation_id)
        .filter(Conversation.user_id == current_user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return [
        ConversationListResponse(
            id=conv.id,
            name=conv.name,
            created_at=str(conv.created_at) if conv.created_at else None,
            updated_at=str(conv.updated_at) if conv.updated_at else None,
            message_count=count,
        )
        for conv, count in results
    ]


@router.post("", response_model=ConversationListResponse)
def create_conversation(
    req: CreateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new conversation."""
    existing = db.query(Conversation).filter(Conversation.id == req.id).first()
    if existing:
        # Already exists — just return it
        return ConversationListResponse(
            id=existing.id,
            name=existing.name,
            created_at=str(existing.created_at) if existing.created_at else None,
            updated_at=str(existing.updated_at) if existing.updated_at else None,
            message_count=0,
        )

    conv = Conversation(
        id=req.id,
        user_id=current_user.id,
        name=req.name,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return ConversationListResponse(
        id=conv.id,
        name=conv.name,
        created_at=str(conv.created_at) if conv.created_at else None,
        updated_at=str(conv.updated_at) if conv.updated_at else None,
        message_count=0,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a conversation with all its messages."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )

    return ConversationDetailResponse(
        id=conv.id,
        name=conv.name,
        created_at=str(conv.created_at) if conv.created_at else None,
        updated_at=str(conv.updated_at) if conv.updated_at else None,
        messages=[
            MessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                message_type=m.message_type,
                metadata_json=m.metadata_json or "{}",
                query_id=m.query_id,
                created_at=str(m.created_at) if m.created_at else None,
            )
            for m in messages
        ],
    )


@router.put("/{conversation_id}")
def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update conversation name."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.name = req.name
    db.commit()
    return {"ok": True}


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Delete messages first
    db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
