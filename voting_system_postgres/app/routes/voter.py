from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from psycopg.errors import UniqueViolation

from .. import db
from ..audit import log_action
from ..election import status as election_status
from ..mailer import send_otp_email
from ..sms import send_mobile_otp
from ..security import (
    generate_otp,
    generate_public_id,
    hash_otp,
    hash_password,
    login_required,
    make_vote_receipt,
    normalize_email,
    normalize_phone,
    normalize_public_id,
    role_required,
    verify_otp,
    otp_expiry,
)
from ..storage import save_image, save_proof

voter_bp = Blueprint("voter", __name__)


def _unique_voter_id() -> str:
    while True:
        voter_id = generate_public_id("VOT")
        if not db.fetch_one("SELECT id FROM voters WHERE voter_id = %s", (voter_id,)):
            return voter_id


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
        WHERE account_type = 'voter' AND public_id = %s AND purpose = %s AND consumed_at IS NULL
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


@voter_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = normalize_email(request.form.get("email", ""))
            phone = normalize_phone(request.form.get("phone", ""))
            age = int(request.form.get("age", "0"))
            constituency = request.form.get("constituency", "").strip()
            address = request.form.get("address", "").strip()
            password_hash = hash_password(request.form.get("password", ""))
            if not name or not constituency or not address:
                raise ValueError("Name, constituency, and address are required.")
            if age < 18:
                raise ValueError("Voter age must be at least 18.")
            voter_id = _unique_voter_id()
            photo_filename = save_image(request.files.get("photo"), f"voter_photo_{voter_id}")
            proof_filename, proof_original = save_proof(request.files.get("proof"), f"voter_proof_{voter_id}")
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO voters (
                            voter_id, name, email, phone, age, constituency, address, password_hash,
                            proof_filename, proof_original_name, photo_filename,
                            email_verified, phone_verified, is_verified
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE,FALSE)
                        RETURNING id
                        """,
                        (voter_id, name, email, phone, age, constituency, address, password_hash, proof_filename, proof_original, photo_filename),
                    )
                    email_otp, phone_otp = _create_dual_otps(cur, "voter", voter_id, email, phone)
            flash(f"Registration successful. Your Voter ID is {voter_id}.", "success")
            _send_dual_otps(email, phone, "voter", voter_id, email_otp, phone_otp)
            session["last_voter_id"] = voter_id
            return redirect(url_for("voter.verify"))
        except UniqueViolation:
            flash("Email or mobile number is already registered.", "danger")
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template("voter_register.html")


@voter_bp.route("/verify", methods=["GET", "POST"])
def verify():
    if request.method == "POST":
        try:
            public_id = normalize_public_id(request.form.get("voter_id", ""))
            email_otp = request.form.get("email_otp", "").strip()
            phone_otp = request.form.get("phone_otp", "").strip()
            ok, error, email_row, phone_row = _validate_dual_otp(public_id, email_otp, phone_otp)
            if not ok:
                flash(error, "danger")
                return render_template("verify_voter.html")
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE otp_codes SET consumed_at = NOW() WHERE id IN (%s, %s)", (email_row["id"], phone_row["id"]))
                    cur.execute(
                        """
                        UPDATE voters
                        SET email_verified = TRUE, phone_verified = TRUE, is_verified = TRUE, updated_at = NOW()
                        WHERE voter_id = %s
                        """,
                        (public_id,),
                    )
            log_action("voter", public_id, "dual_otp_verified")
            flash("Email and mobile OTP verified. Admin proof approval is still required before voting.", "success")
            return redirect(url_for("auth.login"))
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template("verify_voter.html")


@voter_bp.post("/resend-otp")
def resend_otp():
    try:
        public_id = normalize_public_id(request.form.get("voter_id", ""))
        voter = db.fetch_one("SELECT voter_id, email, phone FROM voters WHERE voter_id = %s AND role = 'voter'", (public_id,))
        if not voter:
            flash("Voter ID not found.", "danger")
            return redirect(url_for("voter.verify"))
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE otp_codes SET consumed_at = NOW()
                    WHERE account_type = 'voter' AND public_id = %s AND purpose IN ('email_registration', 'phone_registration') AND consumed_at IS NULL
                    """,
                    (public_id,),
                )
                email_otp, phone_otp = _create_dual_otps(cur, "voter", public_id, voter["email"], voter["phone"])
        _send_dual_otps(voter["email"], voter["phone"], "voter", public_id, email_otp, phone_otp)
        flash("Fresh email and mobile OTPs generated.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("voter.verify"))


@voter_bp.route("/vote", methods=["GET", "POST"])
@login_required
@role_required("voter")
def vote():
    user = session["auth"]
    voter = db.fetch_one("SELECT * FROM voters WHERE id = %s", (user["db_id"],))
    estatus = election_status()
    candidates = []
    if voter:
        candidates = db.fetch_all(
            """
            SELECT id, candidate_id, name, party, symbol, manifesto, constituency, votes
            FROM candidates
            WHERE status = 'approved' AND is_verified = TRUE AND proof_status = 'approved' AND constituency = %s
            ORDER BY name ASC
            """,
            (voter["constituency"],),
        )

    if request.method == "POST":
        candidate_id = int(request.form.get("candidate_db_id", "0"))
        confirm_id = normalize_public_id(request.form.get("confirm_voter_id", ""))
        if confirm_id != user["public_id"]:
            flash("Voter ID confirmation failed.", "danger")
            return redirect(url_for("voter.vote"))
        if not estatus["open"]:
            flash("Election is not open right now.", "danger")
            return redirect(url_for("voter.vote"))
        if not voter or not voter["email_verified"] or not voter["phone_verified"] or not voter["is_verified"]:
            flash("Email and mobile verification are required before voting.", "danger")
            return redirect(url_for("voter.vote"))
        if voter["proof_status"] != "approved":
            flash("Your ID proof must be approved by admin before voting.", "warning")
            return redirect(url_for("voter.vote"))
        try:
            receipt = make_vote_receipt(user["public_id"], candidate_id)
            with db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM voters WHERE id = %s FOR UPDATE", (user["db_id"],))
                    locked_voter = cur.fetchone()
                    if locked_voter["has_voted"]:
                        raise ValueError("You have already voted.")
                    cur.execute(
                        """
                        SELECT * FROM candidates
                        WHERE id = %s AND status = 'approved' AND is_verified = TRUE AND proof_status = 'approved' AND constituency = %s
                        FOR UPDATE
                        """,
                        (candidate_id, locked_voter["constituency"]),
                    )
                    candidate = cur.fetchone()
                    if not candidate:
                        raise ValueError("Selected candidate is not available for your constituency.")
                    cur.execute(
                        "INSERT INTO votes (voter_db_id, candidate_db_id, constituency, vote_receipt_hash) VALUES (%s, %s, %s, %s)",
                        (locked_voter["id"], candidate["id"], locked_voter["constituency"], receipt),
                    )
                    cur.execute("UPDATE voters SET has_voted = TRUE, updated_at = NOW() WHERE id = %s", (locked_voter["id"],))
                    cur.execute("UPDATE candidates SET votes = votes + 1, updated_at = NOW() WHERE id = %s", (candidate["id"],))
            log_action("voter", user["public_id"], "vote_cast", f"receipt={receipt[:16]}... candidate hidden")
            flash(f"Vote submitted successfully. Receipt hash: {receipt[:18]}...", "success")
            return redirect(url_for("public.results"))
        except Exception as exc:
            flash(str(exc), "danger")
    return render_template("vote.html", voter=voter, candidates=candidates, estatus=estatus)
