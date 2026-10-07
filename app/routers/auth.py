"""Browser-facing endpoints for WhatsApp login."""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import auth
from ..config import settings
from ..db import get_session

router = APIRouter(prefix="/auth/wa", tags=["auth"])


@router.post("/start")
def start(db: Session = Depends(get_session)) -> dict:
    """Mint a code and return the WhatsApp deep link the browser should open."""
    code = auth.create_login_code(db)
    number = "".join(ch for ch in settings.whatsapp_business_number if ch.isdigit())
    text = urllib.parse.quote(f"LOGIN {code}")
    return {"code": code, "wa_url": f"https://wa.me/{number}?text={text}"}


@router.get("/status")
def status(code: str, db: Session = Depends(get_session)) -> dict:
    """The browser polls this until status becomes 'verified'."""
    return auth.login_status(db, code)
