from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    debug: bool = False

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # Seals admin-managed secrets stored in app_settings. Falls back to jwt_secret when unset, so
    # rotating jwt_secret without setting this also orphans those stored secrets.
    settings_encryption_key: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # The first administrator, created at startup when both are set. There is no default:
    # a credential shipped in source is a credential every deployment shares.
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = ""

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_image_model: str = "gpt-image-1"

    gemini_api_key: str = ""
    gemini_chat_model: str = "gemini-2.0-flash"
    gemini_image_model: str = "gemini-2.5-flash-image"

    payment_provider: str = "razorpay"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Default shape for generated images. Overridable at runtime from the admin Settings screen.
    image_aspect: str = "portrait"

    storage_path: str = "./storage"
    max_upload_mb: int = 10
    max_image_dimension: int = 4096
    allowed_upload_extensions: str = "jpg,jpeg,png,webp"

    email_backend: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@sumitgroups.com"

    sentry_dsn: str = ""
    log_level: str = "INFO"

    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    auth_rate_limit_per_minute: int = 10

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
