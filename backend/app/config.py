from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    database_url: str = "sqlite:///./locallead.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    frontend_origin: str = "*"

    # Google Places (real lead data + PageSpeed)
    google_places_api_key: str | None = None

    # Stripe (real billing)
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_agency: str | None = None
    # Where Stripe redirects after checkout
    checkout_success_url: str = "http://localhost:8000/?checkout=success"
    checkout_cancel_url: str = "http://localhost:8000/?checkout=cancel"


@lru_cache
def get_settings() -> Settings:
    return Settings()
