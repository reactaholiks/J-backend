"""Receives inbound WhatsApp messages from Interakt and drives the order flow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from .. import conversation, interakt
from ..config import settings
from ..db import get_session

router = APIRouter(prefix="/webhooks", tags=["interakt"])


@router.post("/interakt")
async def interakt_webhook(
    request: Request,
    db: Session = Depends(get_session),
    x_interakt_secret: str | None = Header(default=None),
) -> dict:
    # Optional shared-secret check (set the same value in the Interakt dashboard).
    if settings.interakt_webhook_secret and x_interakt_secret != settings.interakt_webhook_secret:
        return {"status": "unauthorized"}

    body = await request.json()
    msg = interakt.parse_incoming(body)
    if msg is None:
        return {"status": "ignored"}  # delivery receipts, non-text events, etc.

    await conversation.handle(db, msg.phone, msg.text)
    return {"status": "ok"}
