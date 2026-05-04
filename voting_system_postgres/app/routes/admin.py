from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, send_file, session, url_for

from .. import db
from ..audit import log_action
from ..election import set_setting
from ..security import login_required, role_required
from ..storage import read_encrypted_file

admin_bp = Blueprint("admin", __name__)


def _filter_clause(prefix: str, q: str, status: str, is_candidate: bool = False) -> tuple[str, list]:
    clauses = []
    params: list = []
    if q:
        id_col = "candidate_id" if is_candidate else "voter_id"
        clauses.append(f"({prefix}.name ILIKE %s OR {prefix}.{id_col} ILIKE %s OR {prefix}.email ILIKE %s OR {prefix}.phone ILIKE %s OR {prefix}.constituency ILIKE %s)")
        like = f"%{q}%"
        params.extend([like, like, like, like, like])
    if status and status != "all":
        col = "status" if is_candidate else "proof_status"
        clauses.append(f"{prefix}.{col} = %s")
        params.append(status)
    return (" AND " + " AND ".join(clauses) if clauses else "", params)


@admin_bp.get("/dashboard")
@login_required
@role_required("admin")
def dashboard():
    q = request.args.get("q", "").strip()
    voter_status = request.args.get("voter_status", "all")
    candidate_status = request.args.get("candidate_status", "all")

    total_voters = db.fetch_one("SELECT COUNT(*) AS count FROM voters WHERE role = 'voter'")["count"]
    total_votes = db.fetch_one("SELECT COUNT(*) AS count FROM votes")["count"]
    stats = {
        "voters": total_voters,
        "verified_voters": db.fetch_one("SELECT COUNT(*) AS count FROM voters WHERE role = 'voter' AND email_verified = TRUE AND phone_verified = TRUE")["count"],
        "pending_voters": db.fetch_one("SELECT COUNT(*) AS count FROM voters WHERE role = 'voter' AND proof_status = 'pending'")["count"],
        "candidates": db.fetch_one("SELECT COUNT(*) AS count FROM candidates")["count"],
        "approved_candidates": db.fetch_one("SELECT COUNT(*) AS count FROM candidates WHERE status = 'approved'")["count"],
        "pending_candidates": db.fetch_one("SELECT COUNT(*) AS count FROM candidates WHERE status = 'pending'")["count"],
        "votes": total_votes,
        "turnout": round((total_votes / total_voters) * 100, 1) if total_voters else 0,
    }

    voter_clause, voter_params = _filter_clause("v", q, voter_status, False)
    candidate_clause, candidate_params = _filter_clause("c", q, candidate_status, True)
    voters = db.fetch_all(
        f"""
        SELECT id, voter_id, name, email, phone, constituency, age, email_verified, phone_verified, is_verified,
               proof_status, has_voted, proof_original_name, created_at, last_login_at
        FROM voters v WHERE role = 'voter' {voter_clause}
        ORDER BY created_at DESC LIMIT 150
        """,
        tuple(voter_params),
    )
    candidates = db.fetch_all(
        f"""
        SELECT id, candidate_id, name, email, phone, constituency, age, party, symbol, status, email_verified,
               phone_verified, is_verified, proof_status, votes, proof_original_name, created_at, last_login_at
        FROM candidates c WHERE TRUE {candidate_clause}
        ORDER BY created_at DESC LIMIT 150
        """,
        tuple(candidate_params),
    )
    logs = db.fetch_all("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 60")
    settings = {row["key"]: row["value"] for row in db.fetch_all("SELECT key, value FROM settings")}
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        voters=voters,
        candidates=candidates,
        logs=logs,
        settings=settings,
        filters={"q": q, "voter_status": voter_status, "candidate_status": candidate_status},
    )


@admin_bp.post("/settings")
@login_required
@role_required("admin")
def update_settings():
    enabled = "true" if request.form.get("election_enabled") == "on" else "false"
    public_results = "true" if request.form.get("public_results_enabled") == "on" else "false"
    set_setting("election_enabled", enabled)
    set_setting("public_results_enabled", public_results)
    set_setting("election_start", request.form.get("election_start", ""))
    set_setting("election_end", request.form.get("election_end", ""))
    user = session["auth"]
    log_action("admin", user["public_id"], "update_election_settings", f"enabled={enabled};public_results={public_results}")
    flash("Election settings updated.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/voter/<int:voter_id>/<status>")
