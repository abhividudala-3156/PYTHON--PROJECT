from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .. import db
from ..audit import log_action
from ..security import login_required, normalize_public_id, verify_password

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15

auth_bp = Blueprint("auth", __name__)


def _locked_until_text(row: dict) -> str | None:
    locked_until = row.get("locked_until")
    if not locked_until:
        return None
    if isinstance(locked_until, str):
        locked_dt = datetime.fromisoformat(locked_until)
    else:
        locked_dt = locked_until
    if locked_dt.tzinfo is None:
        locked_dt = locked_dt.replace(tzinfo=timezone.utc)
    if locked_dt > datetime.now(timezone.utc):
        return locked_dt.strftime("%d-%m-%Y %I:%M %p UTC")
    return None


def _record_failed(table: str, public_col: str, public_id: str, current_attempts: int | None) -> None:
    attempts = int(current_attempts or 0) + 1
    locked_until = None
    if attempts >= LOCKOUT_THRESHOLD:
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        attempts = 0
    db.execute(
        f"UPDATE {table} SET failed_login_attempts = %s, locked_until = %s WHERE {public_col} = %s",
        (attempts, locked_until, public_id),
    )


def _verification_missing(row: dict) -> str | None:
    missing = []
    if not row.get("email_verified"):
        missing.append("email OTP")
    if not row.get("phone_verified"):
        missing.append("mobile OTP")
    if missing:
        return " and ".join(missing)
    if not row.get("is_verified"):
        return "final verification"
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account_type = request.form.get("account_type", "voter")
        try:
            public_id = normalize_public_id(request.form.get("public_id", ""))
        except ValueError:
            flash("Invalid ID format.", "danger")
            return render_template("login.html")
        password = request.form.get("password", "")

        if account_type in {"voter", "admin"}:
            row = db.fetch_one("SELECT * FROM voters WHERE voter_id = %s", (public_id,))
            table, public_col = "voters", "voter_id"
        else:
            row = db.fetch_one("SELECT * FROM candidates WHERE candidate_id = %s", (public_id,))
            table, public_col = "candidates", "candidate_id"

        if not row:
            flash("Invalid ID or password.", "danger")
            return render_template("login.html")

        locked_text = _locked_until_text(row)
        if locked_text:
            flash(f"Account temporarily locked until {locked_text}.", "danger")
            return render_template("login.html")

        if not verify_password(password, row["password_hash"]):
            _record_failed(table, public_col, public_id, row.get("failed_login_attempts"))
            flash("Invalid ID or password.", "danger")
            return render_template("login.html")

        resolved_role = "candidate" if account_type == "candidate" else row["role"]
        if account_type == "admin" and resolved_role != "admin":
            flash("This account is not an admin account.", "danger")
            return render_template("login.html")
        if account_type == "voter" and row["role"] != "voter":
            flash("Use Admin login for admin account.", "warning")
            return render_template("login.html")

        if resolved_role in {"voter", "candidate"}:
            missing = _verification_missing(row)
            if missing:
                flash(f"Please verify your {missing} before login.", "warning")
                return redirect(url_for("candidate.verify" if resolved_role == "candidate" else "voter.verify"))

        db.execute(
            f"UPDATE {table} SET failed_login_attempts = 0, locked_until = NULL, last_login_at = NOW() WHERE {public_col} = %s",
            (public_id,),
        )
        session.permanent = True
        session["auth"] = {
            "role": resolved_role,
            "db_id": row["id"],
            "public_id": public_id,
            "name": row["name"],
            "email": row["email"],
        }
        log_action(resolved_role, public_id, "login_success")
        flash("Logged in successfully.", "success")
        if resolved_role == "admin":
            return redirect(url_for("admin.dashboard"))
        if resolved_role == "candidate":
            return redirect(url_for("candidate.dashboard"))
        return redirect(url_for("voter.vote"))

    return render_template("login.html")


@auth_bp.get("/logout")
@login_required
def logout():
    user = session.get("auth", {})
    log_action(user.get("role", "unknown"), user.get("public_id", "unknown"), "logout")
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("public.home"))
