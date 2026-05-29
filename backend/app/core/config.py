"""Application settings."""
from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # App
    APP_NAME: str = "Tchoucti"
    APP_BASE_DOMAIN: str = "localhost"        # ex: tchoucti.com en prod
    PLATFORM_ADMIN_SUBDOMAIN: str = "admin"   # admin.{APP_BASE_DOMAIN}
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://tchoucti_user:tchoucti_dev_password@localhost:15432/tchoucti_db"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:16379/0"

    # S3 / MinIO
    S3_ENDPOINT: str = "http://localhost:19000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET: str = "tchoucti-files"
    S3_REGION: str = "us-east-1"
    S3_PUBLIC_URL: str = "http://localhost:19000"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-CHANGE-IN-PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Regex fallback for per-groupement subdomains ({grp}.${DOMAIN}) which can't
    # be listed exhaustively. e.g. r"https://([a-z0-9-]+\.)?myappsuite\.com"
    CORS_ORIGIN_REGEX: Optional[str] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # SMTP (defaults to Mailpit in docker-compose dev)
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@tchoucti.cm"
    SMTP_FROM_NAME: str = "Tchoucti"
    SMTP_TLS: bool = False

    # Invitations
    INVITATION_EXPIRE_DAYS: int = 7

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
