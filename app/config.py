"""Typed settings loaded from the environment / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./orders.db"
    # Comma-separated storefront origins allowed to call the login API.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    whatsapp_business_number: str = ""

    # Brand text embedded in the WhatsApp verification message, e.g. "Verify:LamiJewellery:A1B2C3".
    brand_name: str = "LamiJewellery"

    interakt_api_key: str = ""
    interakt_base_url: str = "https://api.interakt.ai/v1/public"
    interakt_webhook_secret: str = ""

    # How long a login code stays claimable after creation.
    login_code_ttl_seconds: int = 120
    # Per-IP cap on how many codes can be minted per rolling hour (abuse/brute-force guard).
    login_start_rate_limit_per_hour: int = 12

    # Session cookie set after a verified code is claimed.
    session_cookie_name: str = "lsh_session"
    session_ttl_days: int = 30
    # False only for local http:// dev; must be True in production (https).
    cookie_secure: bool = True

    # DEV ONLY: verify login codes without Interakt/WhatsApp. When True, the
    # login QR/link points at /auth/wa/dev/confirm, which marks the code verified
    # through the SAME path the real Interakt webhook uses — so the whole
    # signup/signin + session flow is exercised end to end with a dummy number.
    # MUST stay False in production; the dev endpoint 404s whenever it is off.
    dev_auth_bypass: bool = False

    sanity_project_id: str = ""
    sanity_dataset: str = "production"
    sanity_api_version: str = "2026-06-01"
    sanity_api_read_token: str = ""

    phonepe_base_url: str = "https://api-preprod.phonepe.com/apis/pg-sandbox"
    phonepe_merchant_id: str = "PGTESTPAYUAT"
    phonepe_salt_key: str = ""
    phonepe_salt_index: str = "1"

    # Courier aggregator (Shiprocket) tracking webhook. The token you paste into
    # the Shiprocket dashboard must equal this; it arrives as the `x-api-key`
    # header. Leave blank in dev to let Shiprocket's "Test Webhook" through.
    shipping_webhook_token: str = ""


settings = Settings()
