from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    APP_NAME = os.getenv("APP_NAME", "SecureVote")
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret-key")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/secure_voting")
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "app" / "uploads"))
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024

    ADMIN_ID = os.getenv("ADMIN_ID", "ADMIN001")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@vote.local")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrator")

    FILE_ENCRYPTION_KEY = os.getenv("FILE_ENCRYPTION_KEY", "")

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@vote.local")
    SMTP_USE_TLS = _bool_env("SMTP_USE_TLS", True)

    # Generic SMS gateway support. In development, missing SMS config shows mobile OTP on screen.
    SMS_API_URL = os.getenv("SMS_API_URL", "")
    SMS_API_TOKEN = os.getenv("SMS_API_TOKEN", "")
    SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "SecureVote")

    # OpenRouter assistant. Keep API key only in .env; never expose it to the browser.
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://127.0.0.1:5000")
    OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", APP_NAME)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 2

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
