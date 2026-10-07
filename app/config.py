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

    interakt_api_key: str = ""
    interakt_base_url: str = "https://api.interakt.ai/v1/public"
    interakt_webhook_secret: str = ""

    sanity_project_id: str = ""
    sanity_dataset: str = "production"
    sanity_api_version: str = "2026-06-01"
    sanity_api_read_token: str = ""

    phonepe_base_url: str = "https://api-preprod.phonepe.com/apis/pg-sandbox"
    phonepe_merchant_id: str = "PGTESTPAYUAT"
    phonepe_salt_key: str = ""
    phonepe_salt_index: str = "1"


settings = Settings()
