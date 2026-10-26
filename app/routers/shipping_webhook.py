"""Courier aggregator (Shiprocket) tracking webhook.

Shiprocket POSTs a shipment status update here every time a parcel moves. For now
this receiver authenticates the call and logs the payload so you can (a) confirm
the connection with Shiprocket's "Test Webhook" button and (b) see the exact JSON
shape. The full logic — match order by AWB, map status, update it, send the
WhatsApp milestone — is the next step once shipments are being created.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, Request

from ..config import settings

router = APIRouter(tags=["shipping"])


@router.post("/webhooks/shipping")
async def shipping_webhook(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> dict:
    # If a token is configured, require it (the "x-api-key" header you set in the
    # Shiprocket dashboard). Blank token = dev mode: accept so "Test Webhook" works.
    if settings.shipping_webhook_token and x_api_key != settings.shipping_webhook_token:
        return {"status": "unauthorized"}

    try:
        body = await request.json()
    except Exception:
        body = {"raw": (await request.body()).decode(errors="replace")}

    # Shiprocket field names vary by event; probe the common ones for the log.
    awb = body.get("awb") or body.get("awb_code")
    status = body.get("current_status") or body.get("shipment_status") or body.get("status")
    print(f"[shipping] webhook received — awb={awb} status={status}")
    print(f"[shipping] payload: {body}")

    # TODO: find Order by awb → map status → save → send WhatsApp update.
    return {"status": "ok"}
