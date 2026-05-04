from __future__ import annotations

import re
import requests

from .config import Config
from .security import mask_phone


def clean_indian_phone(phone: str) -> str:
    """
    Fast2SMS expects Indian mobile numbers like 9876543210.
    This removes +91, spaces, hyphens, and other symbols.
    """
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) != 10:
        raise ValueError("Enter a valid 10-digit Indian mobile number.")

    return digits


def send_mobile_otp(phone: str, otp: str, account_type: str, public_id: str) -> tuple[bool, str]:
    """
    Sends mobile OTP using Fast2SMS OTP route.
    Fast2SMS OTP route sends message like: Your OTP: 123456
    """

    if not Config.SMS_API_URL or not Config.SMS_API_TOKEN:
        if Config.APP_ENV == "production":
            raise RuntimeError(
                "SMS is not configured. Add SMS_API_URL and SMS_API_TOKEN in .env."
            )

        return False, f"Development mobile OTP for {mask_phone(phone)} / {public_id}: {otp}"

    mobile_number = clean_indian_phone(phone)

    payload = {
        "variables_values": str(otp),
        "route": "otp",
        "numbers": mobile_number,
    }

    headers = {
        "authorization": Config.SMS_API_TOKEN,
        "Content-Type": "application/json",
        "accept": "*/*",
    }

    response = requests.post(
        Config.SMS_API_URL,
        json=payload,
        headers=headers,
        timeout=20,
    )

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    if response.status_code >= 400:
        raise RuntimeError(f"Fast2SMS request failed: {data}")

    if isinstance(data, dict) and data.get("return") is False:
        raise RuntimeError(f"Fast2SMS rejected SMS: {data}")

    return True, f"Mobile OTP sent to {mask_phone(phone)}."