from __future__ import annotations

from datetime import datetime, timezone

from . import db


def get_setting(key: str, default: str = "") -> str:
    row = db.fetch_one("SELECT value FROM settings WHERE key = %s", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    db.execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, value),
    )


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def status() -> dict[str, object]:
    enabled = get_setting("election_enabled", "false") == "true"
    start_raw = get_setting("election_start", "")
    end_raw = get_setting("election_end", "")
    start_dt = _parse_dt(start_raw)
    end_dt = _parse_dt(end_raw)
    now = datetime.now(timezone.utc)

    if not enabled:
        return {"enabled": False, "open": False, "message": "Election is currently disabled by admin."}
    if not start_dt or not end_dt:
        return {"enabled": True, "open": False, "message": "Election timing is not configured."}
    if now < start_dt:
        return {"enabled": True, "open": False, "message": f"Election starts at {start_dt.strftime('%d-%m-%Y %I:%M %p UTC')}."}
    if now > end_dt:
        return {"enabled": True, "open": False, "message": f"Election ended at {end_dt.strftime('%d-%m-%Y %I:%M %p UTC')}."}
    return {"enabled": True, "open": True, "message": f"Election is open until {end_dt.strftime('%d-%m-%Y %I:%M %p UTC')}."}
