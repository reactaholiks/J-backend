"""PhonePe Standard Checkout (X-VERIFY / salt-key flow).

We create a hosted payment page and send its URL to the customer over WhatsApp.
PhonePe then calls our callback (and we can also poll status) to confirm.
"""
from __future__ import annotations

import base64
import hashlib
import json

import httpx

from .config import settings

_PAY_PATH = "/pg/v1/pay"


def _checksum(payload_to_sign: str, endpoint: str) -> str:
    """X-VERIFY = sha256(payload + endpoint + saltKey) ### saltIndex."""
    digest = hashlib.sha256(
        (payload_to_sign + endpoint + settings.phonepe_salt_key).encode()
    ).hexdigest()
    return f"{digest}###{settings.phonepe_salt_index}"


async def create_payment(
    *, merchant_txn_id: str, amount_paise: int, phone_digits: str
) -> str | None:
    """Create a payment and return the redirect URL the customer should open."""
    redirect_url = f"{settings.public_base_url}/pay/return/{merchant_txn_id}"
    callback_url = f"{settings.public_base_url}/webhooks/phonepe"

    body = {
        "merchantId": settings.phonepe_merchant_id,
        "merchantTransactionId": merchant_txn_id,
        "merchantUserId": phone_digits,
        "amount": amount_paise,
        "redirectUrl": redirect_url,
        "redirectMode": "REDIRECT",
        "callbackUrl": callback_url,
        "mobileNumber": phone_digits[-10:],
        "paymentInstrument": {"type": "PAY_PAGE"},
    }
    encoded = base64.b64encode(json.dumps(body).encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": _checksum(encoded, _PAY_PATH),
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{settings.phonepe_base_url}{_PAY_PATH}",
            json={"request": encoded},
            headers=headers,
        )
        data = resp.json()

    if not data.get("success"):
        print(f"[phonepe] create_payment failed: {data}")
        return None
    return (
        data.get("data", {})
        .get("instrumentResponse", {})
        .get("redirectInfo", {})
        .get("url")
    )


def verify_callback(x_verify: str, raw_base64_response: str) -> dict | None:
    """Validate a PhonePe callback and return the decoded response, or None."""
    expected = (
        hashlib.sha256((raw_base64_response + settings.phonepe_salt_key).encode()).hexdigest()
        + f"###{settings.phonepe_salt_index}"
    )
    if not x_verify or x_verify.split("###")[0] != expected.split("###")[0]:
        return None
    try:
        return json.loads(base64.b64decode(raw_base64_response).decode())
    except (ValueError, json.JSONDecodeError):
        return None


async def check_status(merchant_txn_id: str) -> str:
    """Poll PhonePe for a transaction's state. Returns PhonePe's `code` string."""
    endpoint = f"/pg/v1/status/{settings.phonepe_merchant_id}/{merchant_txn_id}"
    headers = {
        "Content-Type": "application/json",
        "X-VERIFY": _checksum("", endpoint),
        "X-MERCHANT-ID": settings.phonepe_merchant_id,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{settings.phonepe_base_url}{endpoint}", headers=headers)
        return resp.json().get("code", "UNKNOWN")
