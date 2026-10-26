"""Browser-facing endpoints for WhatsApp login."""
from __future__ import annotations

import time
import urllib.parse
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth
from ..config import settings
from ..db import get_session

router = APIRouter(prefix="/auth/wa", tags=["auth"])

# Per-IP rolling-hour counter for code generation. In-memory: resets on deploy
# and isn't shared across multiple worker processes — good enough as a first
# line of defense against a single abusive client; put a real rate limiter
# (Redis/API-gateway) in front before scaling out horizontally.
_attempts: dict[str, list[float]] = defaultdict(list)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    window = _attempts[ip] = [t for t in _attempts[ip] if now - t < 3600]
    if len(window) >= settings.login_start_rate_limit_per_hour:
        return True
    window.append(now)
    return False


class StartIn(BaseModel):
    phone: str


class ProfileIn(BaseModel):
    name: str
    address: str | None = None
    city: str | None = None
    pincode: str | None = None


class ClaimIn(BaseModel):
    code: str


def _cookie_kwargs() -> dict:
    return dict(
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )


def _session_token(request: Request) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


@router.post("/start")
def start(body: StartIn, request: Request, db: Session = Depends(get_session)) -> dict:
    """Mint a code bound to the phone the browser declared, and return the
    WhatsApp deep link / QR payload the browser should present."""
    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    phone = auth.normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit mobile number.")

    row = auth.create_login_code(db, phone)
    message = f"Verify:{settings.brand_name}:{row.code}"

    if settings.dev_auth_bypass:
        # No Interakt yet: the QR/link opens a backend confirm page that verifies
        # the code (simulating the inbound WhatsApp message). Scan it from a phone
        # or tap it on the same device — the browser's existing poll then logs in.
        wa_url = f"{settings.public_base_url}/auth/wa/dev/confirm?code={row.code}"
    else:
        number = "".join(ch for ch in settings.whatsapp_business_number if ch.isdigit())
        wa_url = f"https://wa.me/{number}?text={urllib.parse.quote(message)}"

    return {
        "code": row.code,
        "wa_url": wa_url,
        "message": message,
        "expires_in": settings.login_code_ttl_seconds,
        "dev_mode": settings.dev_auth_bypass,
    }


@router.get("/dev/confirm", response_class=HTMLResponse)
def dev_confirm(code: str, db: Session = Depends(get_session)) -> str:
    """DEV ONLY: stand-in for the Interakt webhook. Verifies the code for the
    number the browser declared, so the rest of the flow (poll → claim → session
    cookie) runs unchanged. Returns 404 unless DEV_AUTH_BYPASS is on, so it can
    never be hit in production."""
    if not settings.dev_auth_bypass:
        raise HTTPException(status_code=404, detail="Not found")

    result = auth.dev_verify(db, code)
    headings = {
        "ok": ("✅ Number confirmed", "Switch back to your browser — you're being logged in."),
        "already_used": ("Already used", "This login was already completed. Start a new one on the site."),
        "expired": ("Code expired", "Please start the login again on the website."),
        "unknown": ("Invalid code", "Please start the login again on the website."),
        "mismatch": ("Number mismatch", "The number doesn't match. Start login again on the site."),
    }
    title, sub = headings.get(result, ("Done", ""))
    return (
        "<html><body style='font-family:system-ui,sans-serif;text-align:center;padding:56px 24px;color:#2a2320'>"
        f"<h2 style='margin:0 0 8px'>{title}</h2><p style='color:#6a5e52'>{sub}</p>"
        "<p style='margin-top:28px;font-size:13px;color:#9b8f80'>Dev mode — WhatsApp verification is simulated. "
        "You can close this tab.</p></body></html>"
    )


@router.get("/status")
def status(code: str, db: Session = Depends(get_session)) -> dict:
    """The browser polls this until status becomes 'verified'. No phone/name
    is ever returned here — see POST /claim, which consumes the code once."""
    return auth.login_status(db, code)


@router.post("/claim")
def claim(body: ClaimIn, response: Response, db: Session = Depends(get_session)) -> dict:
    """Consume a verified code exactly once and set the session cookie."""
    result = auth.claim_session(db, body.code)
    if result is None:
        raise HTTPException(status_code=400, detail="Login code is not verified or already used.")
    response.set_cookie(settings.session_cookie_name, result["token"], **_cookie_kwargs())
    return {
        "phone": result["phone"],
        "name": result["name"],
        "profile_complete": result["profile_complete"],
    }


@router.get("/me")
def me(request: Request, db: Session = Depends(get_session)) -> dict:
    # The logged-in customer is identified by the session cookie — never by a
    # phone number supplied by the browser. That keeps this a "read my own
    # profile" call and prevents anyone from reading another customer's saved
    # address by guessing numbers. Returns the fields the checkout form prefills.
    cust = auth.get_customer_by_token(db, _session_token(request))
    if cust is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return {
        "phone": cust.phone,
        "name": cust.name,
        "email": cust.email,
        "address": cust.address,
        "city": cust.city,
        "pincode": cust.pincode,
        "profile_complete": bool(cust.name),
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_session)) -> dict:
    auth.logout(db, _session_token(request))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "ok"}


@router.post("/profile")
def profile(body: ProfileIn, request: Request, db: Session = Depends(get_session)) -> dict:
    """Save name + default delivery address for the logged-in session."""
    result = auth.save_profile(
        db, _session_token(request), body.name, body.address, body.city, body.pincode
    )
    if result is None:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return result