@login_required
@role_required("admin")
def update_voter_status(voter_id: int, status: str):
    if status not in {"approved", "rejected", "pending"}:
        abort(400)
    voter = db.fetch_one("SELECT email_verified, phone_verified FROM voters WHERE id = %s AND role = 'voter'", (voter_id,))
    if not voter:
        abort(404)
    if status == "approved" and (not voter["email_verified"] or not voter["phone_verified"]):
        flash("Voter must complete both email and mobile OTP verification before proof approval.", "warning")
        return redirect(url_for("admin.dashboard"))
    db.execute("UPDATE voters SET proof_status = %s, updated_at = NOW() WHERE id = %s AND role = 'voter'", (status, voter_id))
    user = session["auth"]
    log_action("admin", user["public_id"], "update_voter_proof_status", f"voter_db_id={voter_id};status={status}")
    flash(f"Voter proof marked {status}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/candidate/<int:candidate_id>/<status>")
@login_required
@role_required("admin")
def update_candidate_status(candidate_id: int, status: str):
    if status not in {"approved", "rejected", "pending"}:
        abort(400)
    candidate = db.fetch_one("SELECT email_verified, phone_verified FROM candidates WHERE id = %s", (candidate_id,))
    if not candidate:
        abort(404)
    if status == "approved" and (not candidate["email_verified"] or not candidate["phone_verified"]):
        flash("Candidate must complete both email and mobile OTP verification before approval.", "warning")
        return redirect(url_for("admin.dashboard"))
    proof_status = "approved" if status == "approved" else ("rejected" if status == "rejected" else "pending")
    db.execute("UPDATE candidates SET status = %s, proof_status = %s, updated_at = NOW() WHERE id = %s", (status, proof_status, candidate_id))
    user = session["auth"]
    log_action("admin", user["public_id"], "update_candidate_status", f"candidate_db_id={candidate_id};status={status}")
    flash(f"Candidate marked {status}.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/reset-election")
@login_required
@role_required("admin")
def reset_election():
    confirmation = request.form.get("confirmation", "").strip().upper()
    if confirmation != "RESET":
        flash("Type RESET to confirm election reset.", "warning")
        return redirect(url_for("admin.dashboard"))
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM votes")
            cur.execute("UPDATE voters SET has_voted = FALSE WHERE role = 'voter'")
            cur.execute("UPDATE candidates SET votes = 0")
    user = session["auth"]
    log_action("admin", user["public_id"], "reset_election")
    flash("Election votes reset.", "warning")
    return redirect(url_for("admin.dashboard"))


def _csv_response(filename: str, rows: list[dict]) -> Response:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("empty\n")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_bp.get("/export/<kind>")
@login_required
@role_required("admin")
def export(kind: str):
    if kind == "voters":
        rows = db.fetch_all("SELECT voter_id, name, email, phone, age, constituency, email_verified, phone_verified, is_verified, proof_status, has_voted, created_at, last_login_at FROM voters WHERE role = 'voter' ORDER BY created_at DESC")
    elif kind == "candidates":
        rows = db.fetch_all("SELECT candidate_id, name, email, phone, age, constituency, party, symbol, email_verified, phone_verified, is_verified, proof_status, status, votes, created_at, last_login_at FROM candidates ORDER BY created_at DESC")
    elif kind == "votes":
        rows = db.fetch_all("SELECT v.voter_id, v.constituency, vo.vote_receipt_hash, vo.created_at FROM votes vo JOIN voters v ON v.id = vo.voter_db_id ORDER BY vo.created_at DESC")
    elif kind == "audit":
        rows = db.fetch_all("SELECT actor_role, actor_identifier, action, details, ip_address, created_at FROM audit_log ORDER BY created_at DESC")
    else:
        abort(404)
    user = session["auth"]
    log_action("admin", user["public_id"], "export_csv", kind)
    return _csv_response(f"{kind}.csv", rows)


@admin_bp.get("/proof/<account_type>/<int:db_id>")
@login_required
@role_required("admin")
def download_proof(account_type: str, db_id: int):
    if account_type == "voter":
        row = db.fetch_one("SELECT proof_filename, proof_original_name FROM voters WHERE id = %s", (db_id,))
    elif account_type == "candidate":
        row = db.fetch_one("SELECT proof_filename, proof_original_name FROM candidates WHERE id = %s", (db_id,))
    else:
        abort(404)
    if not row or not row["proof_filename"]:
        abort(404)
    payload = read_encrypted_file(row["proof_filename"])
    filename = row["proof_original_name"] or "proof-file"
    user = session["auth"]
    log_action("admin", user["public_id"], "download_proof", f"{account_type}:{db_id}")
    return send_file(io.BytesIO(payload), as_attachment=True, download_name=filename)
