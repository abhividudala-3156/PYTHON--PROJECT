from __future__ import annotations

from flask import request

from . import db


def log_action(actor_role: str, actor_identifier: str, action: str, details: str = "") -> None:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "") if request else ""
    db.execute(
        """
        INSERT INTO audit_log (actor_role, actor_identifier, action, details, ip_address)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (actor_role, actor_identifier, action, details, ip),
    )
