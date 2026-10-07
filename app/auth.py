"""WhatsApp-based login: free phone verification, no SMS/OTP provider.

The browser requests a one-time code and opens WhatsApp with it pre-filled. When
the customer sends it, Interakt's webhook hands us a number WhatsApp has already
verified — so matching the code is all the proof we need.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Customer, LoginCode

CODE_TTL = timedelta(minutes=5)


def create_login_code(db: Session) -> str:
    """Mint a fresh pending code and persist it."""
    code = secrets.token_hex(3).upper()  # 6 hex chars, e.g. "A1B2C3"
    db.add(LoginCode(code=code))
    db.commit()
    return code


def _aware(dt: datetime) -> datetime:
    """SQLite can hand back naive datetimes — treat those as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def upsert_customer(db: Session, phone: str, name: str | None = None) -> Customer:
    """Create the customer on first sight (signup) or bump last_login_at."""
    now = datetime.now(timezone.utc)
    cust = db.get(Customer, phone)
    if cust is None:
        cust = Customer(phone=phone, name=name, last_login_at=now)
        db.add(cust)
    else:
        cust.last_login_at = now
        if name and not cust.name:
            cust.name = name
    return cust


def try_verify_login(db: Session, code: str, phone: str) -> bool:
    """Called from the WhatsApp webhook. Returns True if the code was valid."""
    row = db.get(LoginCode, code.upper())
    if row is None or row.verified:
        return False
    if datetime.now(timezone.utc) - _aware(row.created_at) > CODE_TTL:
        return False
    row.verified = True
    row.phone = phone
    upsert_customer(db, phone)
    db.commit()
    return True


def login_status(db: Session, code: str) -> dict:
    """Polled by the browser until the code flips to verified."""
    row = db.get(LoginCode, code.upper())
    if row is None:
        return {"status": "unknown"}
    if row.verified and row.phone:
        cust = db.get(Customer, row.phone)
        return {"status": "verified", "phone": row.phone, "name": cust.name if cust else None}
    return {"status": "pending"}
