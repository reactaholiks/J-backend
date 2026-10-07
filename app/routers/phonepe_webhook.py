"""PhonePe callback + the browser return URL after payment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import conversation, phonepe
from ..db import get_session
from ..models import Order

router = APIRouter(tags=["phonepe"])


@router.post("/webhooks/phonepe")
async def phonepe_callback(
    request: Request,
    db: Session = Depends(get_session),
    x_verify: str | None = Header(default=None),
) -> dict:
    body = await request.json()
    encoded = body.get("response", "")
    decoded = phonepe.verify_callback(x_verify or "", encoded)
    if decoded is None:
        return {"status": "invalid-signature"}

    data = decoded.get("data", {})
    order_id = data.get("merchantTransactionId")
    code = decoded.get("code") or data.get("state")
    if order_id and code in {"PAYMENT_SUCCESS", "COMPLETED"}:
        order = db.get(Order, order_id)
        if order:
            order.phonepe_txn_id = data.get("transactionId")
            db.commit()
        await conversation.mark_paid(db, order_id)
    return {"status": "ok"}


@router.get("/pay/return/{order_id}", response_class=HTMLResponse)
async def pay_return(order_id: str, db: Session = Depends(get_session)) -> str:
    """Where PhonePe redirects the customer's browser. We confirm via status API
    (the server-to-server webhook is the source of truth) and show a simple page."""
    code = await phonepe.check_status(order_id)
    if code == "PAYMENT_SUCCESS":
        await conversation.mark_paid(db, order_id)
        msg = "✅ Payment successful! Check WhatsApp for your order confirmation."
    else:
        msg = "Payment is being processed. You'll get a WhatsApp update shortly."
    return (
        "<html><body style='font-family:sans-serif;text-align:center;padding:48px'>"
        f"<h2>{msg}</h2><p>You can close this window and return to WhatsApp.</p>"
        "</body></html>"
    )
