from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.models.user import User
from app.utils.security import hash_password, verify_password, create_access_token, get_current_user
from app.services.guest_service import create_guest_account

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_guest: bool = False

    class Config:
        from_attributes = True


@router.post("/register", response_model=UserResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=req.email,
        username=req.username,
        hashed_password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.post("/guest", response_model=TokenResponse)
@router.post("/guest-login", response_model=TokenResponse)
def guest_login(db: Session = Depends(get_db)):
    """Instantly authenticate as a guest user with preloaded DB connection and mock conversations."""
    guest_user = create_guest_account(db)
    token = create_access_token(data={"sub": str(guest_user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    is_guest = current_user.username.startswith("guest_") or current_user.email.endswith("@sqlnav.demo")
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        is_guest=is_guest,
    )


@router.get("/onboarding-status")
def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check whether the user has completed onboarding (connection + knowledge base)."""
    from app.models.connection import DBConnection
    from app.models.knowledge import KnowledgeBase

    has_connection = (
        db.query(DBConnection)
        .filter(DBConnection.user_id == current_user.id)
        .first()
        is not None
    )

    has_knowledge_base = False
    if has_connection:
        user_conn_ids = [
            c.id
            for c in db.query(DBConnection)
            .filter(DBConnection.user_id == current_user.id)
            .all()
        ]
        has_knowledge_base = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.connection_id.in_(user_conn_ids))
            .first()
            is not None
        )

    return {
        "has_connection": has_connection,
        "has_knowledge_base": has_knowledge_base,
        "onboarding_complete": has_connection and has_knowledge_base,
    }
