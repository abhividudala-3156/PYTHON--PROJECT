from __future__ import annotations

import smtplib
import ssl
from email.mime.text import MIMEText

from .config import Config


def send_otp_email(to_email: str, otp: str, account_type: str, public_id: str) -> tuple[bool, str]:
    if not Config.SMTP_HOST or not Config.SMTP_USER or not Config.SMTP_PASSWORD:
        if Config.APP_ENV == "production":
            raise RuntimeError("SMTP is not configured. Configure SMTP settings before production OTP delivery.")
        return False, f"Development OTP for {public_id}: {otp}"

    body = (
        f"Your {Config.APP_NAME} OTP is {otp}.\n"
        f"Account type: {account_type}\n"
        f"ID: {public_id}\n"
        "This OTP is valid for 10 minutes. Ignore this email if you did not request it."
    )
    msg = MIMEText(body)
    msg["Subject"] = f"{Config.APP_NAME} OTP Verification"
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to_email

    context = ssl.create_default_context()
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as server:
        if Config.SMTP_USE_TLS:
            server.starttls(context=context)
        server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.send_message(msg)
    return True, "OTP sent to registered email."
