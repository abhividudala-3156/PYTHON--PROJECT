from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable, Any

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .config import Config

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
PHONE_RE = re.compile(r"^[0-9]{10,15}$")
PUBLIC_ID_RE = re.compile(r"^[A-Z0-9]{6,20}$")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_PROOF_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf"}


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def normalize_phone(value: str) -> str:
    phone = re.sub(r"\D+", "", value or "")
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("Phone number must contain 10 to 15 digits.")
    return phone


def normalize_public_id(value: str) -> str:
    public_id = re.sub(r"\s+", "", value or "").upper()
    if not PUBLIC_ID_RE.fullmatch(public_id):
        raise ValueError("Invalid ID format.")
    return public_id


def validate_password(password: str) -> None:
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password) or not re.search(r"\d", password):
        raise ValueError("Password must include uppercase, lowercase, and a number.")


def hash_password(password: str) -> str:
    validate_password(password)
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)


def verify_password(password: str, stored_hash: str) -> bool:
    return check_password_hash(stored_hash or "", password or "")


def generate_public_id(prefix: str) -> str:
    return f"{prefix}{secrets.randbelow(900000) + 100000}"


def generate_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def hash_otp(otp: str) -> str:
    secret = Config.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, otp.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(raw_otp: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(raw_otp.strip()), stored_hash or "")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def otp_expiry(minutes: int = 10) -> datetime:
    return utc_now() + timedelta(minutes=minutes)


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        sent = request.form.get("csrf_token", "")
        if not sent and request.is_json:
            payload = request.get_json(silent=True) or {}
            sent = str(payload.get("csrf_token", ""))
        if not sent:
            sent = request.headers.get("X-CSRFToken", "") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="Invalid CSRF token")


def current_user() -> dict[str, Any] | None:
    auth = session.get("auth")
    return auth if isinstance(auth, dict) else None


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles: str):
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any):
            user = current_user()
            if not user or user.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def allowed_file(filename: str, allowed: set[str]) -> bool:
    return bool(filename and "." in filename and filename.rsplit(".", 1)[-1].lower() in allowed)


def encryption_key() -> bytes:
    configured = Config.FILE_ENCRYPTION_KEY.strip()
    if configured:
        return configured.encode("utf-8")
    seed = f"{Config.SECRET_KEY}|{Config.DATABASE_URL}".encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def encrypt_bytes(payload: bytes) -> bytes:
    return Fernet(encryption_key()).encrypt(payload)


def decrypt_bytes(payload: bytes) -> bytes:
    try:
        return Fernet(encryption_key()).decrypt(payload)
    except InvalidToken as exc:
        raise ValueError("Could not decrypt the stored proof file. Check FILE_ENCRYPTION_KEY.") from exc


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return email or ""
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(1, len(local) - len(visible))}@{domain}"


def mask_phone(phone: str | None) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    return "*" * max(0, len(digits) - 4) + digits[-4:]


def make_vote_receipt(voter_public_id: str, candidate_db_id: int) -> str:
    raw = f"{voter_public_id}|{candidate_db_id}|{secrets.token_urlsafe(16)}|{utc_now().isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
