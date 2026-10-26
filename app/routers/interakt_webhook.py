"""Receives inbound WhatsApp messages from Interakt and drives the order flow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import conversation, interakt
from ..config import settings
from ..db import get_session
from ..models import WebhookEvent

router = APIRouter(prefix="/webhooks", tags=["interakt"])


@router.post("/interakt")
async def interakt_webhook(
    request: Request,
    db: Session = Depends(get_session),
    x_interakt_secret: str | None = Header(default=None),
) -> dict:
    # Shared-secret check (set the same value in the Interakt dashboard). Must
    # be configured in production — without it anyone who finds this URL can
    # forge "message received" events and bypass the WhatsApp verification
    # entirely. Treated as a hard failure, not a soft "unauthorized" 200, so
    # misconfiguration is visible rather than silently accepted.
    if not settings.interakt_webhook_secret or x_interakt_secret != settings.interakt_webhook_secret:
        return {"status": "unauthorized"}

    body = await request.json()

    # Interakt retries webhook deliveries on timeout/non-2xx — dedupe by event
    # id so a retry can't double-process (e.g. re-sending a reply, re-running
    # order logic).
    event_id = str(body.get("id") or body.get("data", {}).get("id") or "")
    if event_id:
        try:
            db.add(WebhookEvent(id=event_id))
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"status": "duplicate"}

    msg = interakt.parse_incoming(body)
    if msg is None:
        return {"status": "ignored"}  # delivery receipts, non-text events, etc.

    await conversation.handle(db, msg.phone, msg.text)
    return {"status": "ok"}
