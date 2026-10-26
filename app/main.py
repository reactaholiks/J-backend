"""FastAPI entrypoint — wires the webhooks and creates tables on startup."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routers import auth, health, interakt_webhook, phonepe_webhook, shipping_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Laxmi Saree House — WhatsApp Orders", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,  # the login session is a cookie — must be explicit, and never "*"
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(interakt_webhook.router)
app.include_router(phonepe_webhook.router)
app.include_router(shipping_webhook.router)
