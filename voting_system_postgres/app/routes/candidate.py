from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from psycopg.errors import UniqueViolation

from .. import db
from ..audit import log_action
from ..mailer import send_otp_email
from ..sms import send_mobile_otp
from ..security import (
    generate_otp,
    generate_public_id,
    hash_otp,
    hash_password,
    login_required,
    normalize_email,
    normalize_phone,
    normalize_public_id,
    role_required,
    verify_otp,
    otp_expiry,
)
from ..storage import save_image, save_proof

candidate_bp = Blueprint("candidate", __name__)


def _unique_candidate_id() -> str:
    while True:
        candidate_id = generate_public_id("CAN")
        if not db.fetch_one("SELECT id FROM candidates WHERE candidate_id = %s", (candidate_id,)):
            return candidate_id


def _parse_expiry(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _create_dual_otps(cur, account_type: str, public_id: str, email: str, phone: str) -> tuple[str, str]:
    email_otp = generate_otp()
    phone_otp = generate_otp()
    cur.execute(
        """
        INSERT INTO otp_codes (account_type, public_id, purpose, delivery_target, otp_hash, expires_at)
        VALUES (%s, %s, 'email_registration', %s, %s, %s)
        """,
        (account_type, public_id, email, hash_otp(email_otp), otp_expiry()),
    )
    cur.execute(
        """
        INSERT INTO otp_codes (account_type, public_id, purpose, delivery_target, otp_hash, expires_at)
        VALUES (%s, %s, 'phone_registration', %s, %s, %s)
        """,
        (account_type, public_id, phone, hash_otp(phone_otp), otp_expiry()),
    )
    return email_otp, phone_otp


def _send_dual_otps(email: str, phone: str, account_type: str, public_id: str, email_otp: str, phone_otp: str) -> None:
    email_delivered, email_message = send_otp_email(email, email_otp, account_type, public_id)
    phone_delivered, phone_message = send_mobile_otp(phone, phone_otp, account_type, public_id)
    flash(email_message, "info")
    flash(phone_message, "info")
    log_action(
        "system",
        public_id,
        f"{account_type}_dual_otp_created",
        f"email={'sent' if email_delivered else 'dev'};phone={'sent' if phone_delivered else 'dev'}",
    )


def _latest_otp(public_id: str, purpose: str) -> dict | None:
    return db.fetch_one(
        """
        SELECT id, otp_hash, expires_at FROM otp_codes
        WHERE account_type = 'candidate' AND public_id = %s AND purpose = %s AND consumed_at IS NULL
        ORDER BY created_at DESC LIMIT 1
        """,
        (public_id, purpose),
    )


def _validate_dual_otp(public_id: str, email_otp: str, phone_otp: str) -> tuple[bool, str, dict | None, dict | None]:
    email_row = _latest_otp(public_id, "email_registration")
    phone_row = _latest_otp(public_id, "phone_registration")
    if not email_row or not phone_row:
        return False, "Both email OTP and mobile OTP are required. Use resend OTP if needed.", email_row, phone_row
    now = datetime.now(timezone.utc)
    if _parse_expiry(email_row["expires_at"]) < now or _parse_expiry(phone_row["expires_at"]) < now:
        return False, "One or both OTPs expired. Use resend OTP.", email_row, phone_row
    if not verify_otp(email_otp, email_row["otp_hash"]):
        return False, "Invalid email OTP.", email_row, phone_row
    if not verify_otp(phone_otp, phone_row["otp_hash"]):
        return False, "Invalid mobile OTP.", email_row, phone_row
    return True, "", email_row, phone_row


@candidate_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = normalize_email(request.form.get("email", ""))
            phone = normalize_phone(request.form.get("phone", ""))
            age = int(request.form.get("age", "0"))
            constituency = request.form.get("constituency", "").strip()
            party = request.form.get("party", "").strip()
            symbol = request.form.get("symbol", "").strip()
            manifesto = request.form.get("manifesto", "").strip()
            password_hash = hash_password(request.form.get("password", ""))
            if not name or not constituency or not party or not symbol:
                raise ValueError("Name, constituency, party, and symbol are required.")
            if age < 18:
                raise ValueError("Candidate age must be at least 18.")
            candidate_id = _unique_candidate_id()
            photo_filename = save_image(request.files.get("photo"), f"candidate_photo_{candidate_id}")
            proof_filename, proof_original = save_proof(request.files.get("proof"), f"candidate_proof_{candidate_id}")
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO candidates (
                            candidate_id, name, email, phone, age, constituency, party, symbol, manifesto,
                            password_hash, proof_filename, proof_original_name, photo_filename,
                            email_verified, phone_verified, is_verified
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE,FALSE)
                        """,
                        (candidate_id, name, email, phone, age, constituency, party, symbol, manifesto, password_hash, proof_filename, proof_original, photo_filename),
                    )
                    email_otp, phone_otp = _create_dual_otps(cur, "candidate", candidate_id, email, phone)
            flash(f"Candidate registration successful. Your Candidate ID is {candidate_id}.", "success")
            _send_dual_otps(email, phone, "candidate", candidate_id, email_otp, phone_otp)
            session["last_candidate_id"] = candidate_id
            return redirect(url_for("candidate.verify"))
        except UniqueViolation:
            flash("Email or mobile number already exists for a candidate.", "danger")
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template("candidate_register.html")


@candidate_bp.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        try:
            public_id = normalize_public_id(request.form.get("candidate_id", ""))
            email_otp = request.form.get("email_otp", "").strip()
            phone_otp = request.form.get("phone_otp", "").strip()
            ok, error, email_row, phone_row = _validate_dual_otp(public_id, email_otp, phone_otp)
            if not ok:
                flash(error, "danger")
                return render_template("verify_candidate.html")
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE otp_codes SET consumed_at = NOW() WHERE id IN (%s, %s)", (email_row["id"], phone_row["id"]))
                    cur.execute(
                        """
                        UPDATE candidates
                        SET email_verified = TRUE, phone_verified = TRUE, is_verified = TRUE, updated_at = NOW()
                        WHERE candidate_id = %s
                        """,
                        (public_id,),
                    )
            log_action("candidate", public_id, "dual_otp_verified")
            flash("Email and mobile OTP verified. Wait for admin approval before appearing on the ballot.", "success")
            return redirect(url_for("auth.login"))
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template("verify_candidate.html")


@candidate_bp.post("/resend-otp")
def resend_otp():
    try:
        public_id = normalize_public_id(request.form.get("candidate_id", ""))
        candidate = db.fetch_one("SELECT candidate_id, email, phone FROM candidates WHERE candidate_id = %s", (public_id,))
        if not candidate:
            flash("Candidate ID not found.", "danger")
            return redirect(url_for("candidate.verify"))
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE otp_codes SET consumed_at = NOW()
                    WHERE account_type = 'candidate' AND public_id = %s AND purpose IN ('email_registration', 'phone_registration') AND consumed_at IS NULL
                    """,
                    (public_id,),
                )
                email_otp, phone_otp = _create_dual_otps(cur, "candidate", public_id, candidate["email"], candidate["phone"])
        _send_dual_otps(candidate["email"], candidate["phone"], "candidate", public_id, email_otp, phone_otp)
        flash("Fresh email and mobile OTPs generated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("candidate.verify"))


@candidate_bp.get("/dashboard")
@login_required
@role_required("candidate")
def dashboard():
    user = session["auth"]
    row = db.fetch_one("SELECT * FROM candidates WHERE id = %s", (user["db_id"],))
    return render_template("candidate_dashboard.html", candidate=row)
