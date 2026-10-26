"""WhatsApp-based login: free phone verification, no SMS/OTP provider.

The browser collects the number the user claims to own, mints a one-time code
bound to that number, and shows a QR / WhatsApp deep link with the code
pre-filled. When the customer sends it, Interakt's webhook hands us the
sending number WhatsApp has already verified. We only treat the login as
successful if that sender matches the number the browser declared — this
closes the "wrong number" / opportunistic-match gap, independent of the code
match itself.

Once verified, the code is claimed exactly once to mint a server-side
`Session` (opaque token, set as an httpOnly cookie). The code is never valid
as a standing credential after that — it's a one-time handshake, not a
session token.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session as DbSession

from .config import settings
from .models import Customer, LoginCode
from .models import Session as SessionRow

CODE_TTL = timedelta(seconds=settings.login_code_ttl_seconds)
SESSION_TTL = timedelta(days=settings.session_ttl_days)

_PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile, 10 digits, no leading 0/country code

VerifyResult = Literal["ok", "mismatch", "expired", "unknown", "already_used"]


def normalize_phone(raw: str) -> str | None:
    """Validate a user-entered mobile number and return it as '91XXXXXXXXXX', or None."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not _PHONE_RE.match(digits):
        return None
    return f"91{digits}"


def _aware(dt: datetime) -> datetime:
    """SQLite can hand back naive datetimes — treat those as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_expired(row: LoginCode) -> bool:
    return datetime.now(timezone.utc) - _aware(row.created_at) > CODE_TTL


def create_login_code(db: DbSession, expected_phone: str) -> LoginCode:
    """Mint a fresh pending code bound to the number the browser declared."""
    code = secrets.token_hex(4).upper()  # 8 hex chars — resists guessing within the TTL window
    row = LoginCode(code=code, expected_phone=expected_phone)
    db.add(row)
    db.commit()
    return row


def upsert_customer(db: DbSession, phone: str, name: str | None = None) -> Customer:
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


def try_verify_login(db: DbSession, code: str, sender_phone: str) -> VerifyResult:
    """Called from the WhatsApp webhook. Returns the outcome so the bot can
    reply with the right message (success / wrong number / expired)."""
    row = db.get(LoginCode, code.upper())
    if row is None:
        return "unknown"
    if row.claimed:
        return "already_used"
    if _is_expired(row):
        return "expired"
    if row.verified:
        # Webhook retry delivering the same event again — idempotent no-op.
        return "ok" if row.phone == sender_phone else "mismatch"
    if sender_phone != row.expected_phone:
        row.mismatch = True
        db.commit()
        return "mismatch"

    row.verified = True
    row.phone = sender_phone
    upsert_customer(db, sender_phone)
    db.commit()
    return "ok"


def dev_verify(db: DbSession, code: str) -> VerifyResult:
    """DEV ONLY: mark a code verified as if its expected number had confirmed over
    WhatsApp. Routes through the exact same `try_verify_login` the Interakt webhook
    calls — so there is no second, less-tested verification path. Gated by
    `settings.dev_auth_bypass` at the router; never reachable in production."""
    row = db.get(LoginCode, code.upper())
    if row is None:
        return "unknown"
    return try_verify_login(db, code, row.expected_phone)


def login_status(db: DbSession, code: str) -> dict:
    """Polled by the browser. Deliberately returns no PII — the phone/name are
    only handed over once the code is claimed (see claim_session), so a code
    leaked via logs/referrers before that point can't be used to read anyone's
    details."""
    row = db.get(LoginCode, code.upper())
    if row is None:
        return {"status": "unknown"}
    if row.claimed:
        return {"status": "already_used"}
    if row.mismatch and not row.verified:
        return {"status": "mismatch"}
    if row.verified:
        return {"status": "verified"}
    if _is_expired(row):
        return {"status": "expired"}
    return {"status": "pending"}


def claim_session(db: DbSession, code: str) -> dict | None:
    """Consume a verified code exactly once and mint a session cookie token."""
    row = db.get(LoginCode, code.upper())
    if row is None or not row.verified or row.claimed or _is_expired(row):
        return None
    row.claimed = True

    cust = db.get(Customer, row.phone)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(SessionRow(token=token, phone=row.phone, created_at=now, expires_at=now + SESSION_TTL))
    db.commit()

    return {
        "token": token,
        "phone": row.phone,
        "name": cust.name if cust else None,
        "profile_complete": bool(cust and cust.name),
    }


def get_customer_by_token(db: DbSession, token: str | None) -> Customer | None:
    if not token:
        return None
    sess = db.get(SessionRow, token)
    if sess is None or _aware(sess.expires_at) < datetime.now(timezone.utc):
        return None
    return db.get(Customer, sess.phone)


def logout(db: DbSession, token: str | None) -> None:
    if not token:
        return
    sess = db.get(SessionRow, token)
    if sess is not None:
        db.delete(sess)
        db.commit()


def save_profile(
    db: DbSession,
    token: str | None,
    name: str,
    address: str | None,
    city: str | None,
    pincode: str | None,
) -> dict | None:
    """Save the profile + default delivery address. Authorized by the session
    cookie (not a raw code), so a caller can only edit the number tied to their
    own logged-in session."""
    cust = get_customer_by_token(db, token)
    if cust is None:
        return None
    cust.name = name
    cust.address = address
    cust.city = city
    cust.pincode = pincode
    db.commit()
    return {"phone": cust.phone, "name": cust.name}
