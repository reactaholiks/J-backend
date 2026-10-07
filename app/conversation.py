"""The WhatsApp order flow, as a per-phone state machine.

Every inbound message runs through `handle()`, which reads the caller's current
state, updates the cart/order, persists it, and sends the next WhatsApp reply.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from . import auth, catalog, interakt, phonepe
from .config import settings
from .models import (
    STATE_AWAITING_ADDRESS,
    STATE_AWAITING_PAYMENT,
    STATE_AWAITING_QTY,
    STATE_CART_REVIEW,
    STATE_IDLE,
    Conversation,
    Order,
)

# Product ref embedded by the storefront deep links, with an optional quantity:
#   single-item  →  "Ref: #kanchi-red-01"
#   cart line    →  "... #kanchi-red-01 x2"
_TOKEN_RE = re.compile(r"#([a-z0-9][a-z0-9-]{1,80})(?:\s*[x×]\s*(\d+))?", re.IGNORECASE)
_LOGIN_RE = re.compile(r"\blogin[-\s]?([a-z0-9]{4,10})\b", re.IGNORECASE)
_PAY_WORDS = {"pay", "checkout", "confirm", "order", "buy"}


def _parse_tokens(text: str) -> list[tuple[str, int | None]]:
    """Extract (slug, quantity) pairs; quantity is None when not specified."""
    out: list[tuple[str, int | None]] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        qty = int(m.group(2)) if m.group(2) else None
        out.append((m.group(1), qty))
    return out


def _rupees(paise: int) -> str:
    return f"₹{paise // 100:,}"


def _cart_total_paise(cart: list[dict]) -> int:
    return sum(int(i["price"]) * int(i["quantity"]) * 100 for i in cart)


def _cart_summary(cart: list[dict]) -> str:
    lines = [f"• {i['name']} × {i['quantity']} — ₹{int(i['price']) * int(i['quantity']):,}" for i in cart]
    lines.append(f"\n*Total: {_rupees(_cart_total_paise(cart))}*")
    return "\n".join(lines)


def _get_convo(db: Session, phone: str) -> Conversation:
    convo = db.get(Conversation, phone)
    if convo is None:
        convo = Conversation(phone=phone, state=STATE_IDLE, cart=[])
        db.add(convo)
    return convo


async def handle(db: Session, phone: str, text: str) -> None:
    convo = _get_convo(db, phone)
    text = text.strip()

    # Website login: "LOGIN <code>" sent from the verified WhatsApp number.
    login = _LOGIN_RE.search(text)
    if login:
        ok = auth.try_verify_login(db, login.group(1), phone)
        await interakt.send_text(
            phone,
            "✅ You're logged in on the website — you can switch back to your browser."
            if ok else
            "That login link has expired. Please tap *Login with WhatsApp* on the site again.",
        )
        db.commit()
        return

    # Product refs always start (or extend) an order, whatever the state.
    tokens = _parse_tokens(text)
    if tokens:
        # A cart link (multiple items, or an explicit quantity) skips the
        # per-item question; a lone ref with no quantity asks "how many?".
        if len(tokens) > 1 or tokens[0][1] is not None:
            await _start_cart(db, convo, tokens)
        else:
            await _start_item(db, convo, tokens[0][0])
        db.commit()
        return

    if convo.state == STATE_AWAITING_QTY:
        await _handle_qty(db, convo, text)
    elif convo.state == STATE_CART_REVIEW:
        await _handle_review(db, convo, text)
    elif convo.state == STATE_AWAITING_ADDRESS:
        await _handle_address(db, convo, text)
    elif convo.state == STATE_AWAITING_PAYMENT:
        await interakt.send_text(phone, "We're still waiting for your payment to complete. "
                                        "Open the PhonePe link we sent, or reply *pay* to get it again.")
    else:
        await _welcome(phone)

    db.commit()


async def _welcome(phone: str) -> None:
    await interakt.send_text(
        phone,
        "🙏 Welcome to *Laxmi Saree House*!\n\n"
        "Browse our collection and tap *Order on WhatsApp* on any product to start. "
        "I'll help you with quantity, address and a secure PhonePe payment link.",
    )


async def _start_item(db: Session, convo: Conversation, slug: str) -> None:
    product = await catalog.get_product(slug)
    if not product:
        await interakt.send_text(
            convo.phone,
            "Sorry, I couldn't find that product. Please tap *Order on WhatsApp* "
            "again from our website.",
        )
        return
    convo.pending_slug = slug
    convo.state = STATE_AWAITING_QTY
    await interakt.send_text(
        convo.phone,
        f"*{product['name']}* — ₹{int(product['price']):,}\n\n"
        "How many would you like? Reply with a number (e.g. *1*).",
    )


async def _start_cart(db: Session, convo: Conversation, tokens: list[tuple[str, int | None]]) -> None:
    """Rebuild a full cart from a storefront cart link, then jump to checkout."""
    cart: list[dict] = []
    for slug, qty in tokens:
        product = await catalog.get_product(slug)
        if not product:
            continue
        cart.append({
            "slug": product["slug"],
            "name": product["name"],
            "price": int(product["price"]),
            "quantity": max(1, qty or 1),
        })
    if not cart:
        await interakt.send_text(
            convo.phone,
            "Sorry, I couldn't find those products. Please tap *Order on WhatsApp* "
            "again from our website.",
        )
        return
    convo.cart = cart
    convo.pending_slug = None
    convo.state = STATE_CART_REVIEW
    await interakt.send_text(
        convo.phone,
        "🛒 *Your cart*\n" + _cart_summary(cart) +
        "\n\nReply *pay* to checkout, or tap another product to add more.",
    )


async def _handle_qty(db: Session, convo: Conversation, text: str) -> None:
    match = re.search(r"\d+", text)
    if not match or not convo.pending_slug:
        await interakt.send_text(convo.phone, "Please reply with a quantity as a number, e.g. *2*.")
        return
    qty = max(1, int(match.group()))
    product = await catalog.get_product(convo.pending_slug)
    if not product:
        convo.state = STATE_IDLE
        convo.pending_slug = None
        await interakt.send_text(convo.phone, "That product is no longer available. Please pick another.")
        return

    cart = list(convo.cart or [])
    cart.append({
        "slug": product["slug"],
        "name": product["name"],
        "price": int(product["price"]),
        "quantity": qty,
    })
    convo.cart = cart
    convo.pending_slug = None
    convo.state = STATE_CART_REVIEW
    await interakt.send_text(
        convo.phone,
        "🛒 *Your cart*\n" + _cart_summary(cart) +
        "\n\nReply *pay* to checkout, or tap another product to add more.",
    )


async def _handle_review(db: Session, convo: Conversation, text: str) -> None:
    if any(w in text.lower() for w in _PAY_WORDS):
        convo.state = STATE_AWAITING_ADDRESS
        await interakt.send_text(
            convo.phone,
            "Great! Please send your *delivery address* in one message:\n"
            "Name, full address, city, and 6-digit pincode.",
        )
    else:
        await interakt.send_text(
            convo.phone,
            "Reply *pay* to checkout, or tap another product on our website to add more.",
        )


async def _handle_address(db: Session, convo: Conversation, text: str) -> None:
    if len(text) < 10:
        await interakt.send_text(convo.phone, "That address looks too short. Please send name, "
                                              "full address, city and pincode in one message.")
        return
    convo.address = {"raw": text}

    cart = list(convo.cart or [])
    amount_paise = _cart_total_paise(cart)
    order_id = f"LX{uuid.uuid4().hex[:20]}".upper()

    order = Order(
        id=order_id, phone=convo.phone, items=cart, address=convo.address,
        amount_paise=amount_paise, status="created",
    )
    db.add(order)
    convo.active_order_id = order_id

    pay_url = await phonepe.create_payment(
        merchant_txn_id=order_id, amount_paise=amount_paise, phone_digits=convo.phone
    )
    if not pay_url:
        await interakt.send_text(convo.phone, "⚠️ We couldn't start the payment just now. "
                                              "Please try again in a moment by replying *pay*.")
        convo.state = STATE_CART_REVIEW
        return

    convo.state = STATE_AWAITING_PAYMENT
    await interakt.send_text(
        convo.phone,
        f"✅ Order *{order_id}* created for {_rupees(amount_paise)}.\n\n"
        f"Pay securely with PhonePe here:\n{pay_url}\n\n"
        "You'll get a confirmation here as soon as the payment succeeds. 🙏",
    )


async def mark_paid(db: Session, order_id: str) -> None:
    """Called from the PhonePe webhook once payment is confirmed."""
    order = db.get(Order, order_id)
    if not order or order.status == "paid":
        return
    order.status = "paid"

    convo = db.get(Conversation, order.phone)
    if convo:
        convo.state = STATE_IDLE
        convo.cart = []
        convo.active_order_id = None
    db.commit()

    await interakt.send_text(
        order.phone,
        f"🎉 Payment received! Your order *{order_id}* is confirmed.\n\n"
        "We'll pack it with love and share tracking details shortly. "
        "Thank you for shopping with Laxmi Saree House! 🌸",
    )
