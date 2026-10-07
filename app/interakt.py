"""Interakt WhatsApp client + incoming-webhook parsing.

Outbound: because the customer always messages us FIRST (via the wa.me deep
link), every reply falls inside WhatsApp's 24-hour customer-care window, so we
can send free-form *session* text — no pre-approved templates needed for v1.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import settings


@dataclass
class IncomingMessage:
    phone: str          # digits incl. country code, e.g. "919999999999"
    text: str
    event: str


def _split_number(phone_digits: str) -> tuple[str, str]:
    """('919999999999') -> ('+91', '9999999999'). Assumes a 91 (India) prefix."""
    d = "".join(ch for ch in phone_digits if ch.isdigit())
    if d.startswith("91") and len(d) > 10:
        return "+91", d[2:]
    return "+91", d[-10:]


async def send_text(phone_digits: str, text: str) -> None:
    """Send a free-form session WhatsApp message via Interakt.

    # VERIFY: confirm this exact body against your Interakt "Send Message" API
    # docs (Settings → Developer Setup). The endpoint + auth are stable; the
    # session-text payload shape is the one thing to double-check for your plan.
    """
    if not settings.interakt_api_key:
        # Dev without credentials: log instead of failing the whole flow.
        print(f"[interakt:dev] -> {phone_digits}: {text}")
        return

    country_code, number = _split_number(phone_digits)
    payload = {
        "countryCode": country_code,
        "phoneNumber": number,
        "type": "Text",
        "data": {"message": text},
    }
    headers = {
        "Authorization": f"Basic {settings.interakt_api_key}",
        "Content-Type": "application/json",
    }
    # A messaging failure must never crash the webhook (which would make Interakt
    # retry) or abort an order/login that was already saved — log and move on.
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.interakt_base_url}/message/", json=payload, headers=headers
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[interakt] send failed for {phone_digits}: {exc}")


def parse_incoming(body: dict) -> IncomingMessage | None:
    """Extract phone + text from an Interakt webhook payload.

    Interakt nests differently across event versions, so we probe a few known
    shapes defensively and return None for anything that isn't customer text.
    """
    event = body.get("type") or body.get("event") or ""
    data = body.get("data", body) or {}

    customer = data.get("customer", {}) or {}
    phone = (
        customer.get("phone_number")
        or customer.get("channel_phone_number")
        or data.get("phone_number")
        or ""
    )
    country = customer.get("country_code") or ""
    phone_digits = "".join(ch for ch in f"{country}{phone}" if ch.isdigit())

    message = data.get("message", {}) or {}
    text = (
        message.get("message")
        or message.get("text")
        or data.get("message_content")
        or ""
    )

    if not phone_digits or not text:
        return None
    return IncomingMessage(phone=phone_digits, text=str(text).strip(), event=str(event))
