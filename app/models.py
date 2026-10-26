"""Persistence: one conversation per phone number, plus placed orders."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Conversation states — the WhatsApp order flow, one step at a time.
STATE_IDLE = "idle"                # nothing pending
STATE_AWAITING_QTY = "awaiting_qty"        # product picked, waiting for a number
STATE_CART_REVIEW = "cart_review"          # summary shown, add-more / checkout
STATE_AWAITING_ADDRESS = "awaiting_address"  # collecting delivery details
STATE_AWAITING_PAYMENT = "awaiting_payment"  # pay link sent, waiting on PhonePe


class Conversation(Base):
    __tablename__ = "conversations"

    phone: Mapped[str] = mapped_column(String, primary_key=True)  # digits, e.g. 919999999999
    state: Mapped[str] = mapped_column(String, default=STATE_IDLE)
    # cart: list of {slug, name, price, quantity}
    cart: Mapped[list] = mapped_column(JSON, default=list)
    # pending product slug while we wait for a quantity reply
    pending_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    active_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Customer(Base):
    """A person, identified by their WhatsApp-verified phone number.

    First time we see a verified number = signup; every later login just bumps
    last_login_at. No password is ever stored — WhatsApp proves the number.
    """
    __tablename__ = "customers"

    phone: Mapped[str] = mapped_column(String, primary_key=True)  # digits incl. country code
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Default delivery address, captured at signup and reusable for future orders.
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    pincode: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginCode(Base):
    """A one-time code tying a browser session to a phone, verified over WhatsApp.

    `expected_phone` is the number the user typed into the website *before* the
    QR/link was generated. The webhook only marks the code verified if the
    WhatsApp sender matches it — this stops an unrelated/incorrect number from
    silently claiming the session. `claimed` makes the code single-use even
    after verification, so it can't be replayed as a standing credential.
    """
    __tablename__ = "login_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    expected_phone: Mapped[str] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)  # set once verified
    verified: Mapped[bool] = mapped_column(default=False)
    mismatch: Mapped[bool] = mapped_column(default=False)
    claimed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Session(Base):
    """An opaque, server-issued login session — the real auth boundary for the
    browser after a login code is claimed. The code itself is never reused as
    a credential past that one claim."""
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    phone: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base):
    """Dedupe table for inbound Interakt webhook deliveries (at-least-once retries)."""
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # merchant txn id (LX-...)
    phone: Mapped[str] = mapped_column(String, index=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    amount_paise: Mapped[int] = mapped_column(Integer)  # PhonePe works in paise
    status: Mapped[str] = mapped_column(String, default="created")  # created|paid|failed
    phonepe_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
