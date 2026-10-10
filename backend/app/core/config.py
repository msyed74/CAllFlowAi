from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Application & Server
    APP_ENV: str = "development"
    APP_NAME: str = "CallFlow AI"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Security & Tokens
    JWT_SECRET: str = "cf_dev_secret_0123456789abcdef0123456789abcdef0123456789abcdef01234567"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_MASTER_KEY: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

    DATABASE_URL: str = "postgresql+asyncpg://callflow_user:callflow_pass@localhost:5432/callflow_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if not v:
            return v
        v = v.strip()
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis Cache & Realtime State
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 50

    # OpenAI Voice & Realtime API
    OPENAI_API_KEY: str = "sk-placeholder-key-for-dev"
    OPENAI_REALTIME_MODEL: str = "gpt-4o-realtime-preview-2024-10-01"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_SUMMARY_MODEL: str = "gpt-4o-mini"
    OPENAI_DEFAULT_VOICE: str = "alloy"

    # Twilio Telephony & Media Streams
    TWILIO_ACCOUNT_SID: str = "ACplaceholder0000000000000000000000"
    TWILIO_AUTH_TOKEN: str = "placeholder_twilio_auth_token"
    TWILIO_DEFAULT_PHONE_NUMBER: str = "+18005550199"
    TWILIO_MEDIA_STREAM_WS_URL: str = "wss://localhost:8000/ws/media-stream"

    # Qdrant Vector Engine
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "callflow_knowledge_base"

    # Object Storage (S3 / MinIO)
    S3_ENDPOINT_URL: Optional[str] = "http://localhost:9000"
    S3_REGION_NAME: str = "us-east-1"
    S3_BUCKET_NAME: str = "callflow-recordings"
    AWS_ACCESS_KEY_ID: str = "minioadmin"
    AWS_SECRET_ACCESS_KEY: str = "minioadmin"

    # Automation (n8n)
    N8N_WEBHOOK_BASE_URL: str = "http://localhost:5678/webhook"
    N8N_API_KEY: str = "callflow_n8n_secret_token"

    # Diagnostics & Logging
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
