"""
Guest User Service
==================
One fixed guest account, used by everyone who clicks "Login as Guest". It is an
ordinary account (conversations and history are stored like anyone else's)
except that it has no usable password and its only database connection is the
preconfigured "shop" database (GUEST_DB_* settings), which it cannot change,
and it cannot delete knowledge groups.
"""

import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.services.schema_index.service import schedule_refresh
from app.utils.db_manager import remove_engine
from app.utils.security import hash_password, encrypt_value, decrypt_value

GUEST_EMAIL = "guest@sqlnav.demo"
GUEST_USERNAME = "guest"
GUEST_DOMAIN = "@sqlnav.demo"
SHOP_TABLES = [
    "categories",
    "products",
    "users",
    "addresses",
    "product_reviews",
    "orders",
    "coupons",
    "order_items",
    "payments",
]


def is_guest(user: User) -> bool:
    # The domain also matches the per-login guest_xxxx accounts created before
    # there was a single guest account.
    return user.email.endswith(GUEST_DOMAIN)


def get_guest_account(db: Session) -> User:
    """The guest user, created (with its shop connection and knowledge base)
    on the first guest login."""
    user = db.query(User).filter(User.email == GUEST_EMAIL).first()
    if user is not None:
        _ensure_shop_connection(db, user)
        return user

    user = User(
        email=GUEST_EMAIL,
        username=GUEST_USERNAME,
        # Random and never stored anywhere: the account can't be used with password login.
        hashed_password=hash_password(uuid.uuid4().hex),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Another request created it at the same moment; that request sets it up.
        db.rollback()
        return db.query(User).filter(User.email == GUEST_EMAIL).one()
    db.refresh(user)

    conn = _ensure_shop_connection(db, user)
    db.add(KnowledgeBase(name="Shop Catalog & Orders", tables=SHOP_TABLES, connection_id=conn.id))
    db.commit()
    return user


def _ensure_shop_connection(db: Session, user: User) -> DBConnection:
    """The guest's connection to the shop database, created if missing and
    kept in line with the GUEST_DB_* settings."""
    settings = get_settings()
    target = {
        "host": settings.GUEST_DB_HOST,
        "port": settings.GUEST_DB_PORT,
        "db_name": settings.GUEST_DB_NAME,
        "username": settings.GUEST_DB_USER,
    }
    conn = (
        db.query(DBConnection)
        .filter(DBConnection.user_id == user.id)
        .order_by(DBConnection.id)
        .first()
    )
    if conn is None:
        conn = DBConnection(
            user_id=user.id,
            name="Shop Database",
            encrypted_password=encrypt_value(settings.GUEST_DB_PASSWORD),
            **target,
        )
        db.add(conn)
        db.commit()
        db.refresh(conn)
        schedule_refresh(conn.id)
        return conn

    changed = any(getattr(conn, k) != v for k, v in target.items())
    try:
        password_changed = decrypt_value(conn.encrypted_password) != settings.GUEST_DB_PASSWORD
    except Exception:       # e.g. ENCRYPTION_KEY was rotated
        password_changed = True
    if changed or password_changed:
        for k, v in target.items():
            setattr(conn, k, v)
        conn.encrypted_password = encrypt_value(settings.GUEST_DB_PASSWORD)
        db.commit()
        remove_engine(conn.id)
        if changed:
            schedule_refresh(conn.id, force=True)
    return conn

